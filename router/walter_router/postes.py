"""Fiches de poste: which model fits a JOB (orchestrator, agent worker), not only a task.

Attributes, each on 0-100 (linear median -> leader of its board, like scoring.board_quality):
  intelligence  AA Intelligence Index (best reasoning level)
  agentic       Arena Agent board (real tool-using sessions)
  reliability   BridgeBench trustworthiness (hallucination resistance)
  speed         BridgeBench speed
  access        100 subscription (Codex), 60 Kie, 40 other paid, 20 OpenRouter only
Hard constraints: callable chat model, context window >= min_context when known. A model must have at least one
of agentic/reliability measured (the job is about tools). Weights per poste live in knowledge.json "postes".
"""
from __future__ import annotations

import re
from pathlib import Path

from . import knowledge, scoring
from . import select as sel

BOARDS = {"intelligence": ("aa_intelligence", "intelligence"), "agentic": ("arena", "agent"),
          "reliability": ("bridgebench", "trustworthiness"), "speed": ("bridgebench", "speed")}
HERMES_CONFIG = Path("/root/.hermes/config.yaml")


def _board(conn, snaps: dict, benchmark: str, task: str) -> dict[str, float]:
    sid = snaps.get(sel.BENCH_KIND[benchmark])
    rows = list(conn.execute("""select model_id, variant, score, score_unit, extra from models.benchmarks
                               where snapshot_id = %s and benchmark = %s and task = %s""", (sid, benchmark, task)))
    return {m: v["q"] for m, v in scoring.board_quality(rows).items()}


def _access(conn, snaps: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    ids = [snaps[k] for k in ("openrouter", "kie", "codex", "hermes_providers") if k in snaps]
    for r in conn.execute("""select model_id, provider, access from models.offers where snapshot_id = any(%s)
                             and interface = 'chat'""", (ids,)):
        v = 100 if r["access"] == "subscription" else 60 if r["provider"] == "kie" else \
            20 if r["provider"] == "openrouter" else 40
        out[r["model_id"]] = max(out.get(r["model_id"], 0), v)
    return out


def rank(conn, poste: str, limit: int = 8) -> list[dict]:
    cfg = knowledge.load()["postes"][poste]
    snaps = sel.latest_snapshots(conn)
    attrs = {name: _board(conn, snaps, *bt) for name, bt in BOARDS.items()}
    attrs["access"] = _access(conn, snaps)
    ctx = {r["model_id"]: r["context_length"] for r in conn.execute(
        "select model_id, context_length from models.canonical where context_length is not null")}
    out = []
    for mid in attrs["access"]:
        if not (mid in attrs["agentic"] or mid in attrs["reliability"]):
            continue
        if ctx.get(mid) and ctx[mid] < cfg.get("min_context", 0):
            continue
        got = {a: attrs[a][mid] for a in cfg["weights"] if mid in attrs[a]}
        w = sum(cfg["weights"][a] for a in got)
        if w < 0.6:  # less than 60 % of the job's criteria measured: not enough evidence
            continue
        score = sum(cfg["weights"][a] * got[a] for a in got) / w
        out.append({"model_id": mid, "score": round(score, 1), "attributes": {a: round(v, 1) for a, v in got.items()},
                    "coverage": round(w, 2), "context_length": ctx.get(mid)})
    return sorted(out, key=lambda x: -x["score"])[:limit]


def current_orchestrator() -> dict:
    """model.default / model.provider of the live Hermes config (read-only text parse)."""
    text = HERMES_CONFIG.read_text()
    block = re.search(r"^model:\n((?:[ \t]+.*\n)+)", text, re.M)
    vals = dict(re.findall(r"^[ \t]+(default|provider):[ \t]*(\S+)", block.group(1), re.M)) if block else {}
    return {"model": vals.get("default"), "provider": vals.get("provider")}
