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

On 2026-10-02 this gives L1 GPT-6 Luna max (38.1, 0.020 $), L2 GPT-6.1 Sol medium (47.8, 0.064 $), L3 Claude
Opus 5.5 high (53.6, 0.73 $) — the tiers the owner had reached by hand. The method proposes; the declared tiers
(knowledge.json "levels") stay until the owner adopts a proposal.
"""
from __future__ import annotations

QUALITY_FLOOR = 35.0
CEILING_BAND = 5.0
KNEE_DROP = 2.0


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


def compute(points: list[dict], floor: float = QUALITY_FLOOR, band: float = CEILING_BAND,
            knee_drop: float = KNEE_DROP) -> dict:
    f = frontier(points)
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
    return {"frontier": f, "L1": l1, "L2": l2, "L3": l3,
            "params": {"floor": floor, "ceiling_band": band, "knee_drop": knee_drop, "ceiling": ceiling}}
