#!/usr/local/bin/walter-python
"""walter_hook — W.Alter's automatic behaviours for any agent runtime (P8.3, plug ③ of a Walter module).

One script, several hosts (the wire format is Claude Code's, which Hermes' shell hooks also speak):

  Claude Code  SessionStart      → one line telling the agent its session is journaled (+ how to recover exact
                                   messages after a compaction: memory_events(thread_id=…))
               UserPromptSubmit  → budgeted W.Alter memory context for the prompt (cloud-safe, secrets dropped)
                                   + walter-context preflight in SHADOW (detached, records a ContextPlan in the
                                   instance, injects nothing; WALTER_HOOK_PREFLIGHT=off disables it)
                                   + the W.Alter skills that fit the message (walter-skills :8891, P10), in parallel
               PostToolUse(Failure)(Bash) → a FAILED command's output goes to the walter-skills policy (skills whose
                                   card lists that symptom, only on a real match); SessionStart also gets the domain map
               PreCompact        → journal the transcript synchronously, so the recovery pointer is true
               Stop / SessionEnd → journal the transcript in the background (connector agent_sessions)
                                   + bus turn.ended / session.ended
  Hermes       pre_llm_call      → same memory context, answered as {"context": …}
               `walter_hook.py hermes-skills` (config.yaml hooks.pre_llm_call): ONLY the walter-skills shortlist —
               Hermes keeps its own memory and its own skill index (parallel mode, P10)
               `walter_hook.py hermes-event` (config.yaml hooks): on_skill_lifecycle (content changes) → bus
               skill.changed; on_session_end (Hermes fires it after EVERY turn) → turn.ended; on_session_finalize
               → session.ended
  Codex        notify            → `walter_hook.py codex-notify '<json>'` (agent-turn-complete) → journal + turn.ended
  DeepSeek H.  dsh-hooks-claude-code (same events as Claude Code; runs inside dsh's workspace-write sandbox)

The Walter bus (walter_memory.bus, Postgres LISTEN/NOTIFY) is how modules hear about runtimes: this adapter turns
each runtime's own hook vocabulary into the same few events. subject = the session key used everywhere
("<runtime>/<account>/<id>", as in skills.retrievals and walter_logs), or the skill name.

Fail-open: any error → no output, exit 0, one line in ~/.hermes/logs/walter-hook.log. Never prints secrets.
Per-prompt context can be switched off with WALTER_HOOK_CONTEXT=off; skills with WALTER_HOOK_SKILLS=off. All skill
decisions live in walter_skills.policy (the service); this file only transports.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

GATEWAY = os.environ.get("WALTER_MEMORY_URL", "http://127.0.0.1:8890")
CONNECTOR = ["walter-memory", "agent-sessions"]   # Walter Memory CLI on the PATH
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
    """walter_memory.privacy (stdlib only; the package imports its DB modules lazily)."""
    from walter_memory import privacy
    return privacy


def _token() -> str:
    """The gateway credential, read by Walter Memory's public client."""
    from walter_memory import client
    return client.token()


MACHINE_PROMPTS = ("<task-notification", "[SYSTEM NOTIFICATION", "Another Claude session sent a message",
                   "[Subagent hand-back]", "<system-reminder", "[ASYNC DELEGATION", "[CONTEXT COMPACTION",
                   "[System:", "[SYSTEM:")


def machine_prompt(q: str) -> bool:
    """Harness/subagent notifications delivered as prompts: no memory or skills for those."""
    head = (q or "").lstrip()[:400]
    return any(m in head for m in MACHINE_PROMPTS)


def memory_context(query: str, caller: str, session_id: str) -> str:
    if os.environ.get("WALTER_HOOK_CONTEXT", "on") == "off" or machine_prompt(query):
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


