"""Decision models on three axes (Monsieur, 2026-10-16): intelligence (AA Decision Index, higher), speed (median
time per task, lower) and price (AA cost per 1M tasks, lower; real price = the Decisions-API offer per M input
tokens, 0 for the free routes we use). A model is Pareto-optimal when no other model is at least as good on all three
and strictly better on one. Used by the notification of a new decision model and by the library page.
"""
from __future__ import annotations

from . import select as sel

FREE = {"mercury-decide": "OpenRouter :free", "clef": "Workers AI (allocation gratuite)",
        "clef-flash": "Workers AI (allocation gratuite)"}


def points(conn, modes: list[str] | None = None) -> list[dict]:
    snaps = sel.latest_snapshots(conn)
    sid = snaps.get("aa_decision")
    if not sid:
        return []
    offers = sel.load_offers(conn, snaps)
    need = set(modes or [])
    out = []
    for b in conn.execute("""select model_id, display_name, max(score) as score, max(cost) as cost,
                                    max((extra->>'time_per_task_ms')::float) as ms
                             from models.benchmarks where snapshot_id = %s and benchmark = 'aa_decision'
                               and extra->>'kind' = 'decisionModel' group by 1, 2""", (sid,)):
        dec = [o for o in offers.get(b["model_id"], []) if o["interface"] == "decisions" and o.get("price_in_1m") is not None]
        if need and not any(need <= set(o.get("modes") or []) for o in dec):
            continue
        out.append({"model_id": b["model_id"], "name": b["display_name"], "index": b["score"], "ms": b["ms"],
                    "cost": b["cost"], "price_in_1m": min((o["price_in_1m"] for o in dec), default=None),
                    "callable": bool(dec), "free": FREE.get(b["model_id"]),
                    "images": any("image" in (o.get("modes") or []) for o in dec)})
    return out


def dominates(a: dict, b: dict) -> bool:
    ge = a["index"] >= b["index"] and a["ms"] <= b["ms"] and a["cost"] <= b["cost"]
    gt = a["index"] > b["index"] or a["ms"] < b["ms"] or a["cost"] < b["cost"]
    return ge and gt


def frontier(pts: list[dict]) -> list[dict]:
    pts = [p for p in pts if p["index"] is not None and p["ms"] is not None and p["cost"] is not None]
    return sorted((p for p in pts if not any(dominates(q, p) for q in pts if q is not p)),
                  key=lambda p: -p["index"])


def verdict(new: dict, current: dict | None, pts: list[dict]) -> dict:
    """Where a newcomer stands: on the frontier?, models it dominates, models dominating it, the frontier itself."""
    f = frontier(pts)
    return {"on_frontier": any(p["model_id"] == new["model_id"] for p in f),
            "dominates": [p for p in pts if dominates(new, p)],
            "dominated_by": [p for p in pts if dominates(p, new)],
            "beats_current_all": bool(current) and dominates(new, current),
            "frontier": f,
            "fastest": min(f, key=lambda p: p["ms"]) if f else None,
            "cheapest": min(f, key=lambda p: p["cost"]) if f else None}
