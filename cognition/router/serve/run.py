"""Do the job on the chosen model — one entry for every runtime (Hermes plugin, walter MCP, the command).

    spec ──▶ decision: the model named by the owner (named.py: exactly that, or why not) / a hard constraint / the
             request classified by the decision model (routes.route)
         ├─ text  ──▶ Walter Engine (engine.py, Engine API `delegate`): the only agent loop (VISION § 9, SOCLE A6).
         │           A model named by the owner included (executed exactly, or an explicit error). Without the engine
         │           binding, or when the Engine API cannot be reached, the job fails with `engine_unavailable`:
         │           the Router has no second loop any more (its former `text_agent` loop was removed 2026-11-11).
         ├─ web   ──▶ a conversational web service when the owner's rule says so (one exchange, not a loop)
         └─ media ──▶ media_exec.generate (image, video, music, voice): costs money, on request only
"""
from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from walter_router.serve import choose, execution, media_exec, named, routes

# Accepted values of walter_run's `toolsets` (public schema, serve/api.py); the engine holds the tools themselves.
ALLOWED_TOOLSETS = ("web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory")
# P1 (2026-10-27): a sub-agent works with Walter's capabilities (web, skills, memory).
DEFAULT_TOOLSETS = ["walter-web", "skills", "memory"]
TOOL_FAMILY_TOOLSETS = {"research": ["walter-web", "skills"], "weather": ["walter-web"]}  # mode "tool" tasks
MEDIA = ("image", "video", "music", "audio")


def default_toolsets() -> list[str]:
    return list(DEFAULT_TOOLSETS)


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


def decide(conn, spec: dict) -> dict:
    if spec.get("model"):
        return named.named(conn, spec["model"], spec.get("provider"), spec.get("task"))
    if spec.get("require"):
        return routes.with_execution(conn, choose.pick(conn, spec.get("task") or "general", spec.get("level"),
                                                       require=spec["require"]))
    return routes.route(conn, spec.get("request") or spec.get("goal") or "", spec.get("task"), spec.get("level"),
                        spec.get("conversation"))


def _web(conn, d: dict, spec: dict) -> dict[str, Any]:
    """The owner's rule gave this intent to a web chat service: the user's own words go there (the request, else the
    goal), in the rule's conversation; the reply comes back verbatim. The result has the text run's shape."""
    from walter_router.serve import web
    w = d["web"]
    message = (spec.get("request") or spec.get("goal") or "").strip()
    if spec.get("conversation"):
        message = f"{message}\n\n(Contexte : {str(spec['conversation'])[:600]})"
    started = time.monotonic()
    out = web.converse({"service": w["service"], "message": message, "conversation": w["conversation"],
                        "timeout_s": min(int(spec.get("budget_seconds") or 300), 600)})
    seconds = round(time.monotonic() - started, 2)
    execution.log(conn, {"task": d.get("task"), "role": d.get("role"), "model_id": None, "provider": f"web:{w['service']}",
                         "model": "web", "ok": bool(out.get("ok")), "seconds": seconds, "usage": None,
                         "cost_usd": None, "cost_status": "unknown", "kind": "web"})
    conn.commit()
    return {"ok": bool(out.get("ok")), "output": out.get("reply") or "", "files": out.get("files") or [],
            "error": out.get("error") or (None if out.get("ok") else out.get("status")), "kind": "web",
            "runtime": "walter-router", "notices": [], "user_notification_required": False, "user_notice": "",
            "routed": {"task": d.get("task"), "provider": f"web:{w['service']}", "service": w["service"],
                       "conversation": out.get("conversation"), "request_id": out.get("request_id"),
                       "why": w.get("why"), "level": (d.get("intent") or {}).get("level"), "seconds": seconds,
                       "timings": out.get("timings")}}


def _run(conn, spec: dict) -> dict[str, Any]:
    if not (spec.get("goal") or spec.get("request")):
        return {"ok": False, "error": "goal (text) or request (media) required"}
    d = decide(conn, spec)
    if d.get("mode") == "none" or d.get("error"):
        return {"ok": False, "error": d.get("error") or d.get("why") or "no model", "decision": d}
    web_notice = None
    if d.get("mode") == "web":
        out = _web(conn, d, spec)
        if out["ok"]:
            return out
        # the owner's fallback rule: the usual path for this intent, said to the user
        web_notice = {"type": "web_fallback", "service": d["web"]["service"], "reason": out.get("error"),
                      "message": f"Le service web {d['web']['service']} n'a pas pu répondre ({out.get('error')}). "
                                 "Réponse par la voie habituelle du routeur."}
        d = {**d, "mode": d["web"].get("fallback_mode")}
        if not spec.get("goal"):
            spec = {**spec, "goal": spec["request"]}
    result = _dispatch(conn, d, spec)
    if web_notice:
        result["notices"] = [web_notice, *(result.get("notices") or [])]
        result["user_notice"] = "\n".join(filter(None, (web_notice["message"], result.get("user_notice"))))
        result["user_notification_required"] = True
    return result


def _dispatch(conn, d: dict, spec: dict) -> dict[str, Any]:
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
    from walter_router.serve import engine
    if engine.enabled(d):   # lot E5: the loop is Walter Engine's; the Router decided and keeps the task record
        return engine.run_text(d, spec, memory=_memory, persist=_persist_observations)
    return engine.unavailable(d, "engine_not_bound")   # SOCLE A6: never a second loop in the Router


def run(conn, spec: dict) -> dict[str, Any]:
    """Versioned result; existing fields remain compatible with every current adapter."""
    return {"schema_version": 1, **_run(conn, spec)}
