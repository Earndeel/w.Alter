"""Benchmark — the same evaluator as the nightly promotion (walter_skills.evaluate), on the held-out labelled messages.

  python bench/run.py            active ranker on the held-out slice (bench + judge labels)
  python bench/run.py --hermes   + the Hermes baselines recorded on 2026-10-09 (data/llm_*.jsonl), on the same truth

History of the method and of every number: /root/.hermes/docs/walter-memory/DECISIONS.md (P10, 2026-10-09/10).
The scripts used on 2026-10-09 (dataset build, LLM baselines, judge pools, shortlist choosers) are in git history
(tag v1-before-refactor); their outputs stay in data/ (0600, private messages, never committed).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from walter_skills import evaluate, registry
from walter_skills.learning import _cases_by_qid
from walter_skills.ranker import Corpus, Encoder, Ranker
from walter_skills.retrieval import search_corpus_skills

DATA = Path(__file__).parent / "data"


def hermes_baselines(ev_ids: set[str]) -> dict:
    lab = registry.labels(("bench", "judge"))
    out = {}
    for f in sorted(DATA.glob("llm_full_hermes-index*_gpt-6-luna.jsonl")):
        hits, n = {1: 0, 3: 0, 5: 0}, 0
        for line in open(f):
            r = json.loads(line)
            good = {s for s, (v, _) in lab.get(r["id"], {}).items() if v == 2}
            if r["id"] not in ev_ids or not good:
                continue
            n += 1
            for k in hits:
                hits[k] += any(x in good for x in r["ranked"][:k])
        out[f.stem] = {f"at{k}": round(100 * v / n, 1) for k, v in hits.items()} | {"n": n}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hermes", action="store_true")
    a = ap.parse_args()
    row = registry.ranker()
    r = Ranker.loads(bytes(row["blob"]))
    c = Corpus(search_corpus_skills(), registry.cards(), Encoder.get())
    ev = evaluate.examples(_cases_by_qid(), holdout=True, sources=("bench", "judge"))
    print(json.dumps({"ranker": row["version"], "held_out": evaluate.measure(c, r, ev)}, indent=1))
    if a.hermes:
        print(json.dumps(hermes_baselines({x["qid"] for x in ev}), indent=1))


if __name__ == "__main__":
    main()
