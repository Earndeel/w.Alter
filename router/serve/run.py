"""Do the job on the chosen model — one entry for every runtime (Hermes plugin, walter MCP, the command).

    spec ──▶ decision: the model named by the owner (named.py: exactly that, or why not) / a hard constraint / the
             request classified by the decision model (routes.route)
         ├─ text  ──▶ a native tool loop on the chosen model, through the model gateway's exact-route transport,
         │           providers in order, every attempt in models.exec_log
         └─ media ──▶ media_exec.generate (image, video, music, voice): costs money, on request only

Text execution is native to the router. Only providers of the selected model are tried; every switch is reported.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from walter_router.serve import choose, execution, media_exec, named, routes

ALLOWED_TOOLSETS = ("web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory")
# P1 (2026-10-27): a sub-agent works with Walter's capabilities by default, through the Tool Gateway; the root
# terminal and file writes are opt-in. WALTER_RUN_TOOLS=legacy restores the former default.
DEFAULT_TOOLSETS = ["walter-web", "skills", "memory"]
LEGACY_TOOLSETS = ["web", "walter-web", "file", "terminal"]
TOOLSET_TOOLS = {"web": ["walter_browse"], "walter-web": ["walter_browse"],
                 "memory": ["memory_context", "memory_search", "memory_events"],
                 "skills": ["skills_search", "skill_read"]}
TOOL_FAMILY_TOOLSETS = {"research": ["walter-web", "skills"], "weather": ["walter-web"]}  # mode "tool" tasks
MEDIA = ("image", "video", "music", "audio")


def default_toolsets() -> list[str]:
    return list(LEGACY_TOOLSETS if os.environ.get("WALTER_RUN_TOOLS") == "legacy" else DEFAULT_TOOLSETS)


def _memory(action: str, payload: dict) -> dict:
    """Walter Memory's Run Plane through its command (declared interface); never blocks the sub-agent."""
    try:
        cmd = ["walter-memory", "observations", "add"] if action == "observations-add" else ["walter-memory", "runs", action]
        out = subprocess.run(cmd, input=json.dumps(payload, default=str),
                             capture_output=True, text=True, timeout=60)
        return json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def _persist_observations(output: str, run_id: str | None, task_id: str | None, geo: dict | None) -> dict:
    """persist="observations": the answer's "observations" list becomes sourced observations of the run (Walter
    Memory validates each one: subject and source required, unknown stays unknown). The sub-agent holds no write tool."""
    text = output.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    try:
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except ValueError:
        return {"stored": 0, "errors": [{"error": "answer is not JSON"}]}
    items = data.get("observations") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {"stored": 0, "errors": [{"error": 'answer has no "observations" list'}]}
    return _memory("observations-add", {"run_id": run_id, "task_id": task_id, "geo": geo, "items": items}) or \
        {"stored": 0, "errors": [{"error": "walter-memory unavailable"}]}


def _child_context(spec: dict) -> dict:
    """walter-context's pack for a sub-agent, through its command (declared interface); {} when unavailable."""
    try:
        out = subprocess.run(["walter-context-child"], input=json.dumps(spec, default=str), capture_output=True,
                             text=True, timeout=45)
        return json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def _events(goal: str, context: str, result: dict, model: str | None, pack: dict | None = None) -> list[dict]:
    """The sub-agent's own trace in walter_logs' vocabulary (masked by Walter Memory at write)."""
    now = lambda t=None: datetime.fromtimestamp(t or time.time(), timezone.utc).isoformat()
    evs = [{"type": "system/context", "text": json.dumps(pack, ensure_ascii=False, default=str)[:20000]}] if pack else []
    evs.append({"type": "user/message", "text": goal + ("\n\nContext:\n" + context if context else "")})
    for i, t in enumerate(result.get("tools") or []):
        cid = f"call-{i}"
        evs.append({"type": "tool/call", "tool": t.get("name"), "call_id": cid, "at": now(t.get("at")),
                    "text": json.dumps(t.get("arguments"), ensure_ascii=False, default=str)[:20000]})
        evs.append({"type": "tool/result", "tool": t.get("name"), "call_id": cid, "at": now(t.get("at")),
                    "status": "ok" if t.get("ok") else "error",
                    "text": json.dumps(t.get("result"), ensure_ascii=False, default=str)[:20000]})
    if result.get("output"):
        evs.append({"type": "assistant/message", "text": result["output"], "model": model})
    else:
        evs.append({"type": "system/message", "text": f"run ended: {result.get('error')}"})
    stamp = now()
    for e in evs:
        e.setdefault("at", stamp)
    return evs


def decide(conn, spec: dict) -> dict:
    if spec.get("model"):
        return named.named(conn, spec["model"], spec.get("provider"), spec.get("task"))
    if spec.get("require"):
        return routes.with_execution(conn, choose.pick(conn, spec.get("task") or "general", spec.get("level"),
                                                       require=spec["require"]))
    return routes.route(conn, spec.get("request") or spec.get("goal") or "", spec.get("task"), spec.get("level"),
                        spec.get("conversation"))


