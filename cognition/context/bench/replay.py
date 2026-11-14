"""C0 replay bench: real sessions from walter_logs, every provider call re-played under several context policies.

For each call (= each assistant message the model produced) the bench builds the payload the policy would send,
then simulates the provider prefix cache (previous payload, provider TTL, real timestamps) and prices it with the
model profile (input = 1). Policies:
  full            no compaction at all (what the history weighs)
  walter-context  this package, config as deployed
  hermes (real)   what Hermes actually sent, from system.agent_calls (A8) for the same sessions

Run (walter-memory venv, read-only on Postgres):
  /walter/cognition/context/bin/walter-context bench [--days 14] [--sessions 50] [--min-calls 15] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from walter_context import load  # noqa: E402
from walter_context.compress.layers import Epoch, project  # noqa: E402
from walter_context.compress.policy import common_prefix, signature  # noqa: E402
from walter_context.compress.session import Session  # noqa: E402
from walter_context.compress.wire import MEMO  # noqa: E402

HEAD_CHARS = 91_000      # Hermes fixed prefix measured 2026-10-11 (system 54 KB + tool schemas 37 KB)


def chains(conn, days: int, min_calls: int, limit: int, runtime: str = "hermes") -> list[list[dict]]:
    """Sessions stitched across Hermes compaction rotations (child → parent), newest first."""
    rows = conn.execute("""select session_id, parent_session_id, model, profile, native_id, started_at, ended_at, meta
                           from walter_logs.sessions where runtime = %s and last_event_at > now() - make_interval(days => %s)
                           order by started_at""", (runtime, days)).fetchall()
    by_id = {r["session_id"]: dict(r) for r in rows}
    nxt: dict[str, str] = {}                   # parent → its compaction continuation (started as the parent ended)
    gap: dict[str, float] = {}
    for r in rows:
        par = by_id.get(r["parent_session_id"])
        if not par or (par.get("meta") or {}).get("end_reason") != "compression" or not par.get("ended_at"):
            continue
        d = abs((r["started_at"] - par["ended_at"]).total_seconds())
        if d < 120 and d < gap.get(par["session_id"], 1e9):
            nxt[par["session_id"]], gap[par["session_id"]] = r["session_id"], d
    continued = set(nxt.values())
    out = []
    for root in (r for r in rows if r["session_id"] not in continued):
        chain, sid = [], root["session_id"]
        while sid:
            chain.append(by_id[sid])
            sid = nxt.get(sid)
        calls = sum(int((c.get("meta") or {}).get("api_call_count") or 0) for c in chain)
        if calls >= min_calls:
            out.append((calls, chain))
    out.sort(key=lambda x: -x[0])
    return [c for _, c in out[:limit]]


def messages(conn, chain: list[dict], *, cloud_safe: bool = False) -> tuple[list[dict], list[tuple[int, float, str]]]:
    """OpenAI-format history of a chain + the calls: (index of the produced assistant message, unix time, model)."""
    msgs: list[dict] = [{"role": "system", "content": "S" * HEAD_CHARS}]
    calls: list[tuple[int, float, str]] = []
    reasoning = ""
    open_step = False                          # last assistant message may still receive tool calls
    seen_calls: set[str] = set()
    previous: set[tuple[str, str]] = set()     # (type, text) of the parent session's messages
    for pos, sess in enumerate(chain):
        evs = conn.execute("""select type, call_id, tool, text, occurred_at, model, privacy_class from walter_logs.events
                              where session_id = %s order by seq""", (sess["session_id"],)).fetchall()
        if cloud_safe and any(e.get("privacy_class") != "cloud_allowed" for e in evs):
            return [], []  # reject the whole chain; never split tool pairs or relabel private history
        copying = pos > 0                      # a compaction child starts with a copy of the parent's tail
        mine: set[tuple[str, str]] = set()
        for e in evs:
            t, text = e["type"], e["text"] or ""
            if t in ("user/message", "assistant/message"):
                mine.add((t, text))
            if copying:
                if t in ("compaction/summary", "system/message", "assistant/reasoning") or \
                        (e["call_id"] and e["call_id"] in seen_calls) or (t, text) in previous:
                    continue
                copying = False
            if e["call_id"]:
                seen_calls.add(e["call_id"])
            at = e["occurred_at"].timestamp() if e["occurred_at"] else 0.0
            if t == "compaction/summary":
                if pos == 0:
                    msgs.append({"role": "user", "content": text})
                open_step = False
            elif t == "user/message":
                msgs.append({"role": "user", "content": text})
                open_step = False
            elif t == "assistant/reasoning":
                reasoning += text
            elif t == "assistant/message":
                m = {"role": "assistant", "content": text}
                if reasoning:
                    m["reasoning_content"], reasoning = reasoning, ""
                calls.append((len(msgs), at, e["model"] or sess.get("model") or ""))
                msgs.append(m)
                open_step = True
            elif t == "tool/call":
                tc = {"id": e["call_id"] or "", "type": "function", "function": {"name": e["tool"] or "", "arguments": text}}
                if open_step and msgs[-1]["role"] == "assistant":
                    msgs[-1].setdefault("tool_calls", []).append(tc)
                else:
                    m = {"role": "assistant", "content": "", "tool_calls": [tc]}
                    if reasoning:
                        m["reasoning_content"], reasoning = reasoning, ""
                    calls.append((len(msgs), at, e["model"] or sess.get("model") or ""))
                    msgs.append(m)
                    open_step = True
            elif t == "tool/result":
                msgs.append({"role": "tool", "tool_call_id": e["call_id"] or "", "content": text})
                open_step = False
        previous = mine
    return msgs, calls


class Meter:
    def __init__(self, name: str):
        self.name, self.rows = name, []

    def add(self, total: int, cached: int, cost: float, boundary: str = "", ms: float = 0.0):
        self.rows.append((total, cached, cost, boundary, ms))

    def summary(self, ref_cost: float | None = None) -> dict:
        if not self.rows:
            return {"policy": self.name, "calls": 0}
        tot = [r[0] for r in self.rows]
        cached = sum(r[1] for r in self.rows)
        cost = sum(r[2] for r in self.rows)
        q = statistics.quantiles(tot, n=20) if len(tot) > 1 else tot * 19
        b = [r[3] for r in self.rows if r[3]]
        ms = sorted(r[4] for r in self.rows)
        return {"policy": self.name, "calls": len(tot), "mean_tokens": round(statistics.mean(tot)),
                "p50": round(statistics.median(tot)), "p95": round(q[18]), "max": max(tot),
                "cached_pct": round(100 * cached / max(1, sum(tot)), 1),
                "uncached_mean": round((sum(tot) - cached) / len(tot)),
                "cost_units": round(cost), "cost_vs_full": round(cost / ref_cost, 3) if ref_cost else 1.0,
                "boundaries": {k: b.count(k) for k in sorted(set(b))},
                "select_ms_p95": ms[int(0.95 * (len(ms) - 1))] if ms else 0}


def replay(msgs: list[dict], calls: list[tuple[int, float, str]], cfg, meters: dict[str, Meter]) -> None:
    sess = Session(cfg, clock=lambda: now[0])
    now = [0.0]
    last_full, last_at, prev_model = (), None, None
    turn_seen = None
    for idx, at, model in calls:
        p = cfg.profile(model)
        history = msgs[:idx]
        warm = last_at is not None and at - last_at < p.cache_ttl_s and model == prev_model
        # full
        v = project(history, Epoch(), cfg.projection)
        sig = signature(v)
        cached = common_prefix(sig, last_full) if warm else 0
        meters["full"].add(v.tokens, cached, cached * p.cached_cost + (v.tokens - cached) * p.write_cost)
        last_full = sig
        # walter-context (its own clock, model and calibration exactly as live)
        now[0] = at
        sess.set_model(model)
        prev_last = sess.last if warm else ()
        sel = sess.select(history)
        t = sel.trace
        c = common_prefix(sess.last, prev_last)
        meters["walter-context"].add(t["tokens"], c, c * p.cached_cost + (t["tokens"] - c) * p.write_cost,
                                     t["boundary"], t["ms"])
        sess.observe({"prompt_tokens": t["tokens"]})          # the bench's "real" count is the estimate itself
        starts = [i for i, m in enumerate(history) if m.get("role") == "user"]
        if starts and starts[-1] != turn_seen:
            if turn_seen is not None:
                sess.turn_complete()
            turn_seen = starts[-1]
        last_at, prev_model = at, model


def hermes_real(conn, chain: list[dict], meter: Meter, cfg) -> None:
    ids = [c["native_id"] for c in chain]
    for r in conn.execute("""select model, input_tokens, coalesce(cached_tokens, 0) cached from system.agent_calls
                             where session_id = any(%s) order by at""", (ids,)).fetchall():
        p = cfg.profile(r["model"])
        t, c = r["input_tokens"] or 0, min(r["cached"], r["input_tokens"] or 0)
        meter.add(t, c, c * p.cached_cost + (t - c) * p.write_cost)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="walter-context bench")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--sessions", type=int, default=50)
    ap.add_argument("--min-calls", type=int, default=15)
    ap.add_argument("--runtime", default="hermes")
    ap.add_argument("--a8", action="store_true", help="only chains fully covered by A8 (apples-to-apples with Hermes)")
    ap.add_argument("--set", action="append", default=[], help="override, e.g. projection.keep_turns=2")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    from walter_memory.db import connection
    cfg = load()
    for s in a.set:
        key, val = s.split("=", 1)
        sect, field = key.split(".")
        cur = getattr(cfg, sect)
        cfg = replace(cfg, **{sect: replace(cur, **{field: type(getattr(cur, field))(val)})})
    meters = {k: Meter(k) for k in ("full", "walter-context", "hermes (real)")}
    t0 = time.time()
    n_calls = 0
    MEMO.enabled = True                       # the bench re-reads the same message objects call after call
    with connection() as conn:
        cs = chains(conn, a.days, a.min_calls, a.sessions, a.runtime)
        if a.a8:
            def covered(ch):
                ids = [c["native_id"] for c in ch]
                meta = sum(int((c.get("meta") or {}).get("api_call_count") or 0) for c in ch)
                n = conn.execute("select count(*) n from system.agent_calls where session_id = any(%s)", (ids,)).fetchone()["n"]
                return meta and n >= 0.9 * meta
            cs = [ch for ch in chains(conn, a.days, a.min_calls, 1000, a.runtime) if covered(ch)][:a.sessions]
        for chain in cs:
            MEMO.clear()
            msgs, calls = messages(conn, chain)
            n_calls += len(calls)
            replay(msgs, calls, cfg, meters)
            hermes_real(conn, chain, meters["hermes (real)"], cfg)
    ref = meters["full"].summary()["cost_units"] if meters["full"].rows else None
    report = {"sessions": len(cs), "calls": n_calls, "seconds": round(time.time() - t0, 1),
              "results": [m.summary(ref) for m in meters.values()]}
    print(json.dumps(report, indent=2))
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
