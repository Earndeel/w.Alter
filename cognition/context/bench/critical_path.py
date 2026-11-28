"""Critical path of a turn (mission « Native Engine × Cognitive Architecture » §9, 2026-11-17).

    PYTHONPATH=/walter/cognition/context:/walter/cognition/memory walter-python bench/critical_path.py run [--limit N]
    … report bench/reports/critical-path-<stamp>.jsonl + a summary on stdout

Same synthetic requests (bench/decision-state-corpus.json: invented people and projects, gold read with the whole
context), four ways of preparing the main model's turn, measured in this process exactly as the preflight service
runs them (Prefetch started with the message, the plan, then gather + pack under the caller's deadline):

  old      the preflight as it ran until 17/11: message + last exchange + candidate thread, no DecisionState
  living   [state] decision_state + living_state: the session's WorkingState (objective, tasks, decisions, memory
           notes, sources — what is known BEFORE the message, fed here as the events the engine posts) is read into
           the DecisionState
  direct   no probabilistic decision: the prudent local plan (degraded_plan: L3, memory, the session's thread)
  adaptive computed from the living runs, no extra call: the turn starts at min(decision, budget); a decision
           later than the budget is replaced by the direct plan (and would come back as an incremental update)

Per case: decision ms, pack ms, total ms, pack tokens, decision tokens, plan / act / needs against the gold
(the decision's quality — NOT the main model's execution, which this bench does not run), the sources the plan
retrieved although the gold needs none (« appels inutiles »). Decision calls go through the gateway like
production (journalled, Router's chain); the run stops if `walter-llm test-budget` shows less than the reserve left.
The owner's Memory is read by the pack (timings and token counts only are kept, never a block's text)."""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
CORPUS = json.loads((HERE / "decision-state-corpus.json").read_text())["cases"]
RESERVE_USD = 0.3
DEADLINE_S = 7.0                       # what the engine waits for the preflight (answer_within default)
BUDGETS_MS = (400, 600, 800)


def spent() -> float:
    out = subprocess.run(["walter-llm", "test-budget"], capture_output=True, text=True, timeout=30).stdout
    return float(json.loads(out)["spent_usd"])


def request(case: dict, sid: str):
    from walter_context.preflight import Exchange, Request
    prev = case.get("previous")
    th = case.get("thread")
    cands = [dict(th)] if th else []
    if th and case.get("objective") and not th.get("objective"):
        cands[0]["objective"] = case["objective"]
    if th and case.get("tasks"):
        cands[0]["task"] = case["tasks"][0]["text"] if isinstance(case["tasks"][0], dict) else case["tasks"][0]
    return Request(turn_id=f"cp-{case['id']}", message=case["message"],
                   previous=Exchange(prev["message"], prev.get("answer"), prev.get("age_s", 120),
                                     prev.get("thread_id") or (th or {}).get("id")) if prev else None,
                   candidates=cands, session_id=sid, default_thread=(th or {}).get("id"))


def seed(manager, sid: str, case: dict) -> None:
    """What the engine has posted before this message: objective, tasks, decisions and notes Memory gave, sources."""
    evs = []
    if case.get("objective"):
        evs.append({"kind": "objective.changed", "payload": {"goal": case["objective"]}})
    for i, t in enumerate(case.get("tasks") or []):
        t = t if isinstance(t, dict) else {"text": t}
        evs.append({"kind": "task.started" if t.get("status") != "done" else "task.ended",
                    "payload": {"task_id": f"t{i}", "goal": t["text"], "status": t.get("status") or "running"}})
    items = [{"kind": "decision", "text": d} for d in case.get("prior_decisions") or []] + \
            [{"kind": "information", "text": m} for m in case.get("memory") or []]
    if items:
        evs.append({"kind": "memory.changed", "payload": {"items": items}})
    for s in case.get("sources") or []:
        evs.append({"kind": "observation", "payload": {"text": s, "source": "source", "ref": s[:60]}})
    if evs:
        manager.update(sid, evs)


def one(case: dict, mode: str, manager, rep: int = 0) -> dict:
    from walter_context import preflight as P
    from walter_context.assembly import pack
    from walter_context.config import STATE_DEFAULTS
    from walter_context.retrieval import Prefetch, gather
    on = mode == "living"
    P.state_settings = lambda path=None: {**STATE_DEFAULTS, "decision_state": on, "living_state": on}
    sid = f"bench-cp/{mode}/{case['id']}/{rep}"
    if on:
        seed(manager, sid, case)
    req = request(case, sid)
    t0 = time.monotonic()
    due = t0 + DEADLINE_S
    pre = Prefetch(req.message, None)
    d0 = time.perf_counter()
    if mode == "direct":
        plan = P.degraded_plan(req, RuntimeError("bench: direct"), d0)
    else:
        plan = P.run(req, purpose="bench critical-path", within=DEADLINE_S - 1.0, readings="apart")
    dec_ms = (time.perf_counter() - d0) * 1000
    g0 = time.monotonic()
    blocks, notes = gather(plan, req.message, session_key=None, deadline=due, prefetch=pre, native_history=True)
    pk = pack(plan, blocks, notes)
    pending = getattr(plan, "_readings", None)
    if pending is not None and not pending.settle(plan, 0):
        pending.late(plan)
    total = (time.monotonic() - t0) * 1000
    s = pk.summary()
    gold = case["gold"]
    needs = sorted(c for c in plan.capabilities if c != "tools")
    level = P.PLAN_LEVEL[gold["plan"]]
    retrieved = [b["id"] for b in s["blocks"] if b["id"] in ("memory", "session_state", "records", "experience")]
    d = plan.decision or {}
    return {"case": case["id"], "mode": mode, "decision_ms": round(dec_ms), "pack_ms": round((time.monotonic() - g0) * 1000),
            "total_ms": round(total), "pack_tokens": s.get("tokens_per_message"), "late_notes": len(notes),
            "decision_model": d.get("model"), "fast_path": plan.fast_path, "degraded": bool(d.get("degraded")),
            "plan": plan.level == level, "act": plan.act == gold["act"], "needs": needs == sorted(gold["needs"]),
            "useless_retrieval": retrieved if (gold["plan"] in ("none", "last_exchange") and not gold["needs"]) else [],
            "got": {"level": plan.level, "act": plan.act, "needs": needs}, "want": {"level": level, **gold},
            "resolution": (d.get("resolution") or {}).get("changed")}


