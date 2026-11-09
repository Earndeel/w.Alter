#!/usr/bin/env python3
"""g0 vs g1 benchmark (lot D of the 2026-11-09 mandate): what each memory read policy puts in Walter's context.

  walter-python bench/g0_g1.py [--sets post,pre] [--policies today,g1,g0] [--judge] [--no-rerank] [--out FILE]

Read-only, nothing is switched: each policy is simulated by overriding the read set cache for one call
(generations._cache), exactly as generations.preview does. Same read path as production (context.get_context, cloud
rerank on unless --no-rerank, profile off so the profile cannot answer for memory).

Question sets (personal data: they live in the instance, `walter instance path state memory`/bench/g0_g1/, never here):
  post  questions whose answers were learnt after the V1 start (2026-11-02) — bench/g1_recall.py QUESTIONS
  pre   pre-V1 questions (voice bench of 2026-10-01): pre.json = [{"q": ..., "answer": regex}] — what « g1 only »
        would lose
Policies: today = the live read set (g0+g1), g1 = g1 alone (after a switch), g0 = g0 alone (what g1 adds),
g1_first = g1 then g0 to fill (a candidate policy; only when generations.read_policy exposes it).

Metrics per policy: hit (the expected answer is in the injected context), judged answer quality (--judge: can the
context answer the question? yes/partial/no, --samples draws averaged, Walter Router poste memory_extraction,
verdicts cached per exact (question, context, draw) so a rerun of an identical context is judged identically), diversity of the injected lines
(every section: distinct memories among them, near-duplicates = >= 60 % shared words), generation mix, tokens, latency, cost
(system.model_calls since the start). Prints aggregates only; the output file holds questions and scores, no memory
content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

JUDGE_PROMPT = """Question posée à la mémoire d'un assistant personnel : {q}

Contexte que la mémoire a fourni à l'assistant :
{ctx}

