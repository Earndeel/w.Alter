#!/usr/local/bin/walter-python
"""Lab bench, owner request 2026-11-16: the same messages played by Walter's current engine (DSH headless, its test
home, hook + walter-context pack + walter-llm `auto`) and by Unharnessed through walter-unharnessed (same pack, same
`auto`, same MCP). Both runs are channel `test` (walter-llm's 2 €/24 h cap). Order alternates per case.

Measures per run: ok, seconds, model turns, tool calls (DSH tools / Unharnessed cells), tokens, models actually
served (from the Walter run). Judging is done afterwards against the expected facts below (`expect`), by a human.

Usage: bench.py [--only NAME,...] [--repeats N]  → report in @instance/state/lab/unharnessed/bench/<time>.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADAPTER = HERE / "bin" / "walter-unharnessed"
DSH = "/opt/dsh/node_modules/.bin/dsh"

def cases() -> list[dict]:
    """The bench's messages and expected facts belong to the instance (they name its data): @instance/config/lab/
    unharnessed-bench.json, {"cases": [{"name", "prompt", "expect"}]}."""
    out = subprocess.run(["walter", "instance", "config", "lab", "unharnessed-bench.json"], capture_output=True,
                         text=True, timeout=30)
    path = Path(out.stdout.strip())
    if out.returncode or not path.is_file():
        raise SystemExit("no bench cases: @instance/config/lab/unharnessed-bench.json")
    return json.loads(path.read_text())["cases"]


def served(run_id: str | None) -> tuple[list[str], dict | None]:
    if not run_id:
        return [], None
    out = subprocess.run(["walter-memory", "runs", "show", run_id], capture_output=True, text=True, timeout=60)
    data = json.loads(out.stdout or "{}")
    calls = data.get("model_calls") or []
    run = data.get("run") or {}
    return (sorted({f"{c.get('provider')}/{c.get('model_id')}" for c in calls}),
            run.get("requested") or (run.get("routing") or {}).get("requested"))


def run_dsh(case: dict, timeout: int) -> dict:
    ws = tempfile.mkdtemp(prefix="unharnessed-bench-dsh-")
    env = {**os.environ, "DSH_HOME": "/opt/dsh/test-home", "WALTER_RUN_CHANNEL": "test"}
    t0 = time.time()
    try:
        out = subprocess.run([DSH, "--profile", "headless", "--json", case["prompt"]], capture_output=True, text=True,
                             cwd=ws, env=env, timeout=timeout)
        stdout, rc = out.stdout, out.returncode
    except subprocess.TimeoutExpired as e:
        stdout, rc = (e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else e.stdout or ""), 124
    sid, answer, tin, tout, steps, tools, failed = None, None, 0, 0, 0, 0, 0
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        if t == "session":
            sid = ev.get("sessionId")
        elif t == "final":
            answer = ev.get("text")
        elif t == "tool_call":
            tools += 1
        elif t == "tool_result" and ev.get("status") != "completed":
            failed += 1
        elif t == "status" and ev.get("phase") == "step_end":
            steps += 1
            tin += (ev.get("usage") or {}).get("inputTokens") or 0
            tout += (ev.get("usage") or {}).get("outputTokens") or 0
    run_id = None
    if sid:
        time.sleep(2)                     # DSH's Stop hook closes the run; let it and the gateway's record land
        f = subprocess.run(["walter-memory", "runs", "find", "--session", f"dsh/vm/{sid}"], capture_output=True,
                           text=True, timeout=60)
        run_id = (json.loads(f.stdout or "{}") or {}).get("run_id")
    models, planned = served(run_id)
    return {"harness": "dsh", "ok": rc == 0 and answer is not None, "rc": rc, "seconds": round(time.time() - t0, 1),
            "turns": steps, "tool_calls": tools, "tool_failures": failed, "input_tokens": tin, "output_tokens": tout,
            "served_by": models, "planned": planned, "run_id": run_id, "workdir": ws, "answer": answer}


def run_unharnessed(case: dict, timeout: int, tag: str) -> dict:
    t0 = time.time()
    out = subprocess.run([str(ADAPTER), "run", "--timeout", str(timeout), "--workdir", f"bench/{tag}", case["prompt"]],
                         capture_output=True, text=True, timeout=timeout + 300)
    try:
        s = json.loads(out.stdout)
    except ValueError:
        return {"harness": "unharnessed", "ok": False, "rc": out.returncode, "seconds": round(time.time() - t0, 1),
                "error": (out.stderr or out.stdout)[-500:]}
    return {"harness": "unharnessed", "ok": s.get("ok"), "rc": s.get("rc"), "seconds": s.get("seconds"),
            "turns": s.get("turns"), "tool_calls": s.get("cells"), "input_tokens": s.get("input_tokens"),
            "output_tokens": s.get("output_tokens"), "cache_read_tokens": s.get("cache_read_tokens"),
            "served_by": s.get("served_by"), "planned": s.get("planned"), "run_id": s.get("run_id"),
            "context": s.get("context_notes"), "workdir": f"bench/{tag}", "answer": s.get("answer"),
            "errors": s.get("errors")}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", default="")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--timeout", type=int, default=900)
    a = p.parse_args()
    only = {x for x in a.only.split(",") if x}
    stamp = time.strftime("%Y%m%dT%H%M%S")
    out_dir = Path(subprocess.run(["walter", "instance", "path", "state", "lab", "unharnessed", "bench"],
                                  capture_output=True, text=True).stdout.strip())
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"at": stamp, "cases": []}
    for rep in range(a.repeats):
        for i, case in enumerate(c for c in cases() if not only or c["name"] in only):
            order = ("dsh", "unharnessed") if (i + rep) % 2 == 0 else ("unharnessed", "dsh")
            row = {"case": case["name"], "repeat": rep, "expect": case["expect"], "order": order, "runs": []}
            for h in order:
                r = run_dsh(case, a.timeout) if h == "dsh" else run_unharnessed(case, a.timeout, f"{stamp}-{case['name']}-{rep}")
                row["runs"].append(r)
                print(f"{case['name']:13} {h:12} ok={r.get('ok')} {r.get('seconds')}s turns={r.get('turns')} "
                      f"tools={r.get('tool_calls')} in={r.get('input_tokens')} out={r.get('output_tokens')} "
                      f"{r.get('served_by')}", flush=True)
            report["cases"].append(row)
            (out_dir / f"{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(out_dir / f"{stamp}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