def score(r: dict) -> float:
    return (r["plan"] + r["act"] + r["needs"]) / 3


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else None


def summary(rows: list[dict]) -> dict:
    out = {}
    by = {}
    for r in rows:
        by.setdefault(r["mode"], []).append(r)
    for mode, rs in by.items():
        out[mode] = {"n": len(rs), "quality": round(statistics.mean(score(r) for r in rs), 3),
                     "plan": sum(r["plan"] for r in rs), "act": sum(r["act"] for r in rs), "needs": sum(r["needs"] for r in rs),
                     "decision_ms_p50_p90_max": [pct([r["decision_ms"] for r in rs], 50), pct([r["decision_ms"] for r in rs], 90),
                                                 max(r["decision_ms"] for r in rs)],
                     "total_ms_p50_p90_max": [pct([r["total_ms"] for r in rs], 50), pct([r["total_ms"] for r in rs], 90),
                                              max(r["total_ms"] for r in rs)],
                     "pack_tokens_p50": pct([r["pack_tokens"] or 0 for r in rs], 50),
                     "useless_retrieval": sum(1 for r in rs if r["useless_retrieval"]),
                     "late_sources": sum(r["late_notes"] for r in rs)}
    liv = {(r["case"], r.get("rep", 0)): r for r in by.get("living", [])}
    dire = {r["case"]: r for r in by.get("direct", [])}
    for b in BUDGETS_MS:                 # adaptive, simulated from the measured runs (no extra call)
        rs = []
        for cid, r in liv.items():
            late = r["decision_ms"] > b and not r["fast_path"]
            base = dire.get(cid[0]) if late else r
            rs.append({"q": score(base), "total": (b if late else r["decision_ms"]) + (base["total_ms"] - base["decision_ms"])})
        if rs:
            out[f"adaptive@{b}ms"] = {"n": len(rs), "quality": round(statistics.mean(x["q"] for x in rs), 3),
                                      "replaced_by_direct": sum(1 for cid, r in liv.items() if r["decision_ms"] > b and not r["fast_path"]),
                                      "total_ms_p50_p90_max": [pct([x["total"] for x in rs], 50), pct([x["total"] for x in rs], 90),
                                                               round(max(x["total"] for x in rs))]}
    return out


def run(limit: int | None, modes: list[str], repeat: int = 1) -> int:
    from walter_context import state as S
    cases = CORPUS[:limit] if limit else CORPUS
    start = spent()
    print(f"{len(cases)} cases × {modes} × {repeat}, spend so far {start} USD", file=sys.stderr)
    tmp = Path(tempfile.mkdtemp(prefix="cp-state-"))
    from walter_context.config import state_settings
    manager = S.Manager(S.Store(tmp), state_settings())
    S._MANAGER[:] = [manager]
    out = HERE / "reports" / f"critical-path-{datetime.now(timezone.utc):%Y%m%dT%H%M}.jsonl"
    rows = []
    with out.open("w") as f:
        jobs = [(rep, i, case) for rep in range(repeat) for i, case in enumerate(cases)]
        for rep, i, case in jobs:       # one at a time: the timings are those of one owner, not of a burst
            k = (i + rep) % len(modes)  # the mode that runs first (cold Memory memo) rotates: no order bias
            for mode in modes[k:] + modes[:k]:
                try:
                    r = one(case, mode, manager, rep)
                except Exception as exc:  # noqa: BLE001
                    r = {"case": case["id"], "mode": mode, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                    print(json.dumps(r), file=sys.stderr)
                    continue
                r["rep"] = rep
                rows.append(r)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"{mode:7s} {case['id']:20s} dec {r['decision_ms']:5d} total {r['total_ms']:5d} q {score(r):.2f}",
                      file=sys.stderr)
            if spent() - start > 2.2 - RESERVE_USD:
                print("budget reserve reached: stop", file=sys.stderr)
                break
        s = summary(rows)
        f.write(json.dumps({"summary": s, "spent_usd": round(spent() - start, 4)}, ensure_ascii=False) + "\n")
    print(json.dumps(s, ensure_ascii=False, indent=1))
    print(f"report: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--modes", default="old,living,direct")
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    sys.exit(run(a.limit, a.modes.split(","), a.repeat))
