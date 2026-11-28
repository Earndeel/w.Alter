"""The owner's method for the three functional text tiers (declared 2026-10-02).

Input: every callable model x reasoning level with its AA Intelligence score and its real cost per AA task
(AA list cost x cheapest-provider / list price ratio). Steps:

1. Strict Pareto frontier: sorted by cost, keep a point only if it scores higher than every cheaper point.
2. Marginal gain of each frontier point = extra points per extra dollar from the previous frontier point.
3. L1 "économique" = the first frontier point at or above the quality floor (35 AA) that is a knee — the next
   step's marginal gain is at most half of its own (beyond it, intelligence gets clearly dearer).
4. L3 "haut de gamme" = among frontier points within 5 points of the best score (the ceiling band), the one with
   the best marginal gain counted from L2 — i.e. the cheapest way to reach top quality.
5. L2 "intermédiaire" = between L1 and L3, the point with the best marginal gain counted from L1.
   (L2 is computed before L3 is finalised: candidates are the frontier points strictly between L1 and the
   ceiling band.)
   Since 2026-11-16 steps 3-5 use the affordable frontier only: from the first point above the floor that buys less
   than CEILING_MIN_GAIN point per extra dollar, points are luxury (shown, never a tier, never the ceiling).
6. Owner's subscription rule (2026-11-16, quota_levels, applied in select._tier_rows): the subscriptions are already
   paid, so L2/L3 are first sought among the models they serve, at their ModelDial cost price — L3 = the method's
   L3 on that pool, L2 = the best model of ANOTHER subscription costing less per task than L3 (the two tiers then
   spread over two quotas), else the best cheaper one of L3's own. Only ever raises a tier; each carries its pick
   once its subscription is spent, which execution switches to instead of paying the API price.
7. Owner's hold rule (2026-11-20, hold_price, applied in select._tier_rows): once a tier is declared, L1 and L2 keep
   about its price — a proposal costs at most HOLD_BAND more per task than the declared tier and scores at least
   HOLD_MIN_GAIN more, both read in the same index snapshot; nothing better at that price = the declared tier stays.
   No tier is ever proposed below the declared tier's current score (L3 keeps the method, with that floor).

On 2026-10-02 this gives L1 GPT-6 Luna max (38.1, 0.020 $), L2 GPT-6.1 Sol medium (47.8, 0.064 $), L3 Claude
Opus 5.5 high (53.6, 0.73 $) — the tiers the owner had reached by hand. The method proposes; the declared tiers
(knowledge.json "levels") stay until the owner adopts a proposal.
"""
from __future__ import annotations

QUALITY_FLOOR = 35.0
CEILING_BAND = 5.0
KNEE_DROP = 2.0
# 2026-11-16 (owner): a frontier point that buys less than 1 AA point per extra dollar is luxury — it neither sets the
# ceiling nor competes for a tier. Fable 5.2 max (64.6 at 26.5 $/task) had set the band at 59.6, so Opus 5.5 max
# (59.1 at 0.17 $) missed it by 0.5 point and L3 went to Gemini 4 Carbon (60.0 at 3.10 $).
CEILING_MIN_GAIN = 1.0
# 2026-11-20 (owner): « le L1 doit rester plus ou moins le même prix, mais évidemment jamais descendre en score.
# pareil pour L2 ». The knee / best-gain rules had proposed Terra medium (38.2) under the declared 6.2 Sol low (40.6).
HOLD_BAND = 0.25
HOLD_MIN_GAIN = 0.5


def frontier(points: list[dict]) -> list[dict]:
    """points: {'model_id', 'variant', 'score', 'cost', ...}; strict Pareto frontier with 'marginal' filled."""
    pts = sorted((p for p in points if p.get("cost") and p["cost"] > 0), key=lambda p: (p["cost"], -p["score"]))
    out: list[dict] = []
    for p in pts:
        if not out or p["score"] > out[-1]["score"]:
            prev = out[-1] if out else None
            marginal = (p["score"] - prev["score"]) / (p["cost"] - prev["cost"]) if prev and p["cost"] > prev["cost"] \
                else None
            out.append({**p, "marginal": marginal})
    return out


def _gain(a: dict, b: dict) -> float:
    """Points per extra dollar going from a to b."""
    return (b["score"] - a["score"]) / (b["cost"] - a["cost"]) if b["cost"] > a["cost"] else float("inf")


