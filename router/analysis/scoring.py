"""One quality score per task from several leaderboards (AA, Arena, Design Arena, BridgeBench...).

Leaderboards use incompatible scales (AA index 0-100, Elo ~1000-1800, BridgeBench 0-1000). Each board is put on
the same 0-100 scale, then boards are averaged with the task's weights:

1. Board -> 0-100: linear between the board's median model (0) and its leader (100), below median = 0.
   Linear keeps the meaning of the gaps (an Elo gap is a win probability, an index gap is an index gap) and,
   unlike a percentile, still separates the leaders, which is where the router chooses.
2. Reliability of a measure: Elo-type boards with votes/samples count v/(v+500) (a model with 300 votes weighs
   0.38, with 20 000 votes 0.98); a provisional BridgeBench row 0.5; otherwise 1.
3. Composite = (sum weight x reliability x q + K x 50) / (sum weight x reliability + K): a model measured on a single
   light board is pulled toward the middle instead of winning on thin evidence (K = 0.25).
4. the owner's own verdicts (models.feedback, last 180 days, this task or any): +/-3 points per net rating, capped
   at +/-9 — their experience moves a model, without erasing the benchmarks.

the owner's favourites and roles stay above this score: it ranks what they have not decided.
"""
from __future__ import annotations

from statistics import median

from walter_router.analysis import select as sel
from walter_router import instance

SHRINK_K = 0.25
FEEDBACK_POINTS = 3.0  # per net rating point from the owner on that task (capped at +/-3 -> +/-9 composite points)
VOTES_HALF = 500.0
BOARD_NAMES = {"aa_intelligence": "AA", "aa_eval": "AA", "aa_decision": "AA Decision", "aa_mm": "AA", "da_models": "Design Arena", "da_agents": "Design Arena",
               "arena": "Arena", "bridgebench": "BridgeBench", "aa_stt": "AA STT", "agentset": "Agentset", "mteb": "MTEB"}


def _reliability(row: dict) -> float:
    extra = row.get("extra") or {}
    if extra.get("provisional"):
        return 0.5
    votes = extra.get("votes") or extra.get("samples")
    if isinstance(votes, (int, float)) and votes > 0:
        return votes / (votes + VOTES_HALF)
    return 1.0


def board_quality(rows: list[dict]) -> dict[str, dict]:
    """Best row per model on one board, with its 0-100 quality and rank."""
    best: dict[str, dict] = {}
    for r in rows:
        if r["model_id"] not in best or r["score"] > best[r["model_id"]]["score"]:
            best[r["model_id"]] = r
    scores = [r["score"] for r in best.values()]
    if len(scores) < 2:
        return {m: {"row": r, "q": 50.0, "rank": 1, "of": 1} for m, r in best.items()}
    floor, top = median(scores), max(scores)
    span = (top - floor) or 1.0
    ordered = sorted(best, key=lambda m: -best[m]["score"])
    return {m: {"row": best[m], "q": max(0.0, min(100.0, 100 * (best[m]["score"] - floor) / span)),
                "rank": ordered.index(m) + 1, "of": len(ordered)} for m in best}


def composite(conn, task: str, snaps: dict | None = None) -> list[dict]:
    """Every model measured on at least one board of the task, best composite first."""
    snaps = snaps or sel.latest_snapshots(conn)
    acc: dict[str, dict] = {}
    for b in conn.execute("""select benchmark, bench_task, weight, is_primary from models.task_benchmarks
                             where task = %s and weight > 0 order by is_primary desc, weight desc""", (task,)).fetchall():
        sid = sel.board_snapshot(conn, snaps, b["benchmark"], b["bench_task"])
        if sid is None:
            continue
        rows = list(conn.execute("""select model_id, variant, display_name, score, score_unit, cost, cost_unit, extra
                                   from models.benchmarks
                                   where snapshot_id = %s and benchmark = %s and task = %s""",
                                 (sid, b["benchmark"], b["bench_task"])))
        if b["benchmark"] == "aa_decision":   # LLM reference rows would set the scale: rank decision models only
            rows = [r for r in rows if (r["extra"] or {}).get("kind") == "decisionModel"]
        name = f'{BOARD_NAMES.get(b["benchmark"], b["benchmark"])} {b["bench_task"]}'
        for model_id, v in board_quality(rows).items():
            rel = _reliability(v["row"])
            a = acc.setdefault(model_id, {"model_id": model_id, "wq": 0.0, "w": 0.0, "boards": {}})
            a["wq"] += b["weight"] * rel * v["q"]
            a["w"] += b["weight"] * rel
            extra = v["row"]["extra"] or {}
            a["boards"][name] = {"score": round(v["row"]["score"], 1), "unit": v["row"]["score_unit"],
                                 "q": round(v["q"], 1), "rank": v["rank"], "of": v["of"], "weight": b["weight"],
                                 "reliability": round(rel, 2), "variant": v["row"]["variant"],
                                 "primary": b["is_primary"],
                                 # the measure behind a "higher = better" score (WER %, latency ms) and the list price
                                 **{k: extra[k] for k in ("wer_pct", "latency_ms", "host") if extra.get(k) is not None},
                                 **({"list_price": v["row"]["cost"], "price_unit": v["row"]["cost_unit"]}
                                    if v["row"]["cost"] is not None else {})}
            if extra.get("latency_ms") is not None:
                a["latency_ms"] = min(a.get("latency_ms") or float("inf"), extra["latency_ms"])
    fb = {r["model_id"]: r["s"] for r in conn.execute(
        """select model_id, sum(rating) as s from models.feedback where (task = %s or task is null)
           and at > now() - interval '180 days' group by 1""", (task,))}
    req = (conn.execute("select requirements from models.tasks where task = %s", (task,)).fetchone() or {}).get(
        "requirements") or {}
    out = []
    for a in acc.values():
        # a poste whose primary quality is a hard need (voice_assist: speed) ranks only models measured on it
        if req.get("require_primary") and not any(b.get("primary") for b in a["boards"].values()):
            continue
        # a poste with a latency budget (rerank: voice recall, 0.7 s) never ranks a model measured slower than it
        if req.get("max_latency_s") and a.get("latency_ms") and a["latency_ms"] > 1000 * req["max_latency_s"]:
            continue
        score = (a["wq"] + SHRINK_K * 50) / (a["w"] + SHRINK_K)
        adj = FEEDBACK_POINTS * max(-3, min(3, fb.get(a["model_id"]) or 0))
        if adj:
            a["boards"][f"Retours de {instance.owner()}"] = {"adjustment": adj, "net_rating": fb[a["model_id"]]}
            score = max(0.0, min(100.0, score + adj))
        out.append({"model_id": a["model_id"], "composite": round(score, 2), "evidence_weight": round(a["w"], 2),
                    "boards": a["boards"]})
    return sorted(out, key=lambda x: -x["composite"])
