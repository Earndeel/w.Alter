"""Train the fusion on judged labels (poste skills.judge) instead of Hermes' loading habits, evaluate on the judged
benchmark sample (never used for training).

Training cases: the judged dev cases (data/train_judge_ids.txt), optionally plus the raw log cases at a low weight.
Memory (learned triggers) and usage prior: every dev case outside the benchmark sample, strictly earlier in time.
Usage: python train_judged.py [--variants judged-lr,judged-hgb,mixed-hgb] [--dump-best]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/opt/walter-skills")
from walter_skills import cards as cards_mod  # noqa: E402
from walter_skills.retrieve import Encoder, Index  # noqa: E402

from evaluate import DATA, load, metrics, summarize  # noqa: E402
from evaluate_walter import ENCODERS, prep  # noqa: E402


def judged_labels() -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for f in sorted((DATA / "judge").glob("out_*.jsonl")):
        for line in open(f):
            if line.strip():
                r = json.loads(line)
                labels.setdefault(r["id"], {}).update(r["labels"])
    return labels


def judged_metrics(ranked: list[str], lab: dict) -> dict:
    return {f"j_hit{k}": float(any(lab.get(n) == 2 for n in ranked[:k])) for k in (1, 3, 5)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="judged-lr,judged-hgb,mixed-hgb")
    ap.add_argument("--encoder", default="potion")
    ap.add_argument("--log-weight", type=float, default=0.2)
    ap.add_argument("--dump", default="")
    a = ap.parse_args()
    cases, corpus_all = load()
    cases = [prep(c) for c in cases]
    labels = judged_labels()
    sample_ids = {json.loads(line)["id"] for line in open(DATA / "llm_active_hermes-index_gpt-6-luna.jsonl")}
    train_ids = set(open(DATA / "train_judge_ids.txt").read().split())
    dev = [c for c in cases if c["split"] == "dev" and c["id"] not in sample_ids]
    sample = [c for c in cases if c["id"] in sample_ids]
    cards = {s["name"]: cards_mod.load(s["name"]) or {} for s in corpus_all}
    enc = Encoder(ENCODERS[a.encoder])
    report, dumps = {}, []
    for corpus_name, gold_key in (("active", "gold_active"), ("full", "gold")):
        corpus = [s for s in corpus_all if corpus_name == "full" or not s["archived"]]
        idx = Index(corpus, cards, enc, prior=Counter(g for c in dev for g in c[gold_key]))
        idx.set_memory(dev, gold_key)
        judged_train = [c | {"labels": labels[c["id"]]} for c in dev if c["id"] in train_ids and c["id"] in labels]
        logs = [c | {"weight": a.log_weight} for c in dev if c["id"] not in train_ids]
        for variant in a.variants.split(","):
            data, kind = variant.split("-")
            train = judged_train + (logs if data == "mixed" else [])
            if data == "logs":
                train = dev
            w = idx.fit(train, gold_key, kind=kind)
            rows_h, rows_j = [], []
            for c in sample:
                top = [n for n, _ in idx.search(c["query"], c["ctx"], k=40, before=c["ts"], exclude=c["id"],
                                                session=c.get("session_skills"))]
                if c[gold_key]:
                    rows_h.append(metrics(top, c[gold_key]))
                lab = labels.get(c["id"], {})
                if any(v == 2 for v in lab.values()):
                    rows_j.append(judged_metrics(top, lab))
                if a.dump and variant == a.variants.split(",")[-1]:
                    dumps.append({"id": c["id"], "corpus": corpus_name, "ranked": top})
            n = len(rows_j)
            jm = {k: round(100 * sum(r[k] for r in rows_j) / n, 1) for k in rows_j[0]} | {"n_judged": n}
            key = f"{corpus_name}/{variant}"
            report[key] = {"historical": summarize(rows_h), "judged": jm,
                           "weights": {k: round(v, 2) for k, v in w.items()}}
            print(key, "judged", jm, "| historical", summarize(rows_h), flush=True)
    (DATA / f"results_judged_{a.encoder}.json").write_text(json.dumps(report, indent=1))
    if a.dump:
        Path(a.dump).write_text("\n".join(json.dumps(d) for d in dumps) + "\n")


if __name__ == "__main__":
    main()
