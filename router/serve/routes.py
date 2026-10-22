"""What Walter runs for a decision: the ordered execution routes of a chat model (subscription at its cost price\nwhile its quota lasts, Kie, OpenRouter on its imposed hosts, then the subscription model of the task and the\ndeclared tier fallback), the provider order of a media model, the OpenRouter id of a service poste — and the\nfree-text entry point (decision model intent -> decision -> routes)."""
from __future__ import annotations

from walter_router.analysis import knowledge
from walter_router.serve import execution, intent


def subscription_fallback(conn, task: str, exclude: str | None = None) -> dict | None:
    """Best model of the task (weighted composite) that the subscription (Codex) can run, with the reasoning level
    measured on the task's primary board."""
    from walter_router.analysis import scoring
    subs = {r["model_id"] for r in conn.execute("""select distinct o.model_id from models.offers o
                                                  join models.latest_snapshots s using (snapshot_id)
                                                  where o.access = 'subscription' and o.interface = 'chat'""")}
    for c in scoring.composite(conn, task):
        if c["model_id"] in subs and c["model_id"] != exclude:
            variants = [b["variant"] for b in c["boards"].values() if b.get("variant")]
            return {"model_id": c["model_id"], "variant": variants[0] if variants else "high",
                    "composite": c["composite"]}
    return None

def with_execution(conn, out: dict) -> dict:
    """Add the ordered Hermes routes to a chat decision (what the Hermes plugin runs, with fallbacks)."""
    task = conn.execute("select interface, requirements from models.tasks where task = %s", (out.get("task"),)).fetchone()
    if out.get("model_id") and task and task["interface"] == "chat":
        background = (out.get("follows") or {}).get("task") == "general" and out.get("task") != "general"
        usage = "background" if background else "interactive"   # level postes (summaries, memory) may use flex hosts
        out["execution"] = execution.routes(conn, out["model_id"], out.get("variant") or "",
                                            preferred=out.get("provider"), usage=usage)
        basis = (out.get("follows") or {}).get("task") or out["task"]   # a 'level' poste falls back like its tier
        if basis != "general" and not any(r["access"] == "subscription" for r in out["execution"]):
            sub = subscription_fallback(conn, out["task"], exclude=out["model_id"])
            if sub:  # best model of this task reachable through the subscription, after the paid routes
                out["execution"] += [{**r, "fallback_for": out["model_id"]}
                                     for r in execution.routes(conn, sub["model_id"], sub["variant"])]
        fallback = knowledge.level_fallback(basis, out.get("level") or out.get("role"))
        if fallback:  # declared tier fallback, after every route of the pinned model
            fb_model, _, fb_variant = fallback.partition("/")
            out["execution"] += [{**r, "fallback_for": out["model_id"]}
                                 for r in execution.routes(conn, fb_model, fb_variant)]
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

def route(conn, request: str, task: str | None = None, level: str | None = None) -> dict:
    """Free-text request -> Jev intent (task, video role, level, unrestricted) -> decision + execution routes.
    Without Jev (network/credits/contract error) the task must be given or defaults to 'general' + keywords."""
    try:
        jev = intent.classify(conn, request)
    except Exception as exc:  # noqa: BLE001 — keywords fallback
        jev = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    if not task:
        task = jev.get("task") if (jev.get("task_confidence") or 0) >= intent.MIN_CONFIDENCE else "general"
    if task == "general" and not level and jev.get("level"):
        level = jev["level"]
    out = with_execution(conn, knowledge.decide(conn, task, request, level, jev if "error" not in jev else None))
    return {**out, "intent": jev}
