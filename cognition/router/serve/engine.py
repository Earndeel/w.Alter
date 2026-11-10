"""walter_run text jobs executed by Walter Engine (lot E5, 2026-11-10) — no second agent loop in the Router.

The Router keeps what it owns: the decision (which task / model), media and web paths, the Run Plane task record and
persisted observations. The loop itself — tools, permissions, interruption, resumption — is the engine's: one
`delegate` call to the Engine API (core/interfaces/api, op `delegate`) opens an unattended `mcp/<caller>/task-…`
session under the `api` preset (reads allowed, anything that would need the owner refused), its run filed under the
caller's run. The binding is the instance's (`host.json` → `engine_api`):

    "engine_api": {"url": "http://127.0.0.1:8895", "token_file": "@instance/bootstrap/engine/api.token",
                   "walter_run": "engine" | "legacy"}

A model named by the owner goes to the engine too (validated here by named.py, executed exactly by walter-llm through
the run's plan); a model the engine cannot run is an explicit error, never the former loop. `legacy` (default while E2/E3 are not active on the live engine) keeps the former text loop (text_agent).
WALTER_RUN_ENGINE / WALTER_ENGINE_API_URL / WALTER_ENGINE_API_TOKEN_FILE override it for a test engine.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

ENGINE_TASKS = ("coding", "general", "document", "summarization")   # engine models = walter-llm postes
TASK_OF = {"code": "coding", "front": "coding"}                      # router task → engine poste when names differ


def binding() -> dict:
    from walter_router import instance
    try:
        b = dict(instance.host().get("engine_api") or {})
    except (OSError, ValueError, RuntimeError):
        b = {}
    for key, env in (("walter_run", "WALTER_RUN_ENGINE"), ("url", "WALTER_ENGINE_API_URL"),
                     ("token_file", "WALTER_ENGINE_API_TOKEN_FILE")):
        if os.environ.get(env):
            b[key] = os.environ[env]
    return b


def enabled(d: dict) -> bool:
    """Text jobs go to the engine when the instance says so — a model NAMED by the owner too: the Router validated it
    (named.py), the engine runs it exactly (the run's plan names it, walter-llm executes only that model)."""
    return binding().get("walter_run") == "engine"


def _token(b: dict) -> str:
    from walter_router import instance
    return instance._expand(b.get("token_file") or "@instance/bootstrap/engine/api.token").read_text().strip()


def _post(b: dict, body: dict, timeout: float) -> tuple[int, dict]:
    req = urllib.request.Request((b.get("url") or "http://127.0.0.1:8895").rstrip("/") + "/v1",
                                 data=json.dumps({"version": 1, **body}).encode(),
                                 headers={"Authorization": "Bearer " + _token(b), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {"error": f"http_{e.code}"}


def engine_task(d: dict, spec: dict) -> str:
    t = TASK_OF.get(d.get("task") or "", d.get("task") or "")
    return t if t in ENGINE_TASKS else "auto"


def run_text(d: dict, spec: dict, *, memory, persist, caller: str = "walter_run") -> dict:
    """One delegation to the engine; the result has the shape of the former text path (ok, output, tools…)."""
    b = binding()
    started = time.monotonic()
    budget = max(60, min(int(spec.get("budget_seconds") or 900), 3600))
    run_id = os.environ.get("WALTER_RUN_ID")
    task_id = str(uuid.uuid4())
    key = str(spec.get("idempotency_key") or task_id)
    task = engine_task(d, spec)
    if run_id:
        memory("task-start", {"run_id": run_id, "task_id": task_id, "kind": "walter_run", "goal": spec["goal"],
                              "spec": {k: spec.get(k) for k in ("task", "level", "budget_seconds", "constraints",
                                                                "output_schema", "persist")}
                              | {"executor": "walter-engine", "engine_task": task,
                                 "requested_task": d.get("requested_task")}})
    named = {"id": d["model_id"], **({"provider": spec["provider"]} if spec.get("provider") else {})} \
        if d.get("source") == "named" and d.get("model_id") else None
    delegation = {"version": 1, "goal": spec["goal"], "context": spec.get("context") or "", "task": task,
                  **({"model": named} if named else {}),
                  "budget_seconds": budget, "idempotency_key": key,
                  "output_contract": spec.get("output_schema"), "constraints": spec.get("constraints"),
                  "parent": {"run_id": run_id, "session_id": os.environ.get("WALTER_SESSION_ID"), "task_id": task_id,
                             "depth": int(os.environ.get("WALTER_DELEGATION_DEPTH") or 0)}}
    try:
        status, out = _post(b, {"op": "delegate", "delegation": delegation, "caller": caller}, timeout=budget + 60)
    except (OSError, ValueError) as exc:          # engine down, token missing: said, never a silent second loop
        status, out = 0, {"error": "engine_unavailable", "detail": type(exc).__name__}
    if status != 200:
        result = {"ok": False, "error": out.get("error") or f"http_{status}", "detail": out.get("message") or out.get("detail")}
    else:
        r = out.get("result") or out
        result = {"ok": bool(r.get("ok")), "output": r.get("output") or "",
                  "error": None if r.get("ok") else (r.get("reason") or r.get("status") or "no_answer"),
                  "tools": [{"name": t} for t in r.get("tools") or []], "engine": {
                      k: r.get(k) for k in ("status", "reason", "session_id", "walter_session", "request_id", "resumed")}}
    persisted = None
    if spec.get("persist") == "observations" and result.get("ok"):
        persisted = persist(result.get("output") or "", run_id, task_id, (spec.get("constraints") or {}).get("geo"))
        result["persisted"] = persisted
    walter_session = (result.get("engine") or {}).get("walter_session")
    seconds = round(time.monotonic() - started, 1)
    if run_id:
        if walter_session:   # the engine session's own trace is already in walter_logs (runtime dsh)
            memory("link", {"run_id": run_id, "kind": "session", "refs": [walter_session]})
        memory("task-end", {"run_id": run_id, "task_id": task_id, "session_id": walter_session or f"walter-engine/{task_id}",
                            "goal": spec["goal"], "events": [],
                            "status": "ended" if result.get("ok") else ("cancelled" if (result.get("engine") or {}).get("status") == "cancelled" else "failed"),
                            "routing": {"task": d.get("requested_task") or d.get("task"), "executed_as": task,
                                        "model_id": named["id"] if named else None, "provider": "walter-engine",
                                        "applied": True},
                            "result": {"ok": result.get("ok"), "error": result.get("error"),
                                       "persisted": {k: (persisted or {}).get(k) for k in ("stored", "skipped", "errors")}
                                       if persisted else None,
                                       "tools": len(result.get("tools") or []), "seconds": seconds}})
    notice = "" if result.get("ok") else (
        "Le moteur Walter est indisponible ; la tâche n'a pas été exécutée." if result.get("error") == "engine_unavailable"
        else f"La tâche déléguée au moteur Walter n'a pas abouti : {result.get('error')}.")
    return {**result, "kind": "text", "runtime": "walter-engine", "notices": [], "run_id": run_id, "task_id": task_id,
            "trace_session": walter_session, "user_notification_required": bool(notice), "user_notice": notice,
            "routed": {"task": d.get("task"), "engine_task": task, "executor": "walter-engine",
                       "named": d.get("named"), "seconds": seconds}}