def previous_turn(transcript: str | None) -> str:
    """Last user + assistant texts of a Claude Code / dsh transcript (JSONL), tail only, best effort."""
    if not transcript:
        return ""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 300_000))
            lines = f.read().decode("utf-8", "replace").splitlines()[1:]
    except OSError:
        return ""
    found: dict[str, str] = {}
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        role = ev.get("type")
        if role not in ("user", "assistant") or role in found:
            continue
        content = (ev.get("message") or {}).get("content")
        text = content if isinstance(content, str) else " ".join(
            b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
        if text.strip() and not text.lstrip().startswith("<"):
            found[role] = text.strip()
        if len(found) == 2:
            break
    return f"{found.get('user', '')[-400:]}\n{found.get('assistant', '')[-400:]}".strip()


def previous_exchange(transcript: str | None) -> dict | None:
    """Last user and assistant texts of a Claude Code / dsh transcript with the age of that user message (seconds)."""
    if not transcript:
        return None
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 300_000))
            lines = f.read().decode("utf-8", "replace").splitlines()[1:]
    except OSError:
        return None
    found: dict[str, tuple[str, str]] = {}
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        role = ev.get("type")
        if role not in ("user", "assistant") or role in found:
            continue
        content = (ev.get("message") or {}).get("content")
        text = content if isinstance(content, str) else " ".join(
            b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
        if text.strip() and not text.lstrip().startswith("<"):
            found[role] = (text.strip(), ev.get("timestamp") or "")
        if len(found) == 2:
            break
    if "user" not in found:
        return None
    age = None
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(found["user"][1].replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        pass
    return {"message": found["user"][0][-1500:], "answer": found.get("assistant", ("", ""))[0][-1500:], "age_s": age}


def preflight_shadow(prompt: str, runtime: str, session_id: str, transcript: str | None) -> None:
    """walter-context lot 4 in shadow: the preflight runs detached and records its ContextPlan in the instance;
    nothing is injected and the prompt is not delayed. A message that looks like it holds a secret stays local."""
    if os.environ.get("WALTER_HOOK_PREFLIGHT", "shadow") == "off" or machine_prompt(prompt) or runtime == "dsh":
        return
    secret = any(cat == "secret" for cat, _ in _privacy().detect(prompt))
    prev = previous_exchange(transcript)
    thread = f"session:{session_id}" if session_id else None
    if prev:
        prev["thread_id"] = thread
    req = {"turn_id": f"{session_id}:{int(time.time() * 1000)}", "message": prompt[:6000], "previous": prev,
           "runtime": runtime, "session_id": session_id, "default_thread": thread,
           "candidates": [{"id": thread, "title": "this session"}] if thread else [],
           "privacy_class": "local_only" if secret else "cloud_allowed"}
    p = subprocess.Popen(["walter-context-preflight", "--shadow"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    p.stdin.write(json.dumps(req, ensure_ascii=False).encode())
    p.stdin.close()


def skills(kind: str, message: str, runtime: str, session_id: str, context: str = "", first_turn: bool = False) -> str:
    """walter-skills exposure (P10). The policy lives in the service; this adapter only transports (fail-open)."""
    if os.environ.get("WALTER_HOOK_SKILLS", "on") == "off":
        return ""
    from walter_skills import client
    return client.expose(kind, message, context=context, session_id=session_id or None, runtime=runtime,
                         first_turn=first_turn).get("text", "")


def journal(transcript: str | None, *, wait: bool, runtime_flag: str | None = None) -> None:
    args = CONNECTOR + ([runtime_flag] if runtime_flag else ["--file", transcript] if transcript else [])
    if wait:
        r = subprocess.run(args, capture_output=True, text=True, timeout=25)
        if r.returncode:
            log(f"journal failed: {(r.stderr or r.stdout).strip()[-300:]}")
    else:
        with open(os.devnull, "wb") as null:
            subprocess.Popen(args, stdin=null, stdout=null, stderr=null, start_new_session=True)


def emit(type: str, source: str, subject: str | None, payload: dict | None = None) -> None:
    """One event on the Walter bus (fail-open, ~10 ms)."""
    try:
        from walter_memory import bus
        bus.emit(type, source, subject, payload)
    except Exception as e:
        log(f"bus {type} failed {type(e).__name__}: {str(e)[:160]}")


SKILL_CONTENT_ACTIONS = {"created", "patched", "edited", "installed", "archived", "restored"}


def hermes_event(ev: dict) -> None:
    """Hermes lifecycle hooks → the Walter bus (the Hermes adapter; Hermes core is never patched)."""
    name, sid, extra = ev.get("hook_event_name"), ev.get("session_id") or "", ev.get("extra") or {}
    if name == "on_skill_lifecycle" and extra.get("action") in SKILL_CONTENT_ACTIONS and extra.get("skill_name"):
        emit("skill.changed", "hermes", str(extra["skill_name"]),
             {"action": extra["action"], "provenance": extra.get("provenance"),
              "session_id": f"hermes/main/{sid}" if sid else None})
    elif name == "on_session_end" and sid:
        emit("turn.ended", "hermes", f"hermes/main/{sid}",
             {k: extra.get(k) for k in ("completed", "failed", "interrupted", "turn_exit_reason", "model", "platform")})
    elif name == "on_session_finalize" and sid:
        emit("session.ended", "hermes", f"hermes/main/{sid}", {"platform": extra.get("platform")})


def runtime_of(ev: dict) -> str:
    """Claude Code and DeepSeek Harness both speak this format; dsh session ids are 'session-<uuid>'."""
    sid, path = ev.get("session_id") or "", ev.get("transcript_path") or ""
    return "dsh" if sid.startswith("session-") or path.startswith("/opt/dsh/") else "claude_code"


OWN = re.compile(r"<walter-context>.*?</walter-context>", re.S)


def ours(runtime: str, text: str) -> str:
    """dsh fires UserPromptSubmit before EVERY step with all pending messages glued together — including the contexts
    this hook injected (map, error skills). Our contexts are tagged there so the prompt can be cleaned of them."""
    return f"<walter-context>\n{text}\n</walter-context>" if text and runtime == "dsh" else text


def claude_code(ev: dict) -> dict | None:
    name, sid, runtime = ev.get("hook_event_name"), ev.get("session_id") or "", runtime_of(ev)
    if name == "SessionStart":
        line = (f"Cette session est journalisée dans la mémoire W.Alter (core.events, source {runtime}, "
                f"thread_id={sid}).")
        if ev.get("source") == "compact":
            line += (" La conversation vient d'être compactée : pour retrouver le texte exact d'un message antérieur, "
                     f"appelle memory_events(thread_id=\"{sid}\", text=\"<mots-clés>\").")
        tier0 = skills("session_start", "", runtime, f"{runtime}/vm/{sid}" if sid else "")
        return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                       "additionalContext": ours(runtime, line + ("\n\n" + tier0 if tier0 else ""))}}
    if name == "UserPromptSubmit":
        from concurrent.futures import ThreadPoolExecutor
        caller, prompt = f"{runtime.replace('_', '-')}-hook", OWN.sub(" ", ev.get("prompt") or "").strip()
        if not prompt:  # a dsh step whose only new messages are our own contexts or tool results
            return None
        try:
            preflight_shadow(prompt, runtime, sid, ev.get("transcript_path"))
        except Exception as e:  # noqa: BLE001 — shadow mode never affects the prompt
            log(f"preflight shadow error {type(e).__name__}: {str(e)[:160]}")
        with ThreadPoolExecutor(2) as ex:  # memory and skills in parallel; each fails open on its own
            fm = ex.submit(memory_context, prompt, caller, sid)
            fs = ex.submit(skills, "message", prompt, runtime, f"{runtime}/vm/{sid}" if sid else "",
                           previous_turn(ev.get("transcript_path")))
            parts = []
            for f, label in ((fm, "memory"), (fs, "skills")):
                try:
                    if f.result(timeout=8):
                        parts.append(f.result())
                except Exception as e:
                    log(f"{label} error {type(e).__name__}: {str(e)[:160]}")
        ctx = ours(runtime, "\n\n".join(parts))
        return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}} if ctx else None
    if name in ("PostToolUse", "PostToolUseFailure"):
        ctx = ours(runtime, error_skills(ev, runtime, sid))
        return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": ctx}} if ctx else None
    if name == "PreCompact":
        journal(ev.get("transcript_path"), wait=True)
    elif name in ("Stop", "SessionEnd", "SubagentStop"):
        # dsh runs hooks in a sandbox that reaps detached children: journal synchronously there (~1 s, incremental)
        journal(ev.get("transcript_path"), wait=runtime == "dsh", runtime_flag="--dsh" if runtime == "dsh" else None)
        if sid and name != "SubagentStop":
            emit("session.ended" if name == "SessionEnd" else "turn.ended", runtime, f"{runtime}/vm/{sid}",
                 {"reason": ev.get("reason")} if name == "SessionEnd" else None)
    return None


