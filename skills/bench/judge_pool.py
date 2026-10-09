"""Gold v2: pooled relevance judgments (TREC style) so the benchmark stops trusting Hermes' own choices.

pool  : for each sample case, candidates = historical gold + top-5 of every system dump given (both corpora),
        written in batches to data/judge/batch_XX.jsonl for judges (Claude Haiku 5.5 subagents).
score : reads data/judge/out_XX.jsonl ({"id", "labels": {skill: 0|1|2}}) and scores every system:
        hit@k = a skill labelled 2 ("the one to load") within the top k; hit@k_soft = labelled >= 1.
Usage: python judge_pool.py pool --systems a.jsonl,b.jsonl  |  python judge_pool.py score --systems ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from evaluate import DATA, load

JUDGE = DATA / "judge"
IDS = ""  # --ids: pool these case ids instead of the benchmark sample


def read_system(path: Path) -> dict[tuple[str, str], list[str]]:
    """(id, corpus) -> ranked names. LLM dumps carry no corpus field: corpus is taken from the file name."""
    out = {}
    corpus_hint = "full" if "_full_" in path.name else "active"
    for line in open(path):
        r = json.loads(line)
        out[(r["id"], r.get("corpus", corpus_hint))] = r["ranked"]
    return out


def pool(systems: list[Path], batch: int) -> None:
    cases, corpus = load()
    by_name = {s["name"]: s for s in corpus}
    cards = {}
    for s in corpus:
        p = Path("/opt/walter-skills/index/cards") / f"{s['name']}.json"
        cards[s["name"]] = json.loads(p.read_text()).get("summary", "") if p.exists() else ""
    sample = {json.loads(line)["id"] for line in open(DATA / "llm_active_hermes-index_gpt-6-luna.jsonl")}
    if IDS:
        sample = set(open(IDS).read().split())
    dumps = [read_system(p) for p in systems]
    JUDGE.mkdir(exist_ok=True)
    os.chmod(JUDGE, 0o700)
    judged: dict[str, set] = {}
    for f in JUDGE.glob("out_*.jsonl"):
        for line in open(f):
            if line.strip():
                r = json.loads(line)
                judged.setdefault(r["id"], set()).update(r["labels"])
    for f in JUDGE.glob("batch_*.jsonl"):
        f.unlink()
    items = []
    for c in cases:
        if c["id"] not in sample:
            continue
        cand = list(dict.fromkeys(c["gold"] + c["gold_active"]))
        for d in dumps:
            for corpus_name in ("active", "full"):
                cand += d.get((c["id"], corpus_name), [])[:5]
        cand = [n for n in dict.fromkeys(cand) if n in by_name and n not in judged.get(c["id"], set())]
        if not cand:
            continue
        ctx = c.get("context") or {}
        items.append({"id": c["id"], "previous_user_message": ctx.get("prev_user", "")[-400:],
                      "previous_assistant_message": ctx.get("prev_assistant", "")[-500:],
                      "current_user_message": c["query"][:1500],
                      "candidates": [{"name": n, "description": by_name[n]["description"][:300],
                                      "summary": cards[n][:200]} for n in sorted(cand)]})
    for i in range(0, len(items), batch):
        p = JUDGE / f"batch_{len(list(JUDGE.glob('out_*.jsonl'))) + i // batch:02d}.jsonl"
        p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in items[i:i + batch]) + "\n")
        os.chmod(p, 0o600)
    print(f"{len(items)} cases to judge in {(len(items) + batch - 1) // batch} batches; "
          f"avg {sum(len(x['candidates']) for x in items) / max(1, len(items)):.1f} candidates")


def score(systems: list[Path]) -> None:
    labels: dict[str, dict] = {}
    for f in sorted(JUDGE.glob("out_*.jsonl")):
        for line in open(f):
            if line.strip():
                r = json.loads(line)
                labels.setdefault(r["id"], {}).update(r["labels"])
    print(f"judged cases: {len(labels)}")
    n_rel = sum(any(v == 2 for v in lab.values()) for lab in labels.values())
    print(f"cases with a skill labelled 2: {n_rel}; with none: {len(labels) - n_rel}")
    cases, _ = load()
    hist = {c["id"]: c for c in cases}
    for path in systems:
        d = read_system(path)
        agg = defaultdict(lambda: defaultdict(float))
        for (cid, corpus_name), ranked in d.items():
            lab = labels.get(cid)
            if lab is None or not any(v == 2 for v in lab.values()):
                continue
            a = agg[corpus_name]
            a["n"] += 1
            for k in (1, 3, 5):
                a[f"hit{k}"] += any(lab.get(n) == 2 for n in ranked[:k])
                a[f"hit{k}_soft"] += any(lab.get(n, 0) >= 1 for n in ranked[:k])
        for corpus_name, a in sorted(agg.items()):
            n = a.pop("n")
            print(f"{path.stem:45} {corpus_name:6} n={int(n)} " +
                  " ".join(f"{k}={100 * v / n:.1f}" for k, v in a.items()))
    # how good was the historical gold itself?
    g = [any(labels[i].get(n) == 2 for n in hist[i]["gold"]) for i in labels if any(v == 2 for v in labels[i].values())]
    print(f"historical gold (skill Hermes opened) judged 'the one to load': {100 * sum(g) / max(1, len(g)):.1f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pool", "score"])
    ap.add_argument("--systems", default="")
    ap.add_argument("--batch", type=int, default=27)
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    global IDS
    IDS = a.ids
    systems = [Path(p) for p in a.systems.split(",") if p]
    pool(systems, a.batch) if a.cmd == "pool" else score(systems)


if __name__ == "__main__":
    sys.exit(main())
