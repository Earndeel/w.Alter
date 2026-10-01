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


@app.post("/v1/context", dependencies=[Depends(auth)])
def post_context(body: ContextIn):
    import hashlib
    import json as _json
    from . import context
    res = context.get_context(body.query, budget=body.budget, include_profile=body.include_profile)
    with connection() as conn:
        conn.execute("""insert into system.context_requests (caller, mode, session_id, query_sha, total_tokens, sections, latency_ms)
                        values (%s,%s,%s,%s,%s,%s,%s)""",
                     (body.caller, body.mode, body.session_id, hashlib.sha256(body.query.encode()).hexdigest(),
                      res["trace"].get("total_tokens"),
                      _json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "refs"} for k, v in res["trace"]["sections"].items()}),
                      res["trace"].get("latency_ms")))
    return res
