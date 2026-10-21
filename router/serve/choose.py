"""What the router (and the orchestrator) calls: pick the model for a task, the owner's preferences first."""
from __future__ import annotations

from typing import Any

from walter_router.analysis import parse
from walter_router.analysis import select as sel
from walter_router import instance

LEVELS = ("L1", "L2", "L3")
# Effective content policy = the owner's profile override, else the detected one. 'permissive' models (reputedly
# lenient, unverified) answer an unrestricted request only after every truly unrestricted one, flagged.
POLICY = "coalesce(pr.content_policy, c.content_policy)"
REQUIREMENTS = {"unrestricted": f"{POLICY} in ('unrestricted', 'permissive')", "open_weights": "c.open_weights"}


def latest_run(conn) -> int | None:
    row = conn.execute("select run_id from models.latest_run").fetchone()
    return row["run_id"] if row else None


def routes_for(conn, model_id: str, interface: str, modes: list[str] | None = None) -> dict[str, Any]:
    """Every current route for one model: subscription first, then paid routes cheapest first."""
    snaps = sel.latest_snapshots(conn)
    offers = sel.load_offers(conn, snaps).get(model_id, [])
    return sel.chat_route(offers, None) if interface == "chat" else sel.media_route(offers, interface, modes)


def _pinned_answer(conn, task: dict, pref: dict) -> dict[str, Any]:
    route = routes_for(conn, pref["pinned_model_id"], task["interface"], task["modes"])
    provider = pref["pinned_provider"] or route.get("subscription") or (route.get("paid") or {}).get("provider") \
        or route.get("ui")
    mode = "manual_ui" if provider and provider == route.get("ui") else "delegate"
    return {"task": task["task"], "role": pref["role"], "level": pref["role"] if pref["role"] in LEVELS else None,
            "mode": mode, "source": "preference_pinned",
            "model_id": pref["pinned_model_id"], "variant": pref["pinned_variant"], "provider": provider,
            "route": route, "why": pref["note"]}


def _best_score(conn, snaps: dict, boards: list[dict], model_id: str) -> tuple[float | None, str | None]:
    """Score on the first board of the task that measures the model (primary first): boards are never mixed,
    an AA index and an Arena Elo are not comparable."""
    for b in boards:
        sid = snaps.get(sel.BENCH_KIND[b["benchmark"]])
        row = conn.execute("""select max(score) as s from models.benchmarks where snapshot_id = %s and benchmark = %s
                              and task = %s and model_id = %s""", (sid, b["benchmark"], b["bench_task"], model_id)).fetchone()
        if row and row["s"] is not None:
            return row["s"], f'{b["benchmark"]}:{b["bench_task"]}'
    return None, None


