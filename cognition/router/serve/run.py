"""Do the job on the chosen model — one entry for every runtime (Hermes plugin, walter MCP, the command).

    spec ──▶ decision: the model named by the owner (named.py: exactly that, or why not) / a hard constraint / the
             request classified by the decision model (routes.route)
         ├─ text  ──▶ a sub-agent with tools on the chosen model: a one-shot run in the Hermes runtime (the runtime
         │           here that runs every provider: Codex subscription, Kie, OpenRouter, Arnict), routes in order,
         │           a provider test before the flaky ones, every attempt in models.exec_log
         └─ media ──▶ media_exec.generate (image, video, music, voice): costs money, on request only

A routed run may end on the subscription's model as a flagged substitute; a named model never does.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

from walter_router.serve import choose, execution, media_exec, named, routes

CHILD_ENV = "WALTER_ROUTER_CHILD"   # set in the sub-agent: its router tools hide (no recursive routing)
ALLOWED_TOOLSETS = ("web", "walter-web", "file", "terminal", "vision", "skills", "code_execution", "memory")
DEFAULT_TOOLSETS = ["web", "walter-web", "file", "terminal"]
MAX_ATTEMPTS = 3
LAST_RESORT = {"hermes_provider": "openai-codex", "provider": "codex", "model": "gpt-6.1-sol", "reasoning": "high"}
PREFLIGHT = {"kie": "kie", "kie-codex": "kie-codex"}   # outages frequent and slow to detect inside a run
FAILURE_MARKS = ("didn't answer after", "Provider said:", "looks temporarily unavailable")
MEDIA = ("image", "video", "music", "audio")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def decide(conn, spec: dict) -> dict:
    if spec.get("model"):
        return named.named(conn, spec["model"], spec.get("provider"), spec.get("task"))
    if spec.get("require"):
        return routes.with_execution(conn, choose.pick(conn, spec.get("task") or "general", spec.get("level"),
                                                       require=spec["require"]))
    return routes.route(conn, spec.get("request") or spec.get("goal") or "", spec.get("task"), spec.get("level"),
                        spec.get("conversation"))


def _once(route: dict, prompt_file: str, toolsets: list[str], max_turns: int, budget: int) -> tuple[bool, str]:
    hermes = shutil.which("hermes")
    if not hermes:
        return False, "Hermes runtime not installed (command `hermes`)"
    cmd = [hermes, "chat", "--query-file", prompt_file, "--oneshot", "-Q", "--provider", route["hermes_provider"],
           "-m", route["model"], "-t", ",".join(toolsets), "--max-turns", str(max_turns), "--run-budget", str(budget),
           "--source", "walter-router"]
    if route.get("reasoning"):
        cmd += ["--reasoning", route["reasoning"]]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=budget + 120, env={**os.environ, CHILD_ENV: "1"})
    except subprocess.TimeoutExpired:
        return False, f"timeout after {budget + 120}s"
    lines = [ln for ln in _ANSI.sub("", out.stdout + out.stderr).splitlines() if not ln.startswith("session_id:")]
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith(("⚠", "Run 'hermes doctor'"))
                     or "Config issues detected" in lines[0]):
        lines.pop(0)   # start-up config warnings are not the sub-agent's answer
    text = "\n".join(lines).strip()
    return not (out.returncode != 0 or not text or any(m in text[-600:] for m in FAILURE_MARKS)), text


def _text(conn, d: dict, spec: dict) -> dict:
    started = time.monotonic()
    toolsets = [t for t in (spec.get("toolsets") or DEFAULT_TOOLSETS) if t in ALLOWED_TOOLSETS] or DEFAULT_TOOLSETS
    max_turns = max(1, min(int(spec.get("max_turns") or 40), 120))
    budget = max(60, min(int(spec.get("budget_seconds") or 900), 3600))
    prompt = spec["goal"] + (f"\n\nContexte :\n{spec['context']}" if spec.get("context") else "")
    is_named = d.get("source") == "named"
    attempts: list[dict] = []
    with tempfile.NamedTemporaryFile("w", suffix=".txt", prefix="walter-run-", delete=False) as fh:
        fh.write(prompt)
        prompt_file = fh.name

    def result(route: dict, text: str, **extra) -> dict:
        return {"ok": True, "kind": "text", "output": text[-30000:],
                "routed": {"task": d.get("task"), "role": d.get("role"), "model": route["model"],
                           "provider": route.get("provider") or route["hermes_provider"],
                           "reasoning": route.get("reasoning"), "fallback_for": route.get("fallback_for"),
                           "named": d.get("named"), "attempts": attempts,
                           "seconds": round(time.monotonic() - started), **extra}}
    try:
        runs = 0
        for route in d.get("execution") or []:
            if runs >= MAX_ATTEMPTS:
                break
            hp = route["hermes_provider"]
            base = {"task": d.get("task"), "role": d.get("role"),
                    "model_id": None if route.get("fallback_for") else d.get("model_id"),
                    "provider": hp, "model": route["model"], "fallback_for": route.get("fallback_for")}
            if hp in PREFLIGHT and not (execution.probe(conn, only=PREFLIGHT[hp], timeout=25).get(PREFLIGHT[hp]) or {}).get("ok"):
                attempts.append({"provider": hp, "model": route["model"], "ok": False, "skipped": "provider test failed"})
                execution.log(conn, {**base, "ok": False, "skipped": "preflight"})
                conn.commit()
                continue
            if route.get("probe_ok") is False and hp not in PREFLIGHT and not is_named:
                attempts.append({"provider": hp, "model": route["model"], "ok": False, "skipped": "last provider test failed"})
                continue
            runs += 1
            t0 = time.monotonic()
            ok, text = _once(route, prompt_file, toolsets, max_turns, budget)
            execution.log(conn, {**base, "ok": ok, "seconds": round(time.monotonic() - t0, 1)})
            conn.commit()
            attempts.append({"provider": hp, "model": route["model"], "ok": ok})
            if ok:
                return result(route, text)
        if not is_named and not (d.get("require") == "unrestricted" or d.get("unrestricted_signals")) \
                and "openai-codex" not in {a["provider"] for a in attempts}:
            ok, text = _once(LAST_RESORT, prompt_file, toolsets, max_turns, budget)   # the subscription, flagged
            attempts.append({"provider": "openai-codex", "model": LAST_RESORT["model"], "ok": ok, "last_resort": True})
            if ok:
                return result(LAST_RESORT, text, substituted_for=d.get("model_id"))
        return {"ok": False, "kind": "text", "error": "every route failed" + (" (modèle nommé : aucun substitut)" if is_named else ""),
                "attempts": attempts, "last_output": (locals().get("text") or "")[-1500:]}
    finally:
        os.unlink(prompt_file)


def run(conn, spec: dict) -> dict[str, Any]:
    if not (spec.get("goal") or spec.get("request")):
        return {"ok": False, "error": "goal (text) or request (media) required"}
    d = decide(conn, spec)
    if d.get("mode") == "none" or d.get("error"):
        return {"ok": False, "error": d.get("error") or d.get("why") or "no model", "decision": d}
    t = conn.execute("select interface from models.tasks where task = %s", (d.get("task"),)).fetchone()
    if t and t["interface"] in MEDIA:
        is_named = d.get("source") == "named"
        if is_named and d["task"] == "text_to_video" and spec.get("image_urls") and not spec.get("task"):
            d["task"] = "image_to_video"
        out = media_exec.generate(conn, spec.get("request") or spec["goal"], task=d["task"], role=spec.get("role"),
                                  image_urls=spec.get("image_urls"), aspect_ratio=spec.get("aspect_ratio"),
                                  duration=spec.get("duration"), resolution=spec.get("resolution"),
                                  paid_fallback=bool(spec.get("paid_fallback")),
                                  model=d["model_id"] if is_named else None,
                                  provider=d.get("provider") if is_named else None, _fallback=not is_named)
        return {"ok": bool(out.get("files")) or out.get("mode") == "manual_ui", "kind": "media", **out}
    if not d.get("execution"):
        return {"ok": False, "error": f"no execution route for task {d.get('task')}", "decision": d}
    if not spec.get("goal"):
        return {"ok": False, "error": "goal required: complete instructions for the sub-agent (it does not see the conversation)"}
    return _text(conn, d, spec)
