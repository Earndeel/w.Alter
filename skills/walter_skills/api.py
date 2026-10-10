"""HTTP port of walter-skills (127.0.0.1:8891). No policy here: policy.py decides, this only transports.

POST /v1/expose            {kind: message|error|session_start, message, context, session_id, runtime, first_turn}
POST /v1/search            {query|message, context, k, include_archived, runtime, session_id}    (tier 2)
GET  /v1/skill/{name}      ?file_path=&runtime=&session_id=                                      (tier 2)
GET  /v1/map               ?runtime=                                                             (tier 0)
POST /v1/skills/propose    POST /v1/skills/patch                                                 (write door)
GET  /health
A background thread hot-swaps the engine when the active ranker or the store (git HEAD) changes.
"""
from __future__ import annotations

import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import domains, door, policy, registry, store
from .retrieval import engine, read_skill

app = FastAPI(title="walter-skills")
_write_lock = threading.Lock()


class ExposeIn(BaseModel):
    kind: str = "message"
    message: str = ""
    context: str = ""
    session_id: str | None = None
    runtime: str = "agent"
    first_turn: bool = False


class SearchIn(BaseModel):
    query: str | None = None
    message: str | None = None  # accepted for older clients
    context: str = ""
    k: int = 8
    include_archived: bool = False
    runtime: str = "agent"
    session_id: str | None = None


class ProposeIn(BaseModel):
    name: str
    skill_md: str
    reason: str
    files: dict[str, str] | None = None
    domain: str = ""
    runtime: str | None = None
    session_id: str | None = None


class PatchIn(BaseModel):
    name: str
    reason: str
    skill_md: str | None = None
    file_path: str | None = None
    content: str | None = None
    runtime: str | None = None
    session_id: str | None = None


@app.post("/v1/expose")
def expose(body: ExposeIn) -> dict:
    return policy.expose(body.kind, body.message, context=body.context, session_id=body.session_id,
                         runtime=body.runtime, first_turn=body.first_turn).as_dict()


@app.post("/v1/search")
def search(body: SearchIn) -> dict:
    q = body.query or body.message or ""
    return {"results": policy.search(q, body.context, max(1, min(body.k, 20)), body.include_archived, body.runtime,
                                     body.session_id), "model": engine().version}


@app.get("/v1/skill/{name}", response_class=PlainTextResponse)
def skill(name: str, file_path: str | None = None, runtime: str | None = None, session_id: str | None = None) -> str:
    text = read_skill(name, file_path or None)
    if text is None:
        raise HTTPException(404, f"unknown skill or file: {name} {file_path or ''}")
    try:
        registry.journal_read(runtime, session_id, name, "http")
    except Exception:
        pass
    return text


@app.get("/v1/map", response_class=PlainTextResponse)
def domain_map(runtime: str = "agent") -> str:
    return domains.render(policy._tools(runtime)[1])


def _door(fn, **kw) -> dict:
    try:
        with _write_lock:  # one git writer at a time
            return {"ok": True} | fn(**kw)
    except door.Refused as e:
        return {"ok": False, "refused": str(e)}


@app.post("/v1/skills/propose")
def propose(body: ProposeIn) -> dict:
    return _door(door.propose, **body.model_dump())


@app.post("/v1/skills/patch")
def patch(body: PatchIn) -> dict:
    return _door(door.patch, **body.model_dump())


@app.get("/health")
def health() -> dict:
    e = engine()
    return {"ok": True, "ranker": e.version, "degraded": e.degraded, "skills": len(e.skills)}


def _watch(period: float = 60.0) -> None:
    """Hot reload: a newly promoted ranker or a new store commit → rebuild the engine aside and swap it in."""
    last = (None, None)
    while True:
        time.sleep(period)
        try:
            row = registry.ranker()
            cur = (row["version"] if row else None, store.git("rev-parse", "HEAD", check=False))
            if last[0] is None:
                last = cur
            elif cur != last:
                engine(reload=True)
                last = cur
        except Exception:
            pass  # registry or git unreachable: keep serving the current engine


@app.on_event("startup")
def _start() -> None:
    threading.Thread(target=engine, daemon=True).start()  # warm up without blocking the port
    threading.Thread(target=_watch, daemon=True).start()
