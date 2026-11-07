"""The single evaluator — used by the nightly promotion, the curator's checks and the benchmark.

Truth = explicit labels (bench + judge; implicit labels train but never grade). Holdout = a deterministic slice of the
labelled messages (qid hash), never trained on. Metrics on messages that have at least one skill labelled 2:
  recall@k  a "2" skill is among the k shown (k = 5 and 15: what the policy can show)
  hit@1/@3  the first / three first are a "2" skill
"""
from __future__ import annotations

from . import registry
from .ranker import Corpus, Ranker, _idf, features, score

import numpy as np


def is_holdout(q: str) -> bool:
    return int(q[:8], 16) % 5 == 0  # 20 %, stable forever


def examples(cases_by_qid: dict[str, dict], holdout: bool | None, sources=("bench", "judge", "implicit", "miss")) -> list[dict]:
    lab = registry.labels(sources)
    out = []
    for q, labels in lab.items():
        c = cases_by_qid.get(q)
        if c is None or (holdout is not None and is_holdout(q) != holdout):
            continue
        out.append(c | {"labels": labels})
    return out


def measure(c: Corpus, r: Ranker, cases: list[dict], ks=(1, 3, 5, 15)) -> dict:
    idf = _idf(r)
    hits = {k: 0 for k in ks}
    n = 0
    for x in cases:
        good = {s for s, (v, _) in x["labels"].items() if v == 2 and s in c.pos}
        if not good:
            continue
        s = score(r, features(c, r, x["query"], x.get("ctx", ""), x.get("session_skills"), before=x.get("ts"),
                              exclude=x.get("id"), _idf_cache=idf))
        top = [c.names[i] for i in np.argsort(-s)[:max(ks)]]
        n += 1
        for k in ks:
            hits[k] += any(t in good for t in top[:k])
    return {f"at{k}": round(100 * v / n, 1) if n else 0.0 for k, v in hits.items()} | {"n": n}


def calibrate_confidence(c: Corpus, r: Ranker, cases: list[dict], k_small: int, k_max: int,
                         grid=(0.8, 0.85, 0.9, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98), min_share: float = 0.2) -> float | None:
    """Smallest p(top1) above which showing k_small cards keeps the recall of k_max (held-out), on ≥ min_share of
    messages. None if no threshold qualifies (the policy then always shows k_max)."""
    idf = _idf(r)
    rows = []
    for x in cases:
        good = {s for s, (v, _) in x["labels"].items() if v == 2 and s in c.pos}
        if not good:
            continue
        s = score(r, features(c, r, x["query"], x.get("ctx", ""), x.get("session_skills"), before=x.get("ts"),
                              exclude=x.get("id"), _idf_cache=idf))
        order = np.argsort(-s)
        top = [c.names[i] for i in order[:k_max]]
        rows.append((float(s[order[0]]), any(t in good for t in top[:k_small]), any(t in good for t in top)))
    for t in grid:
        sub = [x for x in rows if x[0] >= t]
        if rows and len(sub) / len(rows) >= min_share and sum(x[1] for x in sub) >= sum(x[2] for x in sub):
            return t
    return None
