"""What the router (and the orchestrator) calls: pick the model for a task, Monsieur's preferences first."""
from __future__ import annotations

from typing import Any

from . import select as sel

LEVELS = ("L1", "L2", "L3")


def latest_run(conn) -> int | None:
    row = conn.execute("select run_id from models.latest_run").fetchone()
    return row["run_id"] if row else None


def routes_for(conn, model_id: str, interface: str) -> dict[str, Any]:
    """Every current route for one model: subscription first, then paid routes cheapest first."""
    snaps = sel.latest_snapshots(conn)
    offers = sel.load_offers(conn, snaps).get(model_id, [])
    return sel.chat_route(offers, None) if interface == "chat" else sel.media_route(offers, interface)


def pick(conn, task: str, level: str | None = None) -> dict[str, Any]:
    t = conn.execute("select * from models.tasks where task = %s", (task,)).fetchone()
    if not t:
        raise KeyError(f"unknown task: {task}")
    if t["default_objective"] == "tool":
        return {"task": task, "mode": "tool", "tool": task, "why": t["description"]}
    pref = conn.execute("select * from models.preferences where task = %s", (task,)).fetchone()
    if pref and pref["pinned_model_id"]:
        route = routes_for(conn, pref["pinned_model_id"], t["interface"])
        return {"task": task, "mode": "delegate", "source": "preference_pinned", "model_id": pref["pinned_model_id"],
                "variant": pref["pinned_variant"], "provider": pref["pinned_provider"] or (route.get("subscription")
                or (route.get("paid") or {}).get("provider")), "route": route, "why": pref["note"]}
    if t["quality_benchmark"] is None:
        snaps = sel.latest_snapshots(conn)
        ids = [snaps[k] for k in ("openrouter", "kie", "codex") if k in snaps]
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
                    "real_cost": row["real_cost"], "cost_unit": row["cost_unit"], "run_id": run_id}
    return {"task": task, "mode": "none", "why": "no callable candidate in the latest run"}


def set_preference(conn, task: str, objective: str | None = None, pin: str | None = None,
                   provider: str | None = None, note: str | None = None) -> dict:
    """Record Monsieur's declaration. Pinning records every model already better as 'baseline' (no alert for those)."""
    model_id, variant = (pin.split("/", 1) + [""])[:2] if pin else (None, "")
    if model_id:
        conn.execute("insert into models.canonical (model_id) values (%s) on conflict do nothing", (model_id,))
    conn.execute("""insert into models.preferences (task, objective, pinned_model_id, pinned_variant, pinned_provider, note, declared_at)
                    values (%s, %s, %s, %s, %s, %s, now())
                    on conflict (task) do update set objective = coalesce(excluded.objective, models.preferences.objective),
                      pinned_model_id = excluded.pinned_model_id, pinned_variant = excluded.pinned_variant,
                      pinned_provider = excluded.pinned_provider,
                      note = coalesce(excluded.note, models.preferences.note), declared_at = now()""",
                 (task, objective, model_id, variant, provider, note))
    from . import alerts
    baseline = alerts.challengers(conn, status_for_new="baseline", only_task=task) if model_id else []
    return {"task": task, "objective": objective, "pinned": pin, "baseline_challengers": len(baseline)}