def affordable(f: list[dict], floor: float = QUALITY_FLOOR, min_gain: float = CEILING_MIN_GAIN) -> list[dict]:
    """The frontier up to its first point above the floor that buys less than `min_gain` points per extra dollar."""
    for i, p in enumerate(f):
        if i and p["score"] >= floor and p["marginal"] is not None and p["marginal"] < min_gain:
            return f[:i]
    return f


def compute(points: list[dict], floor: float = QUALITY_FLOOR, band: float = CEILING_BAND,
            knee_drop: float = KNEE_DROP, min_gain: float = CEILING_MIN_GAIN) -> dict:
    full = frontier(points)
    f = affordable(full, floor, min_gain)
    luxury = full[len(f):]
    if len(f) < 3:
        return {"frontier": f, "L1": None, "L2": None, "L3": None}
    above = [i for i, p in enumerate(f) if p["score"] >= floor]
    if not above:
        return {"frontier": f, "L1": None, "L2": None, "L3": None}
    l1_i = above[0]
    for i in above:
        nxt = f[i + 1]["marginal"] if i + 1 < len(f) else None
        own = f[i]["marginal"]
        if own and nxt is not None and nxt <= own / knee_drop:
            l1_i = i
            break
    ceiling = max(p["score"] for p in f)
    band_i = [i for i, p in enumerate(f) if p["score"] >= ceiling - band and i > l1_i]
    mid_i = [i for i in range(l1_i + 1, len(f)) if i not in band_i]
    l1 = f[l1_i]
    l2 = max((f[i] for i in mid_i), key=lambda p: _gain(l1, p), default=None)
    base = l2 or l1
    l3 = max((f[i] for i in band_i), key=lambda p: _gain(base, p), default=None)
    return {"frontier": f + luxury, "L1": l1, "L2": l2, "L3": l3,
            "params": {"floor": floor, "ceiling_band": band, "knee_drop": knee_drop, "ceiling": ceiling,
                       "ceiling_min_gain": min_gain, "luxury": [f'{p["model_id"]}/{p["variant"]}' for p in luxury]}}


def hold_price(points: list[dict], anchor: dict, band: float = HOLD_BAND, min_gain: float = HOLD_MIN_GAIN,
               allow=lambda p: True) -> dict | None:
    """The declared tier's successor at about its price: the best-scoring point costing at most (1 + band) x the
    anchor's cost per task and scoring at least `min_gain` above it (tie: the cheaper). None = keep the anchor."""
    if not anchor.get("cost") or anchor.get("score") is None:
        return None
    cap = anchor["cost"] * (1 + band)
    better = [p for p in points if p.get("cost") and p["cost"] <= cap and p.get("score") is not None
              and p["score"] >= anchor["score"] + min_gain and allow(p)]
    return max(better, key=lambda p: (p["score"], -p["cost"]), default=None)


def _best(ps) -> dict | None:
    return max(ps, key=lambda p: (p["score"], -(p.get("cost") or 0)), default=None)


def quota_levels(points: list[dict], in_pool, sub_of=lambda p: None) -> dict:
    """The owner's subscription rule (2026-11-16): the subscriptions are already paid, so L2 and L3 are sought among
    the models they serve, at their cost price. L3 = the method's L3 on that pool (Opus 5.5 xhigh, not max: +1.7 points
    for 66 % more quota per task); L2 = the best model of another subscription than L3's that costs less per task than
    L3 (GPT-6.1 Sol xhigh on ChatGPT Plus while L3 runs on Claude Pro: two quotas instead of one), else the best
    cheaper model of L3's own subscription. `in_pool(point)`: the point's cost is a subscription's; `sub_of(point)`:
    which one. L1 keeps the method (its volume would drain any quota)."""
    pool = [p for p in points if in_pool(p) and p.get("score") is not None and p.get("cost")]
    l3 = compute(pool)["L3"] if pool else None
    if not l3:
        return {"L2": None, "L3": None}
    below = [p for p in pool if p["cost"] < l3["cost"] and p["score"] < l3["score"]]
    return {"L2": _best(p for p in below if sub_of(p) != sub_of(l3)) or _best(below), "L3": l3}


def above(points: list[dict], in_pool, base: dict) -> dict | None:
    """The subscription model above `base` (the tier just below) with the best gain from it — L3's pick once its own
    subscription is spent, so that L3 never falls to L2's level (Claude spent: Sol max above L2's Sol xhigh)."""
    return max((p for p in points if in_pool(p) and p.get("cost") and p["score"] > base["score"]),
               key=lambda p: _gain(base, p), default=None)