Ce contexte permet-il de répondre correctement et précisément à la question ? Réponds en JSON :
{{"verdict": "yes" | "partial" | "no"}}"""


def words(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", text.lower()))


def near(a: set[str], b: set[str]) -> bool:
    return len(a & b) / max(1, min(len(a), len(b))) >= 0.6


def distinct(lines: list[str]) -> int:
    """Greedy clusters of near-duplicate lines (paraphrases of one memory count once)."""
    reps: list[set[str]] = []
    for w in (words(l) for l in lines):
        if not any(near(w, r) for r in reps):
            reps.append(w)
    return len(reps)


def bench_dir() -> Path:
    if os.environ.get("WALTER_BENCH_DIR"):
        return Path(os.environ["WALTER_BENCH_DIR"])
    p = subprocess.run(["walter", "instance", "path", "state", "memory"], capture_output=True, text=True,
                       timeout=10).stdout.strip()
    if not p:
        sys.exit("instance state path unknown: set WALTER_BENCH_DIR")
    return Path(p) / "bench" / "g0_g1"


def load_sets(names: list[str], d: Path) -> list[dict]:
    qs = []
    if "post" in names:
        from g1_recall import QUESTIONS
        qs += [{"set": "post", "q": q, "expect": [e.lower() for e in exp]} for q, exp in QUESTIONS]
    if "pre" in names:
        qs += [{"set": "pre", "q": r["q"], "answer": r["answer"]} for r in json.loads((d / "pre.json").read_text())]
    return qs


def hit(row: dict, text: str) -> bool:
    if "expect" in row:
        t = text.lower()
        return any(e in t for e in row["expect"])
    return bool(re.search(row["answer"], text, re.I))


def read_as(policy: str, q: str):
    from walter_memory import context, generations
    if policy == "today":
        return context.get_context(q, include_profile=False)
    gens = {"g1": ["g1"], "g0": ["g0"]}.get(policy)
    if gens is None:
        raise SystemExit(f"unknown policy {policy}")
    saved = generations._cache
    generations._cache = (time.monotonic(), gens)
    try:
        return context.get_context(q, include_profile=False)
    finally:
        generations._cache = saved


class Judge:
    def __init__(self, cache_path: Path):
        self.path = cache_path
        self.cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    def __call__(self, q: str, text: str, sample: int = 0) -> str:
        key = hashlib.sha256(f"{q}\x00{text}".encode()).hexdigest() + (f":{sample}" if sample else "")
        if key in self.cache:
            return self.cache[key]
        if not text.strip():
            return "no"
        from walter_memory import llm
        prompt = JUDGE_PROMPT.format(q=q, ctx=text[:8000])
        verdict = "error"
        for _ in range(3):
            try:
                c = llm.chat([{"role": "user", "content": prompt}], poste="memory_extraction", processor="bench.g0_g1",
                             privacy_class="cloud_allowed", budget="backfill", purpose="g0/g1 bench judge",
                             response_format={"type": "json_object"}, max_tokens=800)["content"]
                v = json.loads(c[c.find("{"):c.rfind("}") + 1]).get("verdict")
                if v in ("yes", "partial", "no"):
                    verdict = v
                    break
            except Exception:  # noqa: BLE001 — retry, then an error (not counted as a no)
                continue
        if verdict != "error":
            self.cache[key] = verdict
        return verdict

    def save(self) -> None:
        self.path.write_text(json.dumps(self.cache, indent=0))
        self.path.chmod(0o600)


def meta() -> dict:
    from walter_memory import generations
    from walter_memory.db import connection
    with connection() as conn:
        derived = {r["generation"]: r["n"] for r in conn.execute(
            "select generation, count(*) n from core.derived_items group by 1")}
    sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                         text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "walter_memory"],
                                capture_output=True, text=True).stdout.strip())
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "commit": sha, "dirty": dirty,
            "read_set": generations.read_set(), "derived_per_generation": derived}


def cost_since(t0: datetime) -> dict:
    from walter_memory.db import connection
    with connection() as conn:
        rows = conn.execute("""select processor, count(*) n, coalesce(sum(cost_usd), 0) usd from system.model_calls
                               where at >= %s and processor in ('search.rerank', 'bench.g0_g1') group by 1""",
                            (t0,)).fetchall()
    return {r["processor"]: {"calls": r["n"], "usd": round(float(r["usd"]), 4)} for r in rows}


def summarise(rows: list[dict], policy: str, judged: bool) -> dict:
    rs = [r[policy] for r in rows]
    lat = sorted(x["ms"] for x in rs)
    out = {"n": len(rs), "hit": sum(x["hit"] for x in rs), "median_tokens": int(statistics.median(x["tokens"] for x in rs)),
           "median_ms": int(statistics.median(lat)), "p90_ms": lat[int(0.9 * (len(lat) - 1))],
           "lines": sum(x["lines"] for x in rs), "distinct": sum(x["distinct"] for x in rs),
           "items_g0": sum(x["gen"].get("g0", 0) for x in rs), "items_g1": sum(x["gen"].get("g1", 0) for x in rs)}
    out["redundancy"] = round(1 - out["distinct"] / max(1, out["lines"]), 3)
    if judged:
        for v in ("yes", "partial", "no", "error"):
            out[v] = sum(x.get("judge") == v for x in rs)
        out["score"] = round(sum(x["score"] or 0 for x in rs), 2)       # sum of mean judge scores (max n)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="post,pre")
    ap.add_argument("--policies", default="today,g1,g0")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--samples", type=int, default=3, help="judge draws per context (score = mean, yes 1 / partial .5)")
    ap.add_argument("--no-rerank", action="store_true", help="free, but not the production order")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    d = bench_dir()
    qs, policies = load_sets(a.sets.split(","), d), a.policies.split(",")
    from walter_memory import search
    if a.no_rerank:
        search._rerank = lambda qq, rr, limit, timeout=8: rr[:limit]
    t0 = datetime.now(timezone.utc)
    info = meta()
    read_as("today", qs[0]["q"])                       # warm-up (embedding model, pools)
    judge = Judge(d / "judge-cache.json") if a.judge else None
    rows, texts = [], []
    for row in qs:
        r = {"set": row["set"], "q": row["q"]}
        for p in policies:                             # sequential: latency is measured, not contended
            res = read_as(p, row["q"])
            text = res["text"]
            know = [re.sub(r"^- ", "", l) for sec in res["sections"].values() for l in sec.splitlines()
                    if l.startswith("- ")]                  # every injected memory line, whatever its section
            gen: dict[str, int] = {}
            for it in res["trace"].get("items") or []:
                gen[it.get("generation") or "-"] = gen.get(it.get("generation") or "-", 0) + 1
            r[p] = {"hit": hit(row, text), "tokens": res["trace"]["total_tokens"], "ms": res["trace"]["latency_ms"],
                    "lines": len(know), "distinct": distinct(know), "gen": gen,
                    "sha": hashlib.sha256(text.encode()).hexdigest()[:12]}
            texts.append((r, p, row["q"], text))
        rows.append(r)
    if judge:
        jobs = [(t, k) for t in texts for k in range(a.samples)]
        with ThreadPoolExecutor(6) as ex:
            verdicts = list(ex.map(lambda j: judge(j[0][2], j[0][3], j[1]), jobs))
        for i, (r, p, _, _) in enumerate(texts):
            vs = verdicts[i * a.samples:(i + 1) * a.samples]
            ok = [{"yes": 1.0, "partial": 0.5, "no": 0.0}[v] for v in vs if v != "error"]
            r[p]["judges"] = "".join(v[0] for v in vs)
            r[p]["score"] = round(sum(ok) / len(ok), 3) if ok else None
            r[p]["judge"] = max(set(vs), key=vs.count)
        judge.save()
    out = {"meta": {**info, "sets": a.sets, "rerank": not a.no_rerank, "judge": a.judge, "samples": a.samples,
                    "seconds": round((datetime.now(timezone.utc) - t0).total_seconds())}, "summary": {}, "rows": rows}
    for s in sorted({r["set"] for r in rows}):
        sub = [r for r in rows if r["set"] == s]
        out["summary"][s] = {p: summarise(sub, p, a.judge) for p in policies}
        if "today" in policies and "g1" in policies:
            out["summary"][s]["lost_if_g1_only"] = [r["q"] for r in sub if r["today"]["hit"] and not r["g1"]["hit"]]
            out["summary"][s]["gained_if_g1_only"] = [r["q"] for r in sub if r["g1"]["hit"] and not r["today"]["hit"]]
    out["meta"]["cost"] = cost_since(t0)
    path = a.out or d / "runs" / f"{t0.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    path.chmod(0o600)
    print(json.dumps({"out": str(path), "meta": out["meta"],
                      "summary": {s: {k: (len(v) if isinstance(v, list) else v) for k, v in m.items()}
                                  for s, m in out["summary"].items()}}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
