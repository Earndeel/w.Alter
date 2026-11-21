#!/usr/bin/env walter-python
"""Baseline of the engine's real traffic, read from what production already writes (read-only).

Measures, over a window of days, the path between an input and a useful result:
  - intake (engine plug-in journal, `@instance/state/core/engine/intake/observations-*.jsonl`): time spent before the
    first model call (`native_ms`), of which preflight + context pack (`memory_ms`);
  - preflight (walter-context journal, `@instance/state/context/shadow/preflight-*.jsonl`): whole call, decision,
    context retrieval, model, degraded and fast-path rates;
  - turns of the engine (walter_logs, runtime dsh): turn duration, time to the first model answer, steps, tool calls,
    input / cached / output tokens per turn and per model call;
  - runs (Run Plane): outcome status counts.
Nothing is written but the report (`--out`). Message text is never read.

    walter-python /walter/core/engine/bench/baseline.py [--days 5] [--out FILE] [--since ISO] [--until ISO]
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def instance_root() -> Path:
    out = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, timeout=20).stdout.strip()
    return Path(out or "/walter/user")


def pct(values: list[float], *qs: float) -> dict:
    v = sorted(x for x in values if isinstance(x, (int, float)))
    if not v:
        return {"n": 0}
    out = {"n": len(v), "mean": round(statistics.fmean(v), 1)}
    for q in qs:
        i = min(len(v) - 1, max(0, round(q / 100 * (len(v) - 1))))
        out[f"p{q:g}"] = round(v[i], 1)
    return out


P = (50, 95, 99)


def read_jsonl(folder: Path, prefix: str, since: datetime, until: datetime) -> list[dict]:
    rows = []
    for path in sorted(folder.glob(f"{prefix}-*.jsonl")):
        try:
            day = datetime.strptime(path.stem.split(f"{prefix}-")[1], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if day + timedelta(days=1) < since or day > until:
            continue
        for line in path.read_text(errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            at = row.get("at")
            try:
                ts = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
            except ValueError:
                continue
            if since <= ts <= until:
                rows.append(row)
    return rows


def intake(root: Path, since, until) -> dict:
    rows = [r for r in read_jsonl(root / "state/core/engine/intake", "observations", since, until)
            if r.get("kind") == "intake" and not r.get("observation")]
    by_level = defaultdict(list)
    for r in rows:
        by_level[r.get("level") or "?"].append(r.get("native_ms"))
    return {"turns": len(rows), "native_ms": pct([r.get("native_ms") for r in rows], *P),
            "memory_ms": pct([r.get("memory_ms") for r in rows], *P),
            "skills_ms": pct([r.get("skills_ms") for r in rows], *P),
            "context_source": dict(Counter(r.get("context_source") for r in rows)),
            "native_ms_by_level": {k: pct(v, 50, 95) for k, v in sorted(by_level.items())}}


def preflight(root: Path, since, until) -> dict:
    rows = [r for r in read_jsonl(root / "state/context/shadow", "preflight", since, until)
            if r.get("runtime") not in ("warmup",)]
    plans = [r.get("plan") or {} for r in rows]
    dec = [p.get("decision") or {} for p in plans]
    return {"calls": len(rows), "total_ms": pct([r.get("total_ms") for r in rows], *P),
            "plan_ms": pct([r.get("plan_ms") for r in rows], *P),
            "decision_ms": pct([d.get("ms") for d in dec if not d.get("degraded")], *P),
            "retrieval_ms": pct([(r.get("pack") or {}).get("retrieval_ms") for r in rows], *P),
            "pack_tokens": pct([(r.get("pack") or {}).get("tokens_per_message") for r in rows], 50, 95),
            "models": dict(Counter(d.get("model") or ("degraded" if d.get("degraded") else "none") for d in dec)),
            "degraded": sum(1 for d in dec if d.get("degraded")),
            "fast_path": dict(Counter(p.get("fast_path") for p in plans if p.get("fast_path"))),
            "levels": dict(Counter(p.get("level") for p in plans))}


def turns(since, until) -> dict:
    from walter_memory import db
    conn = db.connect()
    rows = conn.execute("""
        select e.session_id, e.seq, e.type, e.occurred_at, e.turn, e.data
        from walter_logs.events e join walter_logs.sessions s using (session_id)
        where s.runtime = 'dsh' and e.occurred_at between %s and %s
          and e.type in ('turn/start', 'turn/end', 'assistant/message', 'tool/call', 'step/start', 'compaction/start')
        order by e.session_id, e.seq""", (since, until)).fetchall()
    per = {}
    calls = []
    cur = {}
    for r in rows:
        sid = r["session_id"]
        t = r["type"]
        if t == "turn/start":
            cur[sid] = {"start": r["occurred_at"], "first": None, "steps": 0, "tools": 0, "in": 0, "cached": 0,
                        "out": 0, "models": 0, "compactions": 0}
            continue
        c = cur.get(sid)
        if c is None:
            continue
        if t == "step/start":
            c["steps"] += 1
        elif t == "tool/call":
            c["tools"] += 1
        elif t == "compaction/start":
            c["compactions"] += 1
        elif t == "assistant/message":
            u = (r["data"] or {}).get("usage") or {}
            c["models"] += 1
            c["in"] += int(u.get("inputTokens") or 0)
            c["cached"] += int(u.get("cacheReadTokens") or 0)
            c["out"] += int(u.get("outputTokens") or 0)
            calls.append(int(u.get("inputTokens") or 0) + int(u.get("cacheReadTokens") or 0))
            if c["first"] is None:
                c["first"] = r["occurred_at"]
        elif t == "turn/end":
            c["end"] = r["occurred_at"]
            per[(sid, r["seq"])] = c
            cur.pop(sid, None)
    done = list(per.values())
    sec = lambda a, b: (b - a).total_seconds() if a and b else None  # noqa: E731
    return {"turns": len(done),
            "turn_s": pct([sec(c["start"], c.get("end")) for c in done], *P),
            "first_answer_s": pct([sec(c["start"], c["first"]) for c in done], *P),
            "steps": pct([c["steps"] for c in done], 50, 95),
            "tool_calls": pct([c["tools"] for c in done], 50, 95),
            "model_calls": pct([c["models"] for c in done], 50, 95),
            "input_tokens_per_turn": pct([c["in"] + c["cached"] for c in done], 50, 95),
            "uncached_input_tokens_per_turn": pct([c["in"] for c in done], 50, 95),
            "output_tokens_per_turn": pct([c["out"] for c in done], 50, 95),
            "context_tokens_per_model_call": pct(calls, *P),
            "turns_with_compaction": sum(1 for c in done if c["compactions"])}


def runs(since, until) -> dict:
    from walter_memory import db
    conn = db.connect()
    rows = conn.execute("""select status, outcome->>'status' as oc, extract(epoch from (ended_at - started_at)) as s,
                                  origin->>'runtime' as runtime
                           from runs.runs where started_at between %s and %s""", (since, until)).fetchall()
    dsh = [r for r in rows if r["runtime"] == "dsh"]
    return {"runs": len(rows), "dsh_runs": len(dsh), "status": dict(Counter(r["status"] for r in dsh)),
            "outcome": dict(Counter(r["oc"] for r in dsh)), "duration_s": pct([float(r["s"]) for r in dsh if r["s"] is not None], *P)}


def engine_process() -> dict:
    try:
        pid = subprocess.run(["systemctl", "show", "dsh-web", "-p", "MainPID", "--value"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        status = Path(f"/proc/{pid}/status").read_text()
        rss = next(int(line.split()[1]) for line in status.splitlines() if line.startswith("VmRSS"))
        mem = subprocess.run(["systemctl", "show", "dsh-web", "-p", "MemoryCurrent", "--value"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
        return {"pid": int(pid), "rss_mb": round(rss / 1024), "cgroup_mb": round(int(mem) / 2**20) if mem.isdigit() else None}
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=5)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--out")
    a = ap.parse_args()
    until = datetime.fromisoformat(a.until) if a.until else datetime.now(timezone.utc)
    since = datetime.fromisoformat(a.since) if a.since else until - timedelta(days=a.days)
    root = instance_root()
    report = {"window": {"since": since.isoformat(), "until": until.isoformat()},
              "intake": intake(root, since, until), "preflight": preflight(root, since, until),
              "turns": turns(since, until), "runs": runs(since, until), "engine_process": engine_process()}
    text = json.dumps(report, ensure_ascii=False, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