def failed_output(ev: dict) -> str:
    """The text of a shell command that FAILED, else "" (a successful command whose output merely mentions
    'Traceback' is not an error). Claude Code: PostToolUseFailure carries the error; on PostToolUse only stderr counts
    (a pipe can hide the exit code). DSH: its bash result ends with an '[exit code: N]' marker on failure."""
    if ev.get("tool_name") not in ("Bash", "bash"):
        return ""
    if ev.get("hook_event_name") == "PostToolUseFailure":
        return str(ev.get("error") or "")
    resp = ev.get("tool_response") or {}
    if isinstance(resp, dict):
        return str(resp.get("stderr") or "")
    resp = str(resp)
    return resp if "[exit code:" in resp[-200:] else ""


def error_skills(ev: dict, runtime: str, sid: str) -> str:
    """After a failed shell command: its output goes to the policy, which answers only on a real symptom match."""
    out = failed_output(ev).strip()
    if not out:
        return ""
    return skills("error", out[-1500:], runtime, f"{runtime}/vm/{sid}" if sid else "",
                  context=str((ev.get("tool_input") or {}).get("command") or "")[:300])


def hermes(ev: dict) -> dict | None:
    if ev.get("hook_event_name") == "pre_llm_call":
        msg = (ev.get("extra") or {}).get("user_message")
        ctx = memory_context(msg if isinstance(msg, str) else "", "hermes-shell-hook", ev.get("session_id") or "")
        return {"context": ctx} if ctx else None
    return None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("text", "input_text"))
    return ""


