"""Ordered providers of the selected model, media provider routes, service poste ids and the free-text entry.
Availability never authorises substituting a different text model.
"""
from __future__ import annotations

from walter_router.analysis import knowledge
from walter_router.serve import choose, execution, intent


def with_execution(conn, out: dict) -> dict:
    """Add the selected model's ordered providers; availability never authorises another model."""
    task = conn.execute("select interface, requirements, modes from models.tasks where task = %s", (out.get("task"),)).fetchone()
    modes = list((task or {}).get("modes") or []) + choose.INPUTS.get(out.get("require") or "", [])
    if out.get("model_id") and task and task["interface"] == "chat":
        background = (out.get("follows") or {}).get("task") == "general" and out.get("task") != "general"
        usage = "background" if background else "interactive"   # level postes (summaries, memory) may use flex hosts
        out["execution"] = execution.routes(conn, out["model_id"], out.get("variant") or "",
                                            preferred=out.get("provider"), usage=usage, modes=modes)
        # Report the effective first route, never the provider from an older ranking.
        out["provider"] = out["execution"][0]["provider"] if out["execution"] else None
        # Availability never authorises another model: try only this model's providers.
        effort = (task["requirements"] or {}).get("reasoning")
        if effort:   # a poste's own reasoning level (voice_assist: minimal, the latency comes first)
            out["execution"] = [{**r, "reasoning": r.get("reasoning") or effort} for r in out["execution"]]
    elif out.get("model_id") and task and task["interface"] in ("rerank", "transcription", "embedding"):
        from walter_router.serve import media_exec  # service postes: modules call OpenRouter with this id (stt, rerank)
        out["openrouter_id"] = media_exec.openrouter_id(conn, out["model_id"])
    elif out.get("model_id") and task and task["interface"] in ("video", "image", "audio", "music"):
        from walter_router.serve import media_exec  # media: provider order of the model (the fallback = its next provider; another model only when declared)
        cfg = media_exec._models().get(out["model_id"]) or {}
        mode = {"text_to_video": "t2v", "image_to_video": "i2v", "text_to_image": "t2i", "image_edit": "i2i"}.get(out["task"])
        out["providers"] = media_exec.choose_provider(conn, out["model_id"], task["interface"], None,
                                                      bool((cfg.get("kie") or {}).get(mode)),
                                                      media_exec.openrouter_id(conn, out["model_id"]))
        out["fallback_models"] = media_exec.fallback_models(conn, out["task"], out.get("role"), out["model_id"], mode)
        out["openrouter_id"] = media_exec.openrouter_id(conn, out["model_id"])   # modules calling OpenRouter (stt)
    return out

def route(conn, request: str, task: str | None = None, level: str | None = None, context: str | None = None) -> dict:
    """Free-text request -> intent by the decision model (task, video role, level, unrestricted) -> decision + routes.

    The decision model reads the request and, when given, `context` (one line on what earlier turns were about, so
    « fais la suite » is understood). It is not called when the caller already fixed everything it would decide: a
    task other than general and the video tasks (whose objective it picks), or general with its level. Without it
    (network, credits, contract error) the task must be given or defaults to 'general' + keywords."""
    if task and ((task != "general" and task not in intent.VIDEO_TASKS) or (task == "general" and level)):
        found = {"skipped": "task and level given by the caller"}
    else:
        try:
            found = intent.classify(conn, request, context=context)
        except Exception as exc:  # noqa: BLE001 — keywords fallback
            found = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    usable = None if ("error" in found or "skipped" in found) else found
    if not task:
        task = found.get("task") if (found.get("task_confidence") or 0) >= intent.MIN_CONFIDENCE else "general"
    if task == "general" and not level and found.get("level"):
        level = found["level"]
    out = with_execution(conn, knowledge.decide(conn, task, request, level, usable))
    return {**out, "intent": found}
