"""What the owner's subscriptions give back each week (owner, 2026-11-16: « les rentabiliser au maximum en essayant de
prendre tous les tokens disponibles par semaine »).

For each plan, from its weekly meter (models.subscription_usage: the vendor's real %, read after agent turns and every
30 min by walter-router-quota) and ModelDial's measured quota (plan/modeldial.py, the same figures that price the
subscription routes): the share of the week used, the tokens and API value that share represents on the plan's
reference model, what is left before the reset, and the multiple of the plan's weekly price recovered. Past weeks
come from the same readings (the highest % of each weekly window = what that week used).

Reference model = the model W.Alter's text tiers run on that plan (Claude Opus 5.5, GPT-6.1 Sol), else the plan's
model with the largest API value: the meter is shared by every model of a plan, so the conversion is a reading on
one model, not a sum. A plan without a readable meter (Google AI Pro) is listed as not measured. Information only:
nothing here routes a call (execution reads the meters itself, serve/execution.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from walter_router.plan import subscriptions

MONTH_WEEKS = subscriptions.MONTH_WEEKS


def _tier_models() -> list[str]:
    from walter_router.analysis import knowledge
    levels = (knowledge.load().get("levels") or {}).get("general") or {}
    return [lv["pin"].split("/")[0] for k, lv in sorted(levels.items(), reverse=True)   # L3, L2, L1
            if isinstance(lv, dict) and "/" in (lv.get("pin") or "")]


SAME_WINDOW_S = 12 * 3600   # vendors report the reset time with up to an hour of drift between readings


def _windows(conn, sub_id: str, weeks: int) -> list[dict]:
    """Weekly windows of one plan, newest first: the highest % read in each. Readings whose reset times lie within
    SAME_WINDOW_S of each other belong to one window (the reported reset drifts from one reading to the next)."""
    rows = conn.execute(
        """select resets_at, used_percent, read_at from models.subscription_usage
           where sub_id = %s and window_name = 'weekly' and source <> 'calibration' and resets_at is not null
           and read_at > now() - make_interval(days => %s) order by resets_at""", (sub_id, 7 * (weeks + 1))).fetchall()
    out: list[dict] = []
    for r in rows:
        w = out[-1] if out and (r["resets_at"] - out[-1]["_last"]).total_seconds() < SAME_WINDOW_S else None
        if w is None:
            out.append({"resets_at": r["resets_at"], "used_percent": r["used_percent"], "read_at": r["read_at"],
                        "_last": r["resets_at"]})
            continue
        w["_last"] = r["resets_at"]
        if r["read_at"] >= w["read_at"]:     # the latest reading names the window's reset
            w.update(resets_at=r["resets_at"], read_at=r["read_at"])
        w["used_percent"] = max(w["used_percent"], r["used_percent"])
    return out[::-1][:weeks + 1]


def weekly(conn, weeks: int = 4) -> list[dict]:
    costs = {r["sub_id"]: (r["detail"] or {}).get("models") or {}
             for r in conn.execute("select sub_id, detail from models.latest_subscription_costs")}
    tier_models = _tier_models()
    now = datetime.now(timezone.utc)
    out = []
    for sub in subscriptions.load():
        if sub.get("retired"):
            continue
        models = costs.get(sub["id"]) or {}
        ref = next((m for m in tier_models if m in models), None) or \
            max(models, key=lambda m: models[m].get("api_value_month") or 0, default=None)
        cap = models.get(ref) or {}
        price = float(sub.get("price_usd_month") or 0)
        list_price = price or float(sub.get("list_price_usd_month") or 0)
        week_value = (cap.get("api_value_month") or 0) / MONTH_WEEKS or None
        week_tokens = (cap.get("tokens_month") or 0) / MONTH_WEEKS or None
        name = sub["plan"] if sub["plan"].startswith(sub["vendor"]) else f'{sub["vendor"]} {sub["plan"]}'
        row = {"id": sub["id"], "name": name, "price_usd_month": price,
               "price_usd_week": round(list_price / MONTH_WEEKS, 2), "free_offer": not price and bool(list_price),
               "reference_model": ref, "week_api_value_usd": week_value and round(week_value, 2),
               "week_tokens": week_tokens and round(week_tokens), "measured": False, "current": None, "past": []}
        for i, w in enumerate(_windows(conn, sub["id"], weeks)):
            pct = float(w["used_percent"])
            value = week_value and week_value * pct / 100
            item = {"resets_at": w["resets_at"].isoformat(), "used_percent": round(pct, 1),
                    "api_value_usd": value and round(value, 2),
                    "tokens": week_tokens and round(week_tokens * pct / 100),
                    "multiple": round(value / row["price_usd_week"], 1) if value and row["price_usd_week"] else None}
            if i == 0 and w["resets_at"] > now:
                left = max(0.0, 100 - pct)
                item.update(left_percent=round(left, 1), read_at=w["read_at"].isoformat(),
                            days_to_reset=round((w["resets_at"] - now).total_seconds() / 86400, 1),
                            tokens_left=week_tokens and round(week_tokens * left / 100),
                            api_value_left_usd=week_value and round(week_value * left / 100, 2))
                row["current"] = item
            else:
                row["past"].append(item)
        row["past"] = row["past"][:weeks]
        row["measured"] = bool(row["current"] or row["past"])
        out.append(row)
    return out


def summary(rows: list[dict]) -> dict:
    """The whole week across plans: API value used and left, price paid."""
    cur = [r["current"] for r in rows if r["current"]]
    return {"api_value_used_usd": round(sum(c["api_value_usd"] or 0 for c in cur), 2),
            "api_value_left_usd": round(sum(c.get("api_value_left_usd") or 0 for c in cur), 2),
            "price_usd_week": round(sum(r["price_usd_week"] for r in rows if r["price_usd_month"]), 2)}