def pick_required(conn, t: dict, require: str, limit: int = 5) -> dict[str, Any]:
    """Best callable model satisfying a hard constraint (unrestricted / open weights) for a task.

    Quality = the model's own score on the task's boards (primary first); an unrestricted fine-tune that no
    leaderboard measures inherits its base model's score, flagged `score_from_base`."""
    if require not in REQUIREMENTS:
        raise KeyError(f"unknown requirement {require}; known: {sorted(REQUIREMENTS)}")
    snaps = sel.latest_snapshots(conn)
    offers = sel.load_offers(conn, snaps)
    boards = conn.execute("""select benchmark, bench_task from models.task_benchmarks where task = %s
                             order by is_primary desc, benchmark""", (t["task"],)).fetchall()
    ids = [snaps[k] for k in parse.OFFER_KINDS if k in snaps]
    cands = []
    for c in conn.execute(f"""select distinct c.model_id, coalesce(c.display_name, c.model_id) as name, c.base_model_id,
                                     c.license, {POLICY} as content_policy, c.open_weights
                              from models.offers o join models.canonical c using (model_id)
                              left join models.profiles pr on pr.model_id = c.model_id
                              where o.snapshot_id = any(%s) and o.interface = %s and {REQUIREMENTS[require]}""",
                          (ids, t["interface"])):
        route = sel.chat_route(offers[c["model_id"]], None) if t["interface"] == "chat" else \
            sel.media_route(offers[c["model_id"]], t["interface"], t["modes"])
        if not route["callable"]:
            continue
        score, board = _best_score(conn, snaps, boards, c["model_id"])
        from_base = None
        if score is None and c["base_model_id"]:
            score, board = _best_score(conn, snaps, boards, c["base_model_id"])
            from_base = c["base_model_id"] if score is not None else None
        paid = route.get("paid") or {}
        cands.append({"model_id": c["model_id"], "display_name": c["name"], "score": score, "board": board,
                      "score_from_base": from_base, "license": c["license"], "content_policy": c["content_policy"],
                      "provider": route.get("subscription") or paid.get("provider") or route.get("ui"),
                      "offer_key": paid.get("offer_key"), "cost": paid.get("cost"),
                      "price_1m_blended": paid.get("blended_1m")})
    order = [f'{b["benchmark"]}:{b["bench_task"]}' for b in boards]
    cands.sort(key=lambda x: (require == "unrestricted" and x["content_policy"] == "permissive",
                              order.index(x["board"]) if x["board"] in order else len(order), -(x["score"] or 0),
                              x["price_1m_blended"] or x["cost"] or 0))
    for x in cands:
        if require == "unrestricted" and x["content_policy"] == "permissive":
            x["warning"] = f"réputé permissif (déclaration de {instance.owner()}), pas garanti sans restriction"
    if not cands:
        return {"task": t["task"], "mode": "none", "require": require,
                "why": f"aucun modèle {require} appelable pour {t['interface']} chez les providers connus"}
    return {"task": t["task"], "mode": "delegate", "source": f"required:{require}", "require": require, **cands[0],
            "alternatives": cands[1:limit]}


def pick(conn, task: str, level: str | None = None, role: str | None = None,
         require: str | None = None) -> dict[str, Any]:
    """The owner's favourite for (task, role) first; otherwise the computed choice for the task's objective.

    Without a role, the 'default' favourite is used and the other roles are listed so the orchestrator can
    switch on intent (e.g. an action scene -> role 'action').
    """
    t = conn.execute("select * from models.tasks where task = %s", (task,)).fetchone()
    if not t:
        raise KeyError(f"unknown task: {task}")
    if t["default_objective"] == "tool":
        return {"task": task, "mode": "tool", "tool": task, "why": t["description"]}
    if require:
        return pick_required(conn, t, require)
    prefs = {p["role"]: p for p in conn.execute("select * from models.preferences where task = %s", (task,))}
    if role and role not in prefs:
        raise KeyError(f"no preference role '{role}' for {task}; known: {sorted(prefs)}")
    if task == "general" and not role and (level or "L1") in prefs:
        role = level or "L1"  # the owner's declared text tiers (knowledge.json "levels")
    pref = prefs.get(role or "default")
    others = {r: {"model_id": p["pinned_model_id"], "note": p["note"]} for r, p in prefs.items()
              if r != (role or "default") and p["pinned_model_id"]}
    if pref and pref["pinned_model_id"]:
        return {**_pinned_answer(conn, t, pref), "other_roles": others}
    if t["default_objective"] == "level":
        return _level_answer(conn, t, level)
    if t["quality_benchmark"] is None:
        snaps = sel.latest_snapshots(conn)
        ids = [snaps[k] for k in parse.OFFER_KINDS if k in snaps]
        offers = conn.execute("""select provider, offer_key, model_id, unit_price, unit from models.offers
                                 where snapshot_id = any(%s) and interface = %s order by provider, offer_key""",
                              (ids, t["interface"])).fetchall()
        return {"task": task, "mode": "offers_only", "why": "aucun classement mesuré pour cette tâche", "offers": offers}
    run_id = latest_run(conn)
    if run_id is None:
        raise RuntimeError("no successful refresh yet")
    objective = (pref and pref["objective"]) or t["default_objective"]
    if task == "general":
        wanted = [level or "L1"]
    else:
        wanted = ["best"] if objective == "best_available" else ["value", "best"]
    for lvl in wanted:
        row = conn.execute("""select * from models.selection where run_id = %s and task = %s and level = %s and rank = 1""",
                           (run_id, task, lvl)).fetchone()
        if row:
            return {"task": task, "mode": "delegate", "source": "preference_objective" if pref else "default_objective",
                    "objective": objective, "level": lvl, "model_id": row["model_id"], "variant": row["variant"],
                    "display_name": row["display_name"], "quality": row["quality"], "quality_unit": row["quality_unit"],
                    "provider": row["subscription"] or row["provider"], "paid_fallback": row["provider"],
                    "real_cost": row["real_cost"], "cost_unit": row["cost_unit"], "run_id": run_id, "other_roles": others}
    return {"task": task, "mode": "none", "why": "no callable candidate in the latest run", "other_roles": others}


