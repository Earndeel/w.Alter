"""Lot E2 bench: the engine's native intake against walter_hook.py on the same messages (04-BASELINE § 2).

Two DSH test homes with the same composition except the intake switch (hook / native), real DSH headless, real
Walter services, runs on channel test. Prompts alternate between the homes so both see the same warm services.
For each turn: the intake latency (hook: UserPromptSubmit durationMs from the DSH session log; native: the plugin's
measurement), the Stop/turn end cost (hook only), the runs opened for the session (one per turn expected), the plan
written on the run (level, act, task), the bus events turn.ended, and the answer's head. Numbers only in the report.

    walter-python core/engine/bench/e2_intake.py --out <dir> [--rounds 1]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

DSH = "/opt/dsh/node_modules/.bin/dsh"
HOMES = {"native": "/opt/dsh/e2-home", "hook": "/opt/dsh/e2-hook-home"}
PROMPTS = [
    "Sans utiliser aucun outil, réponds en une phrase : dans quel pays Monsieur vit-il en ce moment ?",
    "Sans utiliser aucun outil, réponds en une phrase : pour les images, Walter Router doit-il prendre le meilleur rapport qualité-prix ou le meilleur modèle disponible ?",
    "Sans utiliser aucun outil, réponds en une phrase : comment s'appelle le skill d'entrée de Walter pour une recherche de produit local avec Pareto ?",
    "Quelle heure est-il ?",
    "Sans utiliser aucun outil, réponds en une phrase : par quelle connexion sort le navigateur Chromium de Walter ?",
]


def instance() -> Path:
    return Path(subprocess.run(["walter", "instance", "path"], capture_output=True, text=True).stdout.strip())


def turn(mode: str, prompt: str) -> dict:
    ws = tempfile.mkdtemp(prefix=f"e2-{mode}-")
    env = {**os.environ, "DSH_HOME": HOMES[mode], "WALTER_RUN_CHANNEL": "test"}
    t0 = time.time()
    out = subprocess.run([DSH, "--profile", "headless", "--json", prompt], capture_output=True, text=True, cwd=ws,
                         env=env, timeout=400)
    wall = time.time() - t0
    sid = answer = None
    for line in out.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "session":
            sid = ev.get("sessionId")
        elif ev.get("type") == "final":
            answer = ev.get("text")
    return {"mode": mode, "sid": sid, "ok": out.returncode == 0 and answer is not None, "wall_s": round(wall, 1),
            "answer_head": (answer or "")[:120]}


def hook_ms(sid: str) -> dict:
    files = list(Path(HOMES["hook"], "sessions").rglob(f"{sid}/session.v4.jsonl.zstd"))
    if not files:
        return {}
    text = subprocess.run(["zstdcat", "-q", str(files[0])], capture_output=True, text=True).stdout
    found: dict[str, list] = {}
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        stack = [ev]
        while stack:                       # the hook result sits somewhere in the event: walk it
            x = stack.pop()
            if isinstance(x, dict):
                if x.get("point") in ("UserPromptSubmit", "Stop") and isinstance(x.get("durationMs"), (int, float)):
                    found.setdefault(x["point"], []).append(round(x["durationMs"]))
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    return found


def native_ms(sid: str) -> list[dict]:
    rows = []
    for f in sorted((instance() / "state" / "core" / "engine" / "intake").glob("observations-*.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            if r.get("session") == f"dsh/vm/{sid}" and r.get("kind") == "intake":
                rows.append({k: r.get(k) for k in ("native_ms", "run_ms", "memory_ms", "skills_ms", "memory_chars", "skills_chars")})
    return rows


def runs_of(sid: str) -> dict:
    from walter_memory.db import connect
    key = f"dsh/vm/{sid}"
    with connect() as c:
        runs = c.execute("""select status, origin->>'channel' ch, level, act, routing->'requested'->>'task' task
                            from runs.runs where origin->>'session_id' = %s order by started_at""", (key,)).fetchall()
        ended = c.execute("select count(*) n from bus.events where type = 'turn.ended' and subject = %s", (key,)).fetchone()["n"]
    return {"runs": [dict(r) for r in runs], "turn_ended": ended}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=1)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for r in range(a.rounds):
        for i, prompt in enumerate(PROMPTS):
            order = ("native", "hook") if (i + r) % 2 == 0 else ("hook", "native")
            for mode in order:
                row = {"round": r, "prompt": i, **turn(mode, prompt)}
                time.sleep(3)                      # the turn's end lands (run end, bus) before it is read
                if row["sid"]:
                    row.update(runs_of(row["sid"]))
                    row["intake"] = hook_ms(row["sid"]) if mode == "hook" else native_ms(row["sid"])
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False, default=str), flush=True)
    (out / "e2-intake-bench.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
