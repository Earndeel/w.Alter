#!/opt/walter-memory/venv/bin/python3
"""walter_hook — W.Alter's automatic behaviours for any agent runtime (P8.3, plug ③ of a Walter module).

One script, several hosts (the wire format is Claude Code's, which Hermes' shell hooks also speak):

  Claude Code  SessionStart      → one line telling the agent its session is journaled (+ how to recover exact
                                   messages after a compaction: memory_events(thread_id=…))
               UserPromptSubmit  → budgeted W.Alter memory context for the prompt (cloud-safe, secrets dropped)
               PreCompact        → journal the transcript synchronously, so the recovery pointer is true
               Stop / SessionEnd → journal the transcript in the background (connector agent_sessions)
  Hermes       pre_llm_call      → same memory context, answered as {"context": …}
  Codex        notify            → `walter_hook.py codex-notify '<json>'` (agent-turn-complete) → journal

Fail-open: any error → no output, exit 0, one line in ~/.hermes/logs/walter-hook.log. Never prints secrets.
Per-prompt context can be switched off with WALTER_HOOK_CONTEXT=off.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

GATEWAY = os.environ.get("WALTER_MEMORY_URL", "http://127.0.0.1:8890")
ENV_FILE = Path("/opt/walter-memory/.env")
CONNECTOR = ["/opt/walter-memory/venv/bin/python3", "/opt/walter-memory/connectors/agent_sessions.py"]
LOG = Path("/root/.hermes/logs/walter-hook.log")
BUDGET = {"profile": 0, "people": 300, "knowledge": 600, "evidence": 300}
MIN_WORDS = 4
HEADER = ("Mémoire W.Alter (injectée automatiquement pour ce message ; ce sont des souvenirs datés, vérifie l'état "
          "réel avant de les affirmer ; approfondir avec memory_search / person_lookup) :")


def log(msg: str) -> None:
    try:
        with LOG.open("a") as f:
            f.write(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}\n")
    except OSError:
        pass


def _privacy():
    """walter_memory.privacy loaded alone (stdlib only), without the package's DB imports."""
    spec = importlib.util.spec_from_file_location("wm_privacy", "/opt/walter-memory/walter_memory/privacy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _token() -> str:
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith("WALTER_MEMORY_GATEWAY_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def memory_context(query: str, caller: str, session_id: str) -> str:
    if os.environ.get("WALTER_HOOK_CONTEXT", "on") == "off":
        return ""
    q = (query or "").strip()
    if len(q.split()) < MIN_WORDS or q.startswith("/"):
        return ""
    import httpx
    r = httpx.post(f"{GATEWAY}/v1/context", headers={"Authorization": f"Bearer {_token()}"}, timeout=8,
                   json={"query": q[:4000], "budget": BUDGET, "include_profile": False, "caller": caller,
                         "mode": "on", "session_id": session_id or None})
    r.raise_for_status()
    text = (r.json().get("text") or "").strip()
    if not text:
        return ""
    detect = _privacy().detect               # second net: the engine is cloud-safe, drop any line that looks secret
    lines = [l for l in text.splitlines() if not any(cat == "secret" for cat, _ in detect(l))]
    return HEADER + "\n" + "\n".join(lines)


def journal(transcript: str | None, *, wait: bool, runtime_flag: str | None = None) -> None:
    args = CONNECTOR + (["--file", transcript] if transcript else [runtime_flag] if runtime_flag else [])
    if wait:
        r = subprocess.run(args, capture_output=True, text=True, timeout=25)
        if r.returncode:
            log(f"journal failed: {(r.stderr or r.stdout).strip()[-300:]}")
    else:
        with open(os.devnull, "wb") as null:
            subprocess.Popen(args, stdin=null, stdout=null, stderr=null, start_new_session=True)


def claude_code(ev: dict) -> dict | None:
    name, sid = ev.get("hook_event_name"), ev.get("session_id") or ""
    if name == "SessionStart":
        line = (f"Cette session est journalisée dans la mémoire W.Alter (core.events, source claude_code, "
                f"thread_id={sid}).")
        if ev.get("source") == "compact":
            line += (" La conversation vient d'être compactée : pour retrouver le texte exact d'un message antérieur, "
                     f"appelle memory_events(thread_id=\"{sid}\", text=\"<mots-clés>\").")
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": line}}
    if name == "UserPromptSubmit":
        ctx = memory_context(ev.get("prompt") or "", "claude-code-hook", sid)
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}} if ctx else None
    if name == "PreCompact":
        journal(ev.get("transcript_path"), wait=True)
    elif name in ("Stop", "SessionEnd", "SubagentStop"):
        journal(ev.get("transcript_path"), wait=False)
    return None


def hermes(ev: dict) -> dict | None:
    if ev.get("hook_event_name") == "pre_llm_call":
        msg = (ev.get("extra") or {}).get("user_message")
        ctx = memory_context(msg if isinstance(msg, str) else "", "hermes-shell-hook", ev.get("session_id") or "")
        return {"context": ctx} if ctx else None
    return None


def main() -> int:
    t0 = time.perf_counter()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "codex-notify":
            note = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
            if note.get("type") == "agent-turn-complete":
                journal(None, wait=False, runtime_flag="--codex")
            return 0
        ev = json.loads(sys.stdin.read() or "{}")
        name = ev.get("hook_event_name") or ""
        out = hermes(ev) if name and name[0].islower() else claude_code(ev)   # Hermes events are snake_case
        if out:
            print(json.dumps(out, ensure_ascii=False))
        if name in ("UserPromptSubmit", "pre_llm_call"):
            log(f"{name} context={'yes' if out else 'no'} {round((time.perf_counter() - t0) * 1000)}ms")
    except Exception as e:                       # fail-open: never block the agent
        log(f"error {type(e).__name__}: {str(e)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