def hermes_skills(ev: dict) -> dict | None:
    """Hermes pre_llm_call → walter-skills shortlist only, appended by Hermes to the user message."""
    if ev.get("hook_event_name") != "pre_llm_call":
        return None
    extra = ev.get("extra") or {}
    msg = extra.get("user_message")
    msg = _text(msg)
    hist = [m for m in (extra.get("conversation_history") or []) if isinstance(m, dict)]
    prev_user = prev_asst = ""
    for m in reversed(hist[:-1] if hist and _text(hist[-1].get("content")) == msg else hist):
        role, txt = m.get("role"), _text(m.get("content")).strip()
        if role == "assistant" and txt and not prev_asst:
            prev_asst = txt
        elif role == "user" and txt and not prev_user:
            prev_user = txt
        if prev_user and prev_asst:
            break
    sid = ev.get("session_id") or ""
    ctx = skills("message", msg, "hermes", f"hermes/main/{sid}" if sid else "",
                 context=f"{prev_user[-400:]}\n{prev_asst[-400:]}".strip(), first_turn=bool(extra.get("is_first_turn")))
    return {"context": ctx} if ctx else None


def main() -> int:
    t0 = time.perf_counter()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "codex-notify":
            note = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
            if note.get("type") == "agent-turn-complete":
                journal(None, wait=False, runtime_flag="--codex")
                # the notify payload has no originator: the session key is completed by walter_logs ("codex/<originator>/<id>")
                emit("turn.ended", "codex", note.get("thread-id"), {"turn_id": note.get("turn-id"), "cwd": note.get("cwd")})
            return 0
        ev = json.loads(sys.stdin.read() or "{}")
        name = ev.get("hook_event_name") or ""
        if len(sys.argv) > 1 and sys.argv[1] == "hermes-skills":
            out = hermes_skills(ev)
        elif len(sys.argv) > 1 and sys.argv[1] == "hermes-event":
            out = hermes_event(ev)
        else:
            out = hermes(ev) if name and name[0].islower() else claude_code(ev)   # Hermes events are snake_case
        if out:
            print(json.dumps(out, ensure_ascii=False))
        if name in ("UserPromptSubmit", "pre_llm_call") or (name.startswith("PostToolUse") and out):
            log(f"{name} context={'yes' if out else 'no'} {round((time.perf_counter() - t0) * 1000)}ms")
    except Exception as e:                       # fail-open: never block the agent
        log(f"error {type(e).__name__}: {str(e)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