def _level_answer(conn, t: dict, level: str | None = None) -> dict[str, Any]:
    """A background text poste (compression, extraction…) follows one of the owner's text tiers — their declared pin for
    'general' at requirements.level, adopted by them, so the poste moves when they adopt a new tier. A tier model that
    breaks a hard requirement of the poste (context window) hands over to the next tier up."""
    req = t.get("requirements") or {}
    want = level or req.get("level") or "L1"
    for lvl in LEVELS[LEVELS.index(want):]:
        d = pick(conn, "general", level=lvl)
        if not d.get("model_id"):
            continue
        ctx = conn.execute("select context_length from models.canonical where model_id = %s", (d["model_id"],)).fetchone()
        if req.get("min_context") and ctx and ctx["context_length"] and ctx["context_length"] < req["min_context"]:
            continue
        return {**d, "task": t["task"], "level": lvl, "follows": {"task": "general", "level": lvl},
                "source": f'level:{lvl}' + (f' ({d["source"]})' if d.get("source") else ""), "requirements": req,
                "why": f'Poste de fond : niveau texte {lvl} de {instance.owner()} (general/{lvl}). ' + (d.get("why") or "")}
    return {"task": t["task"], "mode": "none", "why": f"aucun niveau texte {want}+ ne respecte {req}"}


def set_preference(conn, task: str, objective: str | None = None, pin: str | None = None, provider: str | None = None,
                   note: str | None = None, role: str = "default", watch: str | None = None) -> dict:
    """Record the owner's declaration. Pinning records every current challenger as 'baseline' (no alert for those)."""
    model_id, variant = (pin.split("/", 1) + [""])[:2] if pin else (None, "")
    if model_id:
        conn.execute("insert into models.canonical (model_id) values (%s) on conflict do nothing", (model_id,))
    conn.execute("""insert into models.preferences (task, role, objective, pinned_model_id, pinned_variant, pinned_provider,
                      note, watch, declared_at)
                    values (%s, %s, %s, %s, %s, %s, %s, coalesce(%s, 'quality'), now())
                    on conflict (task, role) do update set objective = coalesce(excluded.objective, models.preferences.objective),
                      pinned_model_id = excluded.pinned_model_id, pinned_variant = excluded.pinned_variant,
                      pinned_provider = excluded.pinned_provider, watch = coalesce(%s, models.preferences.watch),
                      note = coalesce(excluded.note, models.preferences.note), declared_at = now()""",
                 (task, role, objective, model_id, variant, provider, note, watch, watch))
    from walter_router.analysis import alerts
    baseline = alerts.challengers(conn, status_for_new="baseline", only_task=task, only_role=role) if model_id else []
    return {"task": task, "role": role, "objective": objective, "pinned": pin, "watch": watch,
            "baseline_challengers": len(baseline)}
