"""Evaluate the walter-skills retriever against the same cases/corpora as the Hermes baselines.

Sets: `sample` = the 216 cases the Hermes LLM baseline ran on; `test` = every test case (>= 2026-09-20).
Training/memory = dev cases not in the sample (learned triggers only from strictly earlier messages).
Usage: python evaluate_walter.py [--encoder potion|minilm] [--fit] [--dump data/walter_top.jsonl]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, "/opt/walter-skills")
from walter_skills import cards as cards_mod  # noqa: E402
from walter_skills.retrieve import Encoder, Index  # noqa: E402

from evaluate import DATA, load, metrics, summarize  # noqa: E402

ENCODERS = {"potion": "minishlab/potion-multilingual-128M",
            "minilm": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "mpnet": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
            "e5": "intfloat/multilingual-e5-large"}


def prep(c: dict) -> dict:
    ctx = c.get("context") or {}
    c["ctx"] = f"{ctx.get('prev_user', '')}\n{ctx.get('prev_assistant', '')[-300:]}".strip()
    c["ts"] = datetime.fromisoformat(c["at"]).timestamp()
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--encoder", default="minilm")
    ap.add_argument("--fit", default="", help="lr | hgb")
    ap.add_argument("--no-hist", action="store_true")
    ap.add_argument("--no-session", action="store_true")
    ap.add_argument("--dump", default="")
    ap.add_argument("--dump-ids", default="", help="also rank these case ids (for judging pools)")
    a = ap.parse_args()
    cases, corpus_all = load()
    cases = [prep(c) for c in cases]
    sample_ids = {json.loads(line)["id"] for line in open(DATA / "llm_active_hermes-index_gpt-6-luna.jsonl")}
    train = [c for c in cases if c["split"] == "dev" and c["id"] not in sample_ids]
    sets = {"sample": [c for c in cases if c["id"] in sample_ids], "test": [c for c in cases if c["split"] == "test"]}
    if a.dump_ids:
        extra = set(open(a.dump_ids).read().split())
        sets["extra"] = [c for c in cases if c["id"] in extra]
    cards = {s["name"]: cards_mod.load(s["name"]) or {} for s in corpus_all}
    print(f"cards: {sum(bool(v) for v in cards.values())}/{len(cards)}", file=sys.stderr)
    enc = Encoder(ENCODERS[a.encoder])
    results, dump = {}, []
    for corpus_name, gold_key in (("active", "gold_active"), ("full", "gold")):
        corpus = [s for s in corpus_all if corpus_name == "full" or not s["archived"]]
        prior = Counter(g for c in train for g in c[gold_key])
        idx = Index(corpus, cards, enc, prior=prior)
        if not a.no_hist:
            idx.set_memory(train, gold_key)
        else:
            idx.weights.update(hist=0.0, hist_c=0.0)
        if a.fit:
            t0 = time.time()
            w = idx.fit(train, gold_key, kind=a.fit)
            print(corpus_name, "fit", {k: round(v, 2) for k, v in w.items()}, f"{time.time() - t0:.0f}s",
                  file=sys.stderr)
            idx.save_weights(DATA / f"weights_{corpus_name}_{a.encoder}_{a.fit}.json")
        for set_name, sub in sets.items():
            rows, lat = [], []
            for c in sub:
                if not c[gold_key]:
                    continue
                t0 = time.perf_counter()
                top = idx.search(c["query"], c["ctx"], k=10, before=c["ts"], exclude=c["id"],
                                 session=None if a.no_session else c.get("session_skills"))
                lat.append(time.perf_counter() - t0)
                ranked = [n for n, _ in top]
                rows.append(metrics(ranked, c[gold_key]))
                if a.dump:
                    dump.append({"id": c["id"], "corpus": corpus_name, "ranked": ranked})
            key = f"{corpus_name}/{set_name}/walter-{a.encoder}{'-' + a.fit if a.fit else ''}{'-nohist' if a.no_hist else ''}{'-nosess' if a.no_session else ''}"
            results[key] = summarize(rows) | {"p50_ms": round(1000 * float(np.median(lat)), 1)}
            print(key, results[key], flush=True)
    out = DATA / f"results_walter_{a.encoder}{'_' + a.fit if a.fit else ''}{'_nohist' if a.no_hist else ''}{'_nosess' if a.no_session else ''}.json"
    out.write_text(json.dumps(results, indent=1))
    if a.dump:
        Path(a.dump).write_text("\n".join(json.dumps(d) for d in dump) + "\n")


if __name__ == "__main__":
    main()
