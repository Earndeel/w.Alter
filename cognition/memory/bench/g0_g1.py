#!/usr/bin/env python3
"""g0 vs g1 benchmark (lot D of the 2026-11-09 mandate): what each memory read policy puts in Walter's context.

  walter-python bench/g0_g1.py [--sets v2,post,pre] [--policies today,g1,c,g0] [--judge] [--no-rerank] [--out FILE]

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
    if "v2" in names:     # bench/corpus_v2.py: questions written from canonical messages, verified answers
        qs += [{"set": "v2", "cat": r["cat"], "period": r["period"], "q": r["q"], "expected": r["answer"]}
               for r in json.loads((d / "corpus-v2.json").read_text())]
    return qs


def hit(row: dict, text: str) -> bool | None:
    if "expected" in row:
        return None            # free-text answer: only the judge can tell
    if "expect" in row:
        t = text.lower()
        return any(e in t for e in row["expect"])
    return bool(re.search(row["answer"], text, re.I))


def read_as(policy: str, q: str):
    """today = live settings; g1 / g0 = that generation alone; c[:gate[:slots]] = g1_first read mode (g1 the memory,
    g0 only when one of its rows ranks among the best `gate` knowledge candidates, at most `slots`)."""
    from walter_memory import context, generations
    if policy == "today":
        return context.get_context(q, include_profile=False)
    if policy.startswith("c"):
        parts = policy.split(":")
        mode = {"read": "g1_first", "g0_gate": int(parts[1]) if len(parts) > 1 else 6,
                "g0_slots": int(parts[2]) if len(parts) > 2 else 3, "g0_candidates": 60}
        saved_mode, saved = generations._mode_override, generations._cache
        generations._mode_override, generations._cache = mode, (time.monotonic(), ["g0", "g1"])
        try:
            return context.get_context(q, include_profile=False)
        finally:
            generations._mode_override, generations._cache = saved_mode, saved
    gens = {"g1": ["g1"], "g0": ["g0"], "all": ["g0", "g1"]}.get(policy)
    if gens is None:
        raise SystemExit(f"unknown policy {policy}")
    saved_mode, saved = generations._mode_override, generations._cache
    generations._mode_override = {"read": "all", "g0_gate": 6, "g0_slots": 3, "g0_candidates": 60}
    generations._cache = (time.monotonic(), gens)
    try:
        return context.get_context(q, include_profile=False)
    finally:
        generations._mode_override, generations._cache = saved_mode, saved


JUDGE2_PROMPT = """Question posée à la mémoire de Walter, l'assistant personnel de Monsieur : {q}
Réponse attendue (vérifiée dans les messages d'origine) : {expected}

Lignes que la mémoire a fournies à l'assistant (numérotées) :
{ctx}

1. verdict : "correct" si ces lignes donnent l'information attendue (même formulée autrement, ou plus précise et
   compatible) ; "partial" si elles en donnent une partie seulement ; "absent" si elles ne la donnent pas ;
   "contradicted" si elles affirment une information incompatible (par exemple périmée) sans donner l'attendue.
2. relevant : les numéros des lignes utiles pour répondre à la question.
Réponds en JSON : {{"verdict": "...", "relevant": [numéros]}}"""
SCORE2 = {"correct": 1.0, "partial": 0.5, "absent": 0.0, "contradicted": 0.0}


def numbered(text: str) -> tuple[str, int]:
    """The context's memory lines, numbered (headers kept for orientation)."""
    out, n = [], 0
    for line in text.splitlines():
        if line.startswith("- "):
            n += 1
            out.append(f"{n}. {line[2:]}")
        elif line.startswith("## "):
            out.append(line)
    return "\n".join(out), n


def expected_of(row: dict) -> str:
    if "expected" in row:
        return row["expected"]
    if "expect" in row:
        return "doit mentionner l'un de : " + " / ".join(row["expect"])
    return "doit correspondre à l'expression : " + row["answer"]


