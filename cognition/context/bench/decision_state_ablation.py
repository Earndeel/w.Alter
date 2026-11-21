"""DecisionState ablation (2026-11-17): what does each input contribute to the decision's quality?

    PYTHONPATH=/walter/cognition/context:/walter/cognition/memory walter-python bench/decision_state_ablation.py run [--limit N] [--dry]
    … report bench/reports/decision-state-<stamp>.jsonl

Synthetic corpus only (bench/decision-state-corpus.json: invented people and projects). For each case the decision is
asked EXACTLY as Context's reassess/preflight ask it — Walter Decision, occasion `turn`, `ask` = context.act +
context.plan + context.needs, 3 samples averaged, the Router's decision chain — on a state carrying the message and the compact
DecisionState built from a subset of the inputs. Conditions: the message alone; message + one input (additive); all
inputs; all but one (leave-one-out). Scores against the gold read with the whole context: plan, act, needs (set
equality at p >= 0.5), and their mean. Spend: decision calls only, journalled by the gateway (purpose
« bench decision-state »); the run stops if `walter-llm test-budget` shows less than the reserve left."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "decision-state-corpus.json").read_text())["cases"]
ASK = ["context.act", "context.plan", "context.needs"]
INPUTS = ("last_exchange", "thread", "objective", "tasks", "memory", "prior_decisions", "sources", "capabilities")
CONDITIONS = ([("message", {"message"})] + [(f"+{i}", {"message", i}) for i in INPUTS]
              + [("all", {"message", *INPUTS})] + [(f"all-{i}", {"message", *INPUTS} - {i}) for i in INPUTS])
MAX_SPEND_USD = 0.28
RESERVE_USD = 0.15


def spent() -> float:
    out = subprocess.run(["walter-llm", "test-budget"], capture_output=True, text=True, timeout=30).stdout
    return float(json.loads(out)["spent_usd"])


def build(case: dict, use: set) -> tuple[dict, list[str]]:
    from walter_context import decision_state as DS
    ds = DS.build(case["message"], previous=case.get("previous"), thread=case.get("thread"), objective=case.get("objective"),
                  tasks=case.get("tasks"), memory=case.get("memory"), prior_decisions=case.get("prior_decisions"),
                  sources=case.get("sources"), capabilities=case.get("capabilities"), use=use)
    return {"new_message": case["message"], "decision_state": DS.compact(ds)}, ds["facts"]


def score(sig: dict, gold: dict) -> dict:
    plan = (sig.get("context.plan") or {}).get("choice")
    act = (sig.get("context.act") or {}).get("choice")
    probs = (sig.get("context.needs") or {}).get("probabilities") or {}
    needs = sorted(k for k, p in probs.items() if isinstance(p, (int, float)) and p >= 0.5 and k != "tools")
    r = {"plan": plan == gold["plan"], "act": act == gold["act"], "needs": needs == sorted(gold["needs"])}
    r["all"] = sum(r.values()) / 3
    return {**r, "got": {"plan": plan, "act": act, "needs": needs}}


def run(limit: int | None, dry: bool) -> int:
    from walter_memory import llm
    cases = CORPUS[:limit] if limit else CORPUS
    jobs = [(name, use, c) for name, use in CONDITIONS for c in cases]
    start = spent()
    print(f"{len(jobs)} decisions, spend so far {start} USD", file=sys.stderr)
    if dry:
        return 0
    out = HERE / "reports" / f"decision-state-{datetime.now(timezone.utc):%Y%m%dT%H%M}.jsonl"
    stop = {"now": False}

    def one(job):
        name, use, c = job
        if stop["now"]:
            return None
        state, facts = build(c, use)
        t0 = time.perf_counter()
        try:
            res = llm.decide(state, None, processor="walter-context-preflight", privacy_class="cloud_allowed", purpose="bench decision-state",
                             budget="recurring", timeout=20, samples=3, occasion="turn", focus="new_message", facts=facts, ask=ASK)
            sc = score(res.get("signals") or {}, c["gold"])
        except Exception as exc:  # noqa: BLE001
            sc = {"plan": False, "act": False, "needs": False, "all": 0.0, "error": f"{type(exc).__name__}: {str(exc)[:80]}"}
        return {"condition": name, "case": c["id"], "resolver": c["resolver"], "ms": round((time.perf_counter() - t0) * 1000), **sc}
    rows = []
    with out.open("w") as f, ThreadPoolExecutor(4) as pool:
        for i, row in enumerate(pool.map(one, jobs)):
            if row is None:
                continue
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if i % 25 == 24:
                s = spent() - start
                print(f"{i + 1}/{len(jobs)} spent {s:.4f} USD", file=sys.stderr)
                if s > MAX_SPEND_USD:
                    stop["now"] = True
                    print("spend cap reached: stopping", file=sys.stderr)
    print(f"spent {spent() - start:.4f} USD; rows: {out}", file=sys.stderr)
    report(out)
    return 0


def report(path: Path) -> None:
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["condition"], []).append(r)
    base = by.get("message")
    def mean(rs, k):
        return round(sum(1 if r[k] is True else r[k] if isinstance(r[k], float) else 0 for r in rs) / len(rs), 3) if rs else None
    print(f"{'condition':26} {'n':>3} {'plan':>6} {'act':>6} {'needs':>6} {'mean':>6} {'Δ mean':>7}  errors")
    b = mean(base, "all") if base else None
    for name, _ in CONDITIONS:
        rs = by.get(name)
        if not rs:
            continue
        m = mean(rs, "all")
        print(f"{name:26} {len(rs):>3} {mean(rs,'plan'):>6} {mean(rs,'act'):>6} {mean(rs,'needs'):>6} {m:>6} "
              f"{'' if b is None else format(m - b, '+.3f'):>7}  {sum(1 for r in rs if r.get('error'))}")
    allm = mean(by["all"], "all") if by.get("all") else None
    if allm is not None:
        print("\nleave-one-out (drop of the mean when the input is removed from `all`):")
        for i in INPUTS:
            rs = by.get(f"all-{i}")
            if rs:
                print(f"  {i:18} {allm - mean(rs, 'all'):+.3f}")
    rs_res = {}
    for r in by.get("all", []):
        rs_res.setdefault(r["resolver"], []).append(r)
    print("\n`all` by case family (resolver):", {k: mean(v, "all") for k, v in rs_res.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int)
    r.add_argument("--dry", action="store_true")
    p = sub.add_parser("report")
    p.add_argument("path")
    a = ap.parse_args()
    sys.exit(run(a.limit, a.dry) if a.cmd == "run" else (report(Path(a.path)) or 0))
