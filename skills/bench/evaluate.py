"""Skill-retrieval benchmark: baselines (today's mechanisms) and, later, walter-skills retrievers.

Metrics per case: hit@1 (top-1 is a gold skill), hit@3 / hit@10 (any gold in the top k), MRR of the first gold.
Corpora: `full` = active + archived skills (gold = skill actually opened), `active` = today's Hermes library
(gold mapped through the curator's absorbed_into chain). Query modes: `q` = user message only, `ctx` = message +
previous user/assistant turn (what a hook sees).

Usage: python evaluate.py [--split all|dev|test] [--only name,...] [--json out.json]
LLM baselines are added from data/llm_<name>.jsonl when present (see hermes_llm.py).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, "/opt/walter-memory")

DATA = Path(__file__).parent / "data"
TRUNC = 57  # Hermes skill index: descriptions cut to 57 chars + "..."


def load():
    cases = [json.loads(line) for line in open(DATA / "cases.jsonl")]
    corpus = [json.loads(line) for line in open(DATA / "corpus.jsonl")]
    return cases, corpus


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


STOP = set("""le la les un une des de du d l et ou a au aux en dans sur pour par avec sans ce cet cette ces je tu il elle
on nous vous ils elles me te se mon ma mes ton ta tes son sa ses que qui quoi est sont pas ne plus mais donc car si
the a an of to in on for with and or is are be it this that you i we what how do does can use when""".split())


def tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", fold(s)) if len(t) > 1 and t not in STOP]


def hermes_desc(d: str) -> str:
    return d if len(d) <= TRUNC + 3 else d[:TRUNC] + "..."


def query_text(c: dict, mode: str) -> str:
    if mode == "q":
        return c["query"]
    ctx = c.get("context") or {}
    return f"{ctx.get('prev_user', '')}\n{ctx.get('prev_assistant', '')[-300:]}\n{c['query']}"


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.2, b: float = 0.75):
        self.toks = [tokens(d) for d in docs]
        self.tf = [Counter(t) for t in self.toks]
        self.len = np.array([len(t) for t in self.toks], dtype=float)
        self.avg = self.len.mean() or 1
        df = Counter(w for t in self.toks for w in set(t))
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.k1, self.b = k1, b

    def scores(self, q: str) -> np.ndarray:
        out = np.zeros(len(self.toks))
        for w in set(tokens(q)):
            idf = self.idf.get(w)
            if not idf:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(w)
                if f:
                    out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        return out


def mcp_keyword_scores(q: str, corpus: list[dict]) -> np.ndarray:
    """walter-core skills_search as of 2026-10-09 (substring counts on name/description/tags)."""
    words = [w for w in q.lower().split() if w]
    out = np.zeros(len(corpus))
    for i, s in enumerate(corpus):
        hay = f"{s['name']} {s['description']} {s['tags']}".lower()
        out[i] = sum(hay.count(w) + 3 * (w in s["name"].lower()) for w in words)
    return out


def rrf(*rankings: np.ndarray, k: int = 60) -> np.ndarray:
    out = np.zeros(len(rankings[0]))
    for scores in rankings:
        order = np.argsort(-scores)
        for r, i in enumerate(order):
            out[i] += 1 / (k + r + 1)
    return out


def metrics(ranked: list[str], gold: list[str]) -> dict:
    gold = set(gold)
    rank = next((i + 1 for i, n in enumerate(ranked) if n in gold), None)
    return {"hit1": float(rank == 1), "hit3": float(bool(rank and rank <= 3)),
            "hit10": float(bool(rank and rank <= 10)), "mrr": 1 / rank if rank else 0.0}


def summarize(rows: list[dict]) -> dict:
    n = len(rows) or 1
    return {k: round(100 * sum(r[k] for r in rows) / n, 1) for k in ("hit1", "hit3", "hit10", "mrr")} | {"n": len(rows)}


def build_retrievers(corpus: list[dict]):
    from walter_memory.search import embed

    names = [s["name"] for s in corpus]
    idx_text = [f"{s['name']} {s['category']} {hermes_desc(s['description'])}" for s in corpus]
    full_text = [f"{s['name']} {s['description']} {s['tags']} {s['body'][:4000]}" for s in corpus]
    bm_idx, bm_full = BM25(idx_text), BM25(full_text)
    t0 = time.time()
    e_desc = embed([f"{s['name'].replace('-', ' ')}: {s['description']}" for s in corpus])
    e_body = embed([f"{s['name'].replace('-', ' ')}: {s['description']}\n{s['body'][:2000]}" for s in corpus])
    print(f"corpus embedded in {time.time() - t0:.1f}s", file=sys.stderr)

    def emb(mat):
        return lambda q: mat @ embed([q])[0]

    return names, {
        "mcp_keyword": lambda q: mcp_keyword_scores(q, corpus),
        "bm25_hermes_index": bm_idx.scores,
        "bm25_full": bm_full.scores,
        "potion_desc": emb(e_desc),
        "potion_body": emb(e_body),
        "hybrid_bm25_potion": lambda q: rrf(bm_full.scores(q), e_body @ embed([q])[0]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--ids-from", default="", help="restrict to the case ids of this jsonl (e.g. an LLM sample)")
    a = ap.parse_args()
    cases, corpus_all = load()
    if a.ids_from:
        ids = {json.loads(line)["id"] for line in open(a.ids_from)}
        cases = [c for c in cases if c["id"] in ids]
    if a.split != "all":
        cases = [c for c in cases if c["split"] == a.split]
    only = set(filter(None, a.only.split(",")))
    results = {}
    for corpus_name, corpus, gold_key in (("full", corpus_all, "gold"),
                                          ("active", [s for s in corpus_all if not s["archived"]], "gold_active")):
        names, retr = build_retrievers(corpus)
        sub = [c for c in cases if c[gold_key]]
        for rname, fn in retr.items():
            if only and rname not in only:
                continue
            for mode in ("q", "ctx"):
                rows, lat = [], []
                for c in sub:
                    t0 = time.perf_counter()
                    s = fn(query_text(c, mode))
                    lat.append(time.perf_counter() - t0)
                    top = [names[i] for i in np.argsort(-s)[:10] if s[i] > 0]
                    rows.append(metrics(top, c[gold_key]))
                key = f"{corpus_name}/{rname}/{mode}"
                results[key] = summarize(rows) | {"p50_ms": round(1000 * float(np.median(lat)), 1)}
                print(key, results[key], flush=True)
        for f in sorted(DATA.glob(f"llm_{corpus_name}_*.jsonl")):  # LLM baselines on a sample
            got = {r["id"]: r for r in map(json.loads, open(f))}
            rows = [metrics(got[c["id"]]["ranked"], c[gold_key]) for c in sub if c["id"] in got]
            lat = [got[c["id"]]["latency_ms"] for c in sub if c["id"] in got]
            key = f"{corpus_name}/{f.stem[len('llm_' + corpus_name) + 1:]}"
            results[key] = summarize(rows) | {"p50_ms": float(np.median(lat)) if lat else None}
            print(key, results[key], flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
