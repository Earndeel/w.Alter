"""Ingestion Gateway (HTTP, 127.0.0.1:8890): the single write door for remote/agent connectors.

Local connectors may import the library directly; anything outside this process tree (Mac agents, phone
shortcuts, other harnesses) goes through here. Bearer token from /opt/walter-memory/.env (0600).
"""
from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from . import events, ingestion, objects, types
from .db import connection

TOKEN = os.environ.get("WALTER_MEMORY_GATEWAY_TOKEN", "")
app = FastAPI(title="walter-memory gateway", version="1")


def auth(authorization: str = Header(default="")) -> None:
    if not TOKEN or not secrets.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(401, "unauthorized")


class EventsIn(BaseModel):
    events: list[dict]
    connector: str | None = None
    checkpoint: dict | None = None        # {"stream": "...", "cursor": {...}} advanced atomically with the batch


@app.get("/v1/health")
def health():
    with connection() as conn:
        conn.execute("select 1")
    return {"status": "ok"}


@app.post("/v1/events", dependencies=[Depends(auth)])
def post_events(body: EventsIn):
    try:
        with connection() as conn:
            res = events.record_events(body.events, conn=conn)
            if body.connector and body.checkpoint:
                ingestion.set_checkpoint(body.connector, body.checkpoint.get("stream", ""),
                                         body.checkpoint.get("cursor") or {}, conn=conn)
    except (types.UnknownEventType, types.InvalidPayload, KeyError, ValueError) as e:
        raise HTTPException(422, str(e))
    if body.connector:
        ingestion.mark_success(body.connector)
    return {"inserted": res["inserted"], "duplicates": res["duplicates"]}


@app.get("/v1/events", dependencies=[Depends(auth)])
def list_events(source: str | None = None, event_type: str | None = None, thread_id: str | None = None,
                since: str | None = None, text: str | None = None, limit: int = 50):
    return events.get_events(source=source, event_types=[event_type] if event_type else None, thread_id=thread_id,
                             since=since, text=text, limit=min(limit, 500))


@app.post("/v1/objects", dependencies=[Depends(auth)])
def post_object(file: UploadFile = File(...), source: str = Form(...), captured_at: str | None = Form(None),
                privacy_class: str | None = Form(None)):
    from datetime import datetime
    with tempfile.TemporaryDirectory(dir="/var/tmp") as d:
        path = Path(d) / objects.safe_name(file.filename or "upload")
        with path.open("wb") as f:
            while chunk := file.file.read(1 << 20):
                f.write(chunk)
        row = objects.put_object(path, source, original_name=file.filename,
                                 captured_at=datetime.fromisoformat(captured_at) if captured_at else None,
                                 privacy_class=privacy_class)
    return {k: str(row[k]) for k in ("id", "created", "kind", "storage_zone", "privacy_class")}


@app.get("/v1/checkpoints/{connector}", dependencies=[Depends(auth)])
def get_checkpoint(connector: str, stream: str = ""):
    return ingestion.get_checkpoint(connector, stream)


class ContextIn(BaseModel):
    query: str
    budget: dict | None = None
    include_profile: bool = True
    caller: str = "unknown"
    mode: str = "on"
    session_id: str | None = None
    cloud_safe: bool = False     # E2: drop any line that looks like a secret (the engine's context goes to the cloud)


class AgentMemoryIn(BaseModel):
    version: int = 1
    method: str
    args: dict
    caller: str = 'http-port'


@app.post('/v1/agent-memory', dependencies=[Depends(auth)])
def post_agent_memory(body: AgentMemoryIn):
    """Same module contract as MCP/CLI, including canonical privacy checks."""
    from . import agent_memory
    try:
        return agent_memory.dispatch(body.model_dump())
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, 'invalid agent memory request') from None
    except Exception:
        raise HTTPException(503, 'agent memory temporarily unavailable') from None


@app.post("/v1/views/read", dependencies=[Depends(auth)])
def post_views_read(body: dict):
    """Memory Views (lot 3): the MemoryViewQuery v1 contract of walter-context (depth, key | domain, horizon,
    max_tokens, max_age_s, privacy)."""
    from . import views
    res = views.read(body)
    if "error" in res:
        raise HTTPException(404 if res["error"].startswith("no view") else 422, res["error"])
    return res


@app.post("/v1/views/candidates", dependencies=[Depends(auth)])
def post_views_candidates(body: dict):
    """The subjects a new owner message may belong to (walter-context preflight): {message, session_id, limit}."""
    from . import views
    return views.subject_candidates(str(body.get("message") or "")[:4000], body.get("session_id"),
                                    limit=max(1, min(int(body.get("limit") or 5), 10)))


# The hooks' callers and the runtime (core.events source) whose thread their session_id names (P1.1 working state)
RUNTIME_OF_CALLER = {"claude-code-hook": "claude_code", "codex-hook": "codex", "dsh-hook": "dsh",
                     "hermes-shell-hook": "hermes", "hermes": "hermes"}


@app.post("/v1/context", dependencies=[Depends(auth)])
def post_context(body: ContextIn):
    import hashlib
    import json as _json
    from . import context
    source = RUNTIME_OF_CALLER.get(body.caller)
    session = (source, body.session_id.rsplit("/", 1)[-1]) if source and body.session_id else None
    res = context.get_context(body.query, budget=body.budget, include_profile=body.include_profile, session=session)
    with connection() as conn:
        conn.execute("""insert into system.context_requests (caller, mode, session_id, query_sha, total_tokens, sections, latency_ms)
                        values (%s,%s,%s,%s,%s,%s,%s)""",
                     (body.caller, body.mode, body.session_id, hashlib.sha256(body.query.encode()).hexdigest(),
                      res["trace"].get("total_tokens"),
                      _json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "refs"} for k, v in res["trace"]["sections"].items()}),
                      res["trace"].get("latency_ms")))
    if body.cloud_safe and res.get("text"):
        from . import privacy
        res["text"] = "\n".join(l for l in res["text"].splitlines()
                                 if not any(cat == "secret" for cat, _ in privacy.detect(l)))
    return res