def _text(conn, d: dict, spec: dict) -> dict:
    """The router alone owns failover. Preserve the conversation across providers of this model."""
    from walter_router.serve import text_agent

    started = time.monotonic()
    budget = max(60, min(int(spec.get("budget_seconds") or 900), 3600))
    deadline = started + budget
    toolsets = spec.get("toolsets") if spec.get("toolsets") is not None else default_toolsets()
    unknown = set(toolsets) - set(ALLOWED_TOOLSETS)
    if unknown:
        return {"ok": False, "error": "unsupported_toolsets", "toolsets": sorted(unknown)}
    if "vision" in toolsets:
        return {"ok": False, "error": "vision_toolset_requires_an_explicit_image_input"}
    max_turns = max(1, min(int(spec.get("max_turns") or 40), 120))
    # Defend against stale/cached decisions containing the former subscription/model fallback.
    candidates = [r for r in d.get("execution") or [] if not r.get("fallback_for")]
    attempts, notices = [], []
    state = {"index": 0, "route": None}

    def call(messages, tools, remaining):
        while state["index"] < len(candidates):
            route = candidates[state["index"]]
            available = deadline - time.monotonic()
            if available <= 0:
                raise RuntimeError("budget_exhausted")
            t0 = time.monotonic()
            entry = {"provider": route["provider"], "model": route["model"],
                     "usage": None, "cost_usd": None, "cost_status": "unknown"}
            try:
                # Keep time for this model's remaining providers when one endpoint hangs.
                attempt_timeout = available / (len(candidates) - state["index"])
                response = text_agent.complete(route, messages, tools, attempt_timeout)
                entry.update(ok=True, response_id=response.get("response_id"),
                             response_model=response.get("response_model"), usage=response.get("usage"),
                             cost_usd=response.get("cost_usd"), cost_status=response.get("cost_status") or "unknown")
            except (RuntimeError, OSError, ValueError, KeyError) as exc:
                entry.update(ok=False, error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
                response = None
            entry["seconds"] = round(time.monotonic() - t0, 2)
            attempts.append(entry)
            execution.log(conn, {"task": d.get("task"), "role": d.get("role"), "model_id": d.get("model_id"),
                                 "provider": route["provider"], "model": route["model"],
                                 "ok": entry["ok"], "seconds": entry["seconds"], "usage": entry["usage"],
                                 "cost_usd": entry["cost_usd"], "cost_status": entry["cost_status"]})
            conn.commit()
            if response is not None:
                state["route"] = route
                return response
            state["index"] += 1
            if state["index"] < len(candidates):
                nxt = candidates[state["index"]]
                notice = {"type": "provider_fallback", "model": d["model_id"],
                          "from_provider": route["provider"], "to_provider": nxt["provider"],
                          "reason": entry["error"],
                          "message": f"{route['provider']} n'a pas répondu correctement pour {d['model_id']}. "
                                     f"Basculement vers {nxt['provider']}, avec le même modèle."}
                notices.append(notice)
        raise RuntimeError("all_providers_failed")

    # Walter Run Plane: inside a run, this execution is a task with its own walter_logs session.
    run_id = os.environ.get("WALTER_RUN_ID")
    task_id = session_id = None
    if run_id:
        task_id = str(uuid.uuid4())
        session_id = f"walter-router/{task_id}"
        os.environ["WALTER_TASK_ID"] = task_id          # read by execution.log and passed to the Tool Gateway
        _memory("task-start", {"run_id": run_id, "task_id": task_id, "kind": "walter_run", "goal": spec["goal"],
                               "session_id": session_id,
                               "spec": {k: spec.get(k) for k in ("task", "level", "max_turns", "budget_seconds",
                                                                 "constraints", "output_schema", "persist")} |
                                       {"toolsets": list(toolsets), "requested_task": d.get("requested_task")}})
    # P2-b: the sub-agent gets a pack built for its task by walter-context (context.build scope=child), the caller's
    # context kept verbatim inside it; WALTER_RUN_CONTEXT=caller restores the caller's string alone.
    context, pack_summary = spec.get("context") or "", None
    if os.environ.get("WALTER_RUN_CONTEXT", "walter") != "caller":
        pack = _child_context({"goal": spec["goal"], "toolsets": list(toolsets), "caller_context": context,
                               "constraints": spec.get("constraints"), "output_schema": spec.get("output_schema"),
                               "budget": {"seconds": budget, "turns": max_turns}, "run_id": run_id, "task_id": task_id})
        if pack.get("text"):
            context, pack_summary = pack["text"], pack.get("summary")
            reused = [ref for b in (pack_summary or {}).get("blocks") or [] if b.get("id") == "observations"
                      for ref in b.get("sources") or []]
            if run_id and reused:                       # provenance: what the run relied on without re-reading
                _memory("link", {"run_id": run_id, "kind": "observation_reused", "refs": reused})
    walter_tools = sorted({t for ts in toolsets for t in TOOLSET_TOOLS.get(ts, [])})
    gateway = None
    try:
        if walter_tools:
            gateway = text_agent.Gateway(walter_tools)
        result = text_agent.run(spec["goal"], context, list(toolsets), max_turns, deadline, call, gateway=gateway)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        result = {"ok": False, "error": str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__}
    finally:
        if gateway:
            gateway.close()
    route = state["route"]
    persisted = None
    if spec.get("persist") == "observations" and result.get("ok"):
        persisted = _persist_observations(result.get("output") or "", run_id, task_id,
                                          (spec.get("constraints") or {}).get("geo"))
        result = {**result, "persisted": persisted}
    if run_id:
        _memory("task-end", {"run_id": run_id, "task_id": task_id, "session_id": session_id, "goal": spec["goal"],
                             "parent_session_id": os.environ.get("WALTER_SESSION_ID"),
                             "model": route["model"] if route else None,
                             "events": _events(spec["goal"], context, result, route["model"] if route else None,
                                               pack_summary),
                             "status": "ended" if result.get("ok") else "failed",
                             "routing": {"task": d.get("requested_task") or d.get("task"), "executed_as": d.get("task"),
                                         "model_id": d.get("model_id"), "provider": route["provider"] if route else None,
                                         "applied": True},
                             "result": {"ok": result.get("ok"), "error": result.get("error"),
                                        "persisted": {k: (persisted or {}).get(k) for k in ("stored", "skipped", "errors")}
                                        if persisted else None,
                                        "tools": len(result.get("tools") or []),
                                        "seconds": round(time.monotonic() - started, 1)}})
    user_notice = "\n".join(n["message"] for n in notices)
    if not result["ok"]:
        failure = (f"Aucun fournisseur n'a pu exécuter {d['model_id']}. Aucun autre modèle n'a été utilisé."
                   if result.get("error") == "all_providers_failed" else
                   f"L'exécution de {d['model_id']} a échoué : {result.get('error')}.")
        user_notice = "\n".join(filter(None, (user_notice, failure)))
    return {**result, "kind": "text", "runtime": "walter-router", "notices": notices, "run_id": run_id,
            "task_id": task_id, "trace_session": session_id,
            "user_notification_required": bool(user_notice), "user_notice": user_notice,
            "routed": {"task": d.get("task"), "model_id": d.get("model_id"),
                       "model": route["model"] if route else None,
                       "provider": route["provider"] if route else None,
                       "reasoning": route.get("reasoning") if route else None,
                       "named": d.get("named"), "attempts": attempts,
                       "seconds": round(time.monotonic() - started, 2)}}


def _run(conn, spec: dict) -> dict[str, Any]:
    if not (spec.get("goal") or spec.get("request")):
        return {"ok": False, "error": "goal (text) or request (media) required"}
    d = decide(conn, spec)
    if d.get("mode") == "none" or d.get("error"):
        return {"ok": False, "error": d.get("error") or d.get("why") or "no model", "decision": d}
    if d.get("mode") == "tool" and spec.get("goal"):
        # A task answered by a tool (research, weather…): a sub-agent on the general tier holding that tool.
        family = d.get("tool") or d.get("task")
        spec = {**spec, "toolsets": spec["toolsets"] if spec.get("toolsets") is not None
                else TOOL_FAMILY_TOOLSETS.get(family, default_toolsets())}
        d = {**decide(conn, {**spec, "task": "general", "level": spec.get("level") or "L2"}), "requested_task": family}
        if d.get("mode") == "none" or d.get("error"):
            return {"ok": False, "error": d.get("error") or "no model", "decision": d}
    t = conn.execute("select interface from models.tasks where task = %s", (d.get("task"),)).fetchone()
    if t and t["interface"] in MEDIA:
        is_named = d.get("source") == "named"
        if is_named and d["task"] == "text_to_video" and spec.get("image_urls") and not spec.get("task"):
            d["task"] = "image_to_video"
        out = media_exec.generate(conn, spec.get("request") or spec["goal"], task=d["task"], role=spec.get("role"),
                                  image_urls=spec.get("image_urls"), aspect_ratio=spec.get("aspect_ratio"),
                                  duration=spec.get("duration"), resolution=spec.get("resolution"),
                                  paid_fallback=bool(spec.get("paid_fallback")),
                                  model=d["model_id"] if is_named else None,
                                  provider=d.get("provider") if is_named else None, _fallback=not is_named)
        return {"ok": bool(out.get("files")) or out.get("mode") == "manual_ui", "kind": "media", **out}
    if not d.get("execution"):
        return {"ok": False, "error": f"no execution route for task {d.get('task')}", "decision": d}
    if not spec.get("goal"):
        return {"ok": False, "error": "goal required: complete instructions for the sub-agent (it does not see the conversation)"}
    return _text(conn, d, spec)


def run(conn, spec: dict) -> dict[str, Any]:
    """Versioned result; existing fields remain compatible with every current adapter."""
    return {"schema_version": 1, **_run(conn, spec)}