class Judge2:
    """Answer correctness against the verified expected answer + which injected lines are relevant (precision)."""
    def __init__(self, cache_path: Path):
        self.path = cache_path
        self.cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    def __call__(self, row: dict, text: str, sample: int = 0) -> dict:
        ctx, n = numbered(text)
        exp = expected_of(row)
        key = hashlib.sha256(f"j2\x00{row['q']}\x00{exp}\x00{ctx}".encode()).hexdigest() + (f":{sample}" if sample else "")
        if key in self.cache:
            return self.cache[key]
        if n == 0:
            return {"verdict": "absent", "relevant": [], "lines": 0}
        from walter_memory import llm
        prompt = JUDGE2_PROMPT.format(q=row["q"], expected=exp, ctx=ctx[:12000])
        out = {"verdict": "error", "relevant": [], "lines": n}
        for _ in range(3):
            try:
                c = llm.chat([{"role": "user", "content": prompt}], poste="memory_extraction", processor="bench.g0_g1",
                             privacy_class="local_only", budget="backfill", purpose="g0/g1 bench judge (expected)",
                             response_format={"type": "json_object"}, max_tokens=800)["content"]
                j = json.loads(c[c.find("{"):c.rfind("}") + 1])
                if j.get("verdict") in SCORE2:
                    rel = sorted({int(x) for x in j.get("relevant") or [] if str(x).isdigit() and 1 <= int(x) <= n})
                    out = {"verdict": j["verdict"], "relevant": rel, "lines": n}
                    break
            except Exception:  # noqa: BLE001
                continue
        if out["verdict"] != "error":
            self.cache[key] = out
        return out

    def save(self) -> None:
        self.path.write_text(json.dumps(self.cache, indent=0))
        self.path.chmod(0o600)


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


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return 0
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def summarise(rows: list[dict], policy: str, judged: bool) -> dict:
    rs = [r[policy] for r in rows]
    lat = [x["ms"] for x in rs]
    out = {"n": len(rs), "median_tokens": int(statistics.median(x["tokens"] for x in rs)),
           "mean_tokens": int(statistics.mean(x["tokens"] for x in rs)),
           "p50_ms": pct(lat, 0.5), "p95_ms": pct(lat, 0.95),
           "candidates_mean": round(statistics.mean(x["candidates"] for x in rs), 1),
           "lines": sum(x["lines"] for x in rs), "distinct": sum(x["distinct"] for x in rs),
           "items_g0": sum(x["gen"].get("g0", 0) for x in rs), "items_g1": sum(x["gen"].get("g1", 0) for x in rs),
           "g0_kept": sum(x.get("g0_kept", 0) for x in rs)}
    hits = [x["hit"] for x in rs if x["hit"] is not None]
    if hits:
        out["hit"] = f"{sum(hits)}/{len(hits)}"
    out["redundancy"] = round(1 - out["distinct"] / max(1, out["lines"]), 3)
    if judged:
        for v in ("correct", "partial", "absent", "contradicted", "error"):
            out[v] = sum(x.get("verdict") == v for x in rs)
        out["score"] = round(sum(x.get("score") or 0 for x in rs), 2)
        out["score_pct"] = round(100 * out["score"] / max(1, len(rs)), 1)
        rel = sum(x.get("relevant", 0) for x in rs)
        out["precision"] = round(rel / max(1, sum(x.get("judged_lines", 0) for x in rs)), 3)
        out["relevant_lines_mean"] = round(rel / max(1, len(rs)), 2)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="v2,post,pre")
    ap.add_argument("--policies", default="today,g1,c")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--samples", type=int, default=1, help="judge draws per context (score = mean)")
    ap.add_argument("--no-rerank", action="store_true", help="free, but not the production order")
    ap.add_argument("--limit", type=int, default=0, help="first N questions only (smoke test)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    d = bench_dir()
    qs, policies = load_sets(a.sets.split(","), d), a.policies.split(",")
    if a.limit:
        qs = qs[:a.limit]
    from walter_memory import search
    if a.no_rerank:
        search._rerank = lambda qq, rr, limit, timeout=8: rr[:limit]
    t0 = datetime.now(timezone.utc)
    info = meta()
    read_as("today", qs[0]["q"])                       # warm-up (embedding model, pools)
    judge = Judge2(d / "judge2-cache.json") if a.judge else None
    rows, texts = [], []
    for row in qs:
        r = {"set": row["set"], "q": row["q"], "cat": row.get("cat") or ("personal" if row["set"] == "pre" else "post"),
             "period": row.get("period") or ("pre" if row["set"] == "pre" else "post")}
        for p in policies:                             # sequential: latency is measured, not contended
            res = read_as(p, row["q"])
            text = res["text"]
            know = [re.sub(r"^- ", "", l) for sec in res["sections"].values() for l in sec.splitlines()
                    if l.startswith("- ")]                  # every injected memory line, whatever its section
            gen: dict[str, int] = {}
            for it in res["trace"].get("items") or []:
                gen[it.get("generation") or "-"] = gen.get(it.get("generation") or "-", 0) + 1
            secs = res["trace"]["sections"]
            r[p] = {"hit": hit(row, text), "tokens": res["trace"]["total_tokens"], "ms": res["trace"]["latency_ms"],
                    "lines": len(know), "distinct": distinct(know), "gen": gen,
                    "candidates": sum((secs.get(k) or {}).get("candidates", 0) for k in ("records", "knowledge"))
                    + (res["trace"].get("g0_fallback") or {}).get("candidates", 0),
                    "g0_kept": (res["trace"].get("g0_fallback") or {}).get("kept", 0),
                    "sha": hashlib.sha256(text.encode()).hexdigest()[:12]}
            texts.append((r, p, row, text))
        rows.append(r)
    if judge:
        jobs = [(t, k) for t in texts for k in range(a.samples)]
        with ThreadPoolExecutor(6) as ex:
            verdicts = list(ex.map(lambda j: judge(j[0][2], j[0][3], j[1]), jobs))
        for i, (r, p, _, _) in enumerate(texts):
            vs = verdicts[i * a.samples:(i + 1) * a.samples]
            ok = [v for v in vs if v["verdict"] != "error"]
            r[p]["verdicts"] = "".join(v["verdict"][0] for v in vs)
            r[p]["score"] = round(sum(SCORE2[v["verdict"]] for v in ok) / len(ok), 3) if ok else None
            r[p]["verdict"] = max({v["verdict"] for v in vs}, key=[v["verdict"] for v in vs].count)
            r[p]["relevant"] = round(sum(len(v["relevant"]) for v in ok) / max(1, len(ok)), 2)
            r[p]["judged_lines"] = ok[0]["lines"] if ok else 0
        judge.save()
    out = {"meta": {**info, "sets": a.sets, "policies": policies, "rerank": not a.no_rerank, "judge": a.judge,
                    "samples": a.samples, "seconds": round((datetime.now(timezone.utc) - t0).total_seconds())},
           "summary": {}, "rows": rows}
    groups = {"all": rows}
    for key in ("set", "cat", "period"):
        for v in sorted({r[key] for r in rows}):
            groups[f"{key}={v}"] = [r for r in rows if r[key] == v]
    for g, sub in groups.items():
        out["summary"][g] = {p: summarise(sub, p, a.judge) for p in policies}
        if a.judge and "today" in policies:
            for p in policies:
                if p == "today":
                    continue
                out["summary"][g][f"{p}_vs_today"] = {
                    "worse": sum(1 for r in sub if (r[p].get("score") or 0) < (r["today"].get("score") or 0)),
                    "better": sum(1 for r in sub if (r[p].get("score") or 0) > (r["today"].get("score") or 0))}
    out["meta"]["cost"] = cost_since(t0)
    path = a.out or d / "runs" / f"{t0.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    path.chmod(0o600)
    print(json.dumps({"out": str(path), "meta": out["meta"], "summary": out["summary"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