# ── Engine lot E2 (2026-11-10): the engine's intake and events speak HTTP to Walter's single sources ──────────────
# The Run Plane stays the only source of runs and the bus the only source of events; these routes only transport the
# same writes the hook makes through the library (walter_hook.run_start / run_end / emit), so a native engine plugin
# needs no Python. Never a second registry.

ENGINE_BUS_TYPES = {"turn.started", "turn.ended", "session.ended"}
RUN_CHANNELS = {"owner", "machine", "test"}


class RunStartIn(BaseModel):
    origin: dict                       # {"channel", "runtime", "session_id"}
    goal: str | None = None
    dedupe_key: str | None = None      # one run per turn: a replayed turn returns the same run
    cancel_run_id: str | None = None   # this session's previous run that never got its end
    routing: dict | None = None


class RunEndIn(BaseModel):
    run_id: str | None = None
    session_id: str | None = None
    status: str = "ended"


class BusEmitIn(BaseModel):
    type: str
    source: str
    subject: str | None = None
    payload: dict | None = None
    dedupe_key: str | None = None


def _run_of(run_id: str) -> dict | None:
    """The session that opened a run and its idempotency key (None for an unknown or malformed id)."""
    try:
        with connection() as conn:
            return conn.execute("select origin->>'session_id' session, dedupe_key from runs.runs where run_id::text = %s",
                                (run_id,)).fetchone()
    except Exception:  # noqa: BLE001 — a malformed id is simply unknown
        return None


def _run_session(run_id: str) -> str | None:
    row = _run_of(run_id)
    return row["session"] if row else None


def _episode_later(run_id: str) -> None:
    """The run's episode once its transcript is journaled (detached, as the hook does; `episodes pending` repairs)."""
    import shutil
    import subprocess
    if os.environ.get("WALTER_EPISODES", "on") == "off" or not shutil.which("walter-memory"):
        return
    subprocess.Popen(["sh", "-c", f"sleep 30; exec walter-memory episodes build {run_id}"], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


@app.post("/v1/runs/start", dependencies=[Depends(auth)])
def post_runs_start(body: RunStartIn):
    from . import privacy, runs
    o = body.origin or {}
    if not o.get("runtime") or not o.get("session_id") or o.get("channel", "owner") not in RUN_CHANNELS:
        raise HTTPException(422, "origin needs runtime, session_id and a known channel")
    origin = {"channel": o.get("channel", "owner"), "runtime": str(o["runtime"]), "session_id": str(o["session_id"])}
    if body.cancel_run_id:              # only a run of the same session is ever interrupted
        prev = _run_of(body.cancel_run_id)       # a replay of the same turn never cancels the run it gets back
        if prev and prev["session"] == origin["session_id"] and (not body.dedupe_key or prev["dedupe_key"] != body.dedupe_key):
            runs.safe(runs.end, body.cancel_run_id, "cancelled")
    secret = any(cat == "secret" for cat, _ in privacy.detect(body.goal or ""))
    privacy_class = "local_only" if secret else "cloud_allowed"
    run_id = runs.start(origin=origin, goal=body.goal, privacy_class=privacy_class, dedupe_key=body.dedupe_key)
    if body.routing:
        runs.safe(runs.routing, run_id, body.routing)
    return {"run_id": run_id, "privacy_class": privacy_class}


@app.post("/v1/runs/end", dependencies=[Depends(auth)])
def post_runs_end(body: RunEndIn):
    from . import runs
    if body.status not in ("ended", "cancelled", "failed"):
        raise HTTPException(422, "unknown status")
    run_id = None
    if body.run_id:
        owner = _run_session(body.run_id)
        if owner is not None and (not body.session_id or owner == body.session_id):
            runs.end(body.run_id, body.status)
            run_id = body.run_id
    if run_id is None and body.session_id:
        run_id = runs.end_open(body.session_id, body.status)
    if run_id:
        _episode_later(run_id)
    return {"run_id": run_id}


@app.post("/v1/bus/emit", dependencies=[Depends(auth)])
def post_bus_emit(body: BusEmitIn):
    """Lifecycle events of an agent runtime (turn.started, turn.ended, session.ended). An observation (shadow) never
    reaches the production bus: `payload.observation` is refused here, whatever the caller believes."""
    from . import bus
    if body.type not in ENGINE_BUS_TYPES:
        raise HTTPException(422, "event type not open to runtimes")
    if (body.payload or {}).get("observation"):
        raise HTTPException(422, "observations never go to the production bus")
    with connection() as conn:
        event_id = bus.emit(body.type, body.source, body.subject, body.payload, body.dedupe_key, conn=conn)
    return {"id": event_id, "duplicate": event_id is None}


@app.post("/v1/privacy/classify", dependencies=[Depends(auth)])
def post_privacy_classify(body: dict):
    """The privacy class a text would get (no write): a runtime that cannot run the detectors asks before any cloud
    call. Returns the categories found, never the matched text."""
    from . import privacy
    found = sorted({cat for cat, _ in privacy.detect(str(body.get("text") or "")[:20000])})
    return {"privacy_class": "local_only" if "secret" in found else "cloud_allowed", "categories": found}
