#!/usr/bin/env python3
"""Recall quality bench through the real read paths (gateway :8890), not the library internals.

  walter-python bench/recall_bench.py --bench-dir DIR [--path recall|context] [--show 3] [--out results.json]

DIR holds queries.json (list of questions) and gold_hindsight.json ({question: [{"text": ...}, ...]}); the bench data
is personal and stays outside this repository. Metric (same as the retired voice bench, so scores stay comparable):
hit@3 = one of the first 3 returned memories shares >= 60 % of its words with the gold top-1 memory.
Optional answers.json ({question: regex}) adds answer@3 = one of the first 3 memories matches the expected answer
(the Hindsight gold is itself sometimes wrong or off-topic; this second score judges the answer, not the wording).
--path recall  = agent_memory.recall (Hermes provider, MCP memory_recall)
--path context = /v1/context knowledge section (Claude Code / Codex hook, MCP memory_context)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walter_memory import client  # noqa: E402




def words(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", text.lower()))


def sim(a: str, b: str) -> float:
    a, b = words(a), words(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def via_recall(query: str) -> list[str]:
    out = client.call("recall", {"query": query, "budget": "low", "max_tokens": 1024, "structured": True},
                      caller="walter-bench", timeout=15)
    return [r.get("text") or "" for r in out.get("records") or []]


def via_context(query: str) -> list[str]:
    req = urllib.request.Request("http://127.0.0.1:8890/v1/context", method="POST",
                                 data=json.dumps({"query": query, "include_profile": False, "caller": "walter-bench",
                                                  "budget": {"evidence": 0, "people": 0}}).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + client.token()})
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read())
    know = (res.get("sections") or {}).get("knowledge") or ""
    return [re.sub(r"^- ", "", l) for l in know.splitlines() if l.startswith("- ")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench-dir", required=True, type=Path)
    ap.add_argument("--path", choices=("recall", "context"), default="recall")
    ap.add_argument("--show", type=int, default=1)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    queries = json.loads((a.bench_dir / "queries.json").read_text())
    gold = json.loads((a.bench_dir / "gold_hindsight.json").read_text())
    keys = json.loads((a.bench_dir / "answers.json").read_text()) if (a.bench_dir / "answers.json").exists() else {}
    fn = via_recall if a.path == "recall" else via_context
    fn(queries[0])  # warm-up (embedding model, pool)
    lat, hits, answers, rows = [], 0, 0, []
    for q in queries:
        t = time.monotonic()
        try:
            got = fn(q)
        except Exception as e:  # a failing call is a miss, not a crash
            got = []
            print("ERR", q, type(e).__name__)
        lat.append((time.monotonic() - t) * 1000)
        g = gold[q][0]["text"] if gold.get(q) else ""
        hit = bool(g) and any(sim(g, x) >= 0.6 for x in got[:3])
        ans = bool(keys.get(q)) and any(re.search(keys[q], x) for x in got[:3])
        hits += hit
        answers += ans
        rows.append({"q": q, "hit": hit, "answer": ans, "top": got[:max(3, a.show)], "ms": round(lat[-1])})
    p90 = sorted(lat)[int(0.9 * len(lat))]
    print(f"[{a.path}] hit@3 {hits}/{len(queries)} ; answer@3 {answers}/{len(queries)} ; latence médiane {statistics.median(lat):.0f} ms, p90 {p90:.0f} ms")
    for r in rows:
        print("OK " if r["hit"] else "XX ", "A " if r["answer"] else "- ", r["q"], f"({r['ms']} ms)")
        for x in r["top"][:a.show]:
            print("     →", x.replace("\n", " ")[:140])
    if a.out:
        a.out.write_text(json.dumps({"path": a.path, "hits": hits, "answers": answers, "n": len(queries), "median_ms": statistics.median(lat),
                                     "p90_ms": p90, "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
