"""Do the job on the chosen model — one entry for every runtime (Hermes plugin, walter MCP, the command).

    spec ──▶ decision: the model named by the owner (named.py: exactly that, or why not) / a hard constraint / the
             request classified by the decision model (routes.route)
         ├─ text  ──▶ a native tool loop on the chosen model, through the model gateway's exact-route transport,
         │           providers in order, every attempt in models.exec_log
         └─ media ──▶ media_exec.generate (image, video, music, voice): costs money, on request only

Text execution is native to the router. Only providers of the selected model are tried; every switch is reported.
"""
from __future__ import annotations

import time
from typing import Any

from walter_router.serve import choose, execution, media_exec, named, routes

ALLOWED_TOOLSETS = ("web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory")
DEFAULT_TOOLSETS = ["web", "walter-web", "file", "terminal"]
MEDIA = ("image", "video", "music", "audio")


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
    toolsets = spec.get("toolsets") if spec.get("toolsets") is not None else DEFAULT_TOOLSETS
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
            entry = {"provider": route["provider"], "model": route["model"]}
            try:
                # Keep time for this model's remaining providers when one endpoint hangs.
                attempt_timeout = available / (len(candidates) - state["index"])
                response = text_agent.complete(route, messages, tools, attempt_timeout)
                entry.update(ok=True, response_id=response.get("response_id"),
                             response_model=response.get("response_model"))
            except (RuntimeError, OSError, ValueError, KeyError) as exc:
                entry.update(ok=False, error=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__)
                response = None
            entry["seconds"] = round(time.monotonic() - t0, 2)
            attempts.append(entry)
            execution.log(conn, {"task": d.get("task"), "role": d.get("role"), "model_id": d.get("model_id"),
                                 "provider": route["provider"], "model": route["model"],
                                 "ok": entry["ok"], "seconds": entry["seconds"]})
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

    try:
        result = text_agent.run(spec["goal"], spec.get("context") or "", list(toolsets), max_turns, deadline, call)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        result = {"ok": False, "error": str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__}
    route = state["route"]
    user_notice = "\n".join(n["message"] for n in notices)
    if not result["ok"]:
        failure = (f"Aucun fournisseur n'a pu exécuter {d['model_id']}. Aucun autre modèle n'a été utilisé."
                   if result.get("error") == "all_providers_failed" else
                   f"L'exécution de {d['model_id']} a échoué : {result.get('error')}.")
        user_notice = "\n".join(filter(None, (user_notice, failure)))
    return {**result, "kind": "text", "runtime": "walter-router", "notices": notices,
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
