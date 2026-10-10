"""walter-skills service (127.0.0.1:8891): the one place every runtime asks "which skill for this message?".

POST /v1/search  {message, context?, session_id?, runtime?, k?, include_archived?, mode?}  → ranked skills
GET  /v1/skill/{name}?file_path=…                                                          → SKILL.md (or a file)
GET  /health
Local only, read-only on the store. Each search is journaled in skills.retrievals (hash + length, never the text).
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from . import engine, history, proposals

sys.path.insert(0, "/opt/walter-memory")
from walter_memory.db import connection  # noqa: E402

app = FastAPI(title="walter-skills")
_engine: engine.Engine | None = None
_lock = threading.Lock()


def eng() -> engine.Engine:
    global _engine
    with _lock:
        if _engine is None:
            _engine = engine.load_engine()
    return _engine


class SearchIn(BaseModel):
    message: str
    context: str = ""
    session_id: str | None = None
    runtime: str | None = None
    k: int = 5
    include_archived: bool = False
    mode: str = "search"  # search | inject | shadow (journal label only)
    choose: bool = False  # optional stage 2 (separate LLM picks); off by default since 2026-10-09: the agent's own model chooses
    need_threshold: float = 0.4  # local gate: below it, nothing is proposed for injection
    privacy_class: str = "cloud_allowed"  # of the message; local_only never leaves the VM (local ranking only)


def _journal(body: SearchIn, results: list[dict], injected: list[str], ms: int, model: str) -> None:
    try:
        with connection() as conn:
            conn.execute(
                """insert into skills.retrievals (runtime, session_id, mode, query_sha, query_chars, results, injected,
                                                  latency_ms, model)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (body.runtime, body.session_id, body.mode, hashlib.sha256(body.message.encode()).hexdigest()[:16],
                 len(body.message), json.dumps([{"name": r["name"], "score": r["score"]} for r in results]),
                 injected, ms, model))
    except Exception:  # journal is best effort
        pass


@app.post("/v1/search")
def search(body: SearchIn) -> dict:
    t0 = time.perf_counter()
    e = eng()
    session = {}
    if body.session_id:
        try:
            session = history.session_history(body.session_id, e.aliases)
        except Exception:
            session = {}
    k = max(1, min(body.k, 20))
    results = e.search(body.message[:4000], body.context[:2000], session=session, k=40 if body.choose else k,
                       include_archived=body.include_archived)
    need = e.last_need
    chosen, stage = None, "local"
    if body.choose and body.privacy_class != "local_only":
        chosen = engine.choose(body.message, body.context, [r for r in results if r["state"] == "active"],
                               privacy_class=body.privacy_class)
    if chosen is not None:
        stage = "chooser"
        by = {r["name"]: r for r in results}
        picked = [by[n] | {"chosen": True} for n in chosen]
        results = picked + [r for r in results if r["name"] not in chosen]
    results = results[:k]
    inject = [r["name"] for r in results if r.get("chosen")] if stage == "chooser" else \
        ([r["name"] for r in results if r["state"] == "active"] if (need is None or need >= body.need_threshold) else [])
    ms = round(1000 * (time.perf_counter() - t0))
    _journal(body, results, inject if body.mode in ("inject", "shadow") else [], ms, f"{e.version}/{stage}")
    return {"results": results, "inject": inject, "need": need, "stage": stage, "latency_ms": ms,
            "model": e.version, "session_skills": sorted(session)}


@app.get("/v1/skill/{name}", response_class=PlainTextResponse)
def skill(name: str, file_path: str | None = None, runtime: str | None = None, session_id: str | None = None) -> str:
    text = engine.read_skill(name, file_path)
    if text is None:
        raise HTTPException(404, f"unknown skill or file: {name} {file_path or ''}")
    try:
        with connection() as conn:
            conn.execute("insert into skills.reads (runtime, session_id, name, via) values (%s, %s, %s, %s)",
                         (runtime, session_id, name, "http"))
    except Exception:
        pass
    return text


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


def _door(fn, **kw) -> dict:
    try:
        with _lock:  # one writer at a time (git)
            return {"ok": True} | fn(**kw)
    except proposals.Refused as e:
        return {"ok": False, "refused": str(e)}


@app.post("/v1/skills/propose")
def propose(body: ProposeIn) -> dict:
    return _door(proposals.propose, **body.model_dump())


@app.post("/v1/skills/patch")
def patch(body: PatchIn) -> dict:
    return _door(proposals.patch, **body.model_dump())


@app.get("/health")
def health() -> dict:
    e = eng()
    return {"ok": True, "model": e.version, "skills": len(e.skills)}
