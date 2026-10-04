#!/usr/bin/env python3
"""Agent sessions connector (P8.2): Claude Code and Codex sessions → core.events, like the Hermes connector.

Every runtime that works for Monsieur writes into the same journal (DeepSeek-Harness principle: the session log
is the source of truth, whatever the agent loop). Reads the runtimes' own append-only JSONL transcripts:
  - Claude Code: ~/.claude/projects/<project>/<session>.jsonl
  - Codex:       ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
and records conversation.started, message.sent (Monsieur, or the delegating agent for `codex exec`),
message.received (the agent's visible answer) and tool.called metadata (name, summarised args, status, output
size, reference) — never tool outputs, never hidden reasoning, never system-injected rows (reminders, slash-command
echoes, compaction summaries).

Triggered by the runtimes' hooks (Claude Code Stop/PreCompact/SessionEnd, Codex `notify`) through
/opt/walter-core/hooks/walter_hook.py — no timer. Incremental per file (byte offset of the last complete line) and
idempotent (source_id = line uuid / byte offset), so any run catches up whatever earlier runs missed.

  - DeepSeek Harness: /opt/dsh/home/sessions/<workspace>/session-*/session.v4.jsonl.zstd
Usage: agent_sessions.py [--claude] [--codex] [--dsh] [--file PATH]     (no flag = every runtime, every file)
"""
from __future__ import annotations

import argparse
import fcntl
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CONNECTOR = "agent_sessions"
CLAUDE_DIR = Path("/root/.claude/projects")
CODEX_DIR = Path("/root/.codex/sessions")
DSH_DIR = Path("/opt/dsh/home/sessions")
LOCK = Path("/run/lock/walter-agent-sessions.lock")
ROOTS = {"claude": CLAUDE_DIR, "codex": CODEX_DIR, "dsh": DSH_DIR}
MONSIEUR = {"external_id": "monsieur", "display_name": "Monsieur", "is_self": True}
AGENTS = {"claude_code": {"external_id": "claude-code", "display_name": "Claude Code"},
          "codex": {"external_id": "codex", "display_name": "Codex"},
          "dsh": {"external_id": "dsh", "display_name": "DeepSeek Harness"}}
DELEGATOR = {"external_id": "delegator", "display_name": "Agent délégant (codex exec)"}
CODEX_INTERACTIVE = {"codex_cli_rs", "codex-tui", "codex_vscode", "codex_desktop"}
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
INJECTED = ("<local-command-", "<command-name>", "<command-message>", "<task-notification>", "Caveat: The messages")
BATCH = 2000


def summarise_args(args, limit: int = 300) -> str | None:
    if args in (None, "", {}):
        return None
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            pass
    raw = (", ".join(f"{k}={json.dumps(v, ensure_ascii=False)[:120]}" for k, v in args.items())
           if isinstance(args, dict) else str(args))
    return raw[:limit] + ("…" if len(raw) > limit else "")


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text"))
    return ""


def _chars(content) -> int:
    return len(content) if isinstance(content, str) else len(json.dumps(content, ensure_ascii=False))


# ───────────────────────── parsers (pure: line dict + state → events) ─────────────────────────
def parse_claude(d: dict, offset: int, st: dict) -> list[dict]:
    """One Claude Code transcript line. st (persisted per file): sid, model, title, last_user, pending tool_uses."""
    kind, sid = d.get("type"), d.get("sessionId") or st.get("sid")
    if kind == "custom-title" and d.get("customTitle"):
        st["title"] = d["customTitle"]
    if kind not in ("user", "assistant") or not sid or d.get("isSidechain"):
        return []
    out, ts, uid = [], d.get("timestamp"), d.get("uuid") or f"{sid}:{offset}"
    base = {"source": "claude_code", "source_account": "vm", "thread_id": sid, "occurred_at": ts}
    chat = {"id": sid, "type": "agent", "network": "claude-code"}
    if sid not in st.setdefault("started", []):
        st["started"] = (st["started"] + [sid])[-20:]
        out.append({**base, "event_type": "conversation.started", "source_id": f"session:{sid}:start",
                    "content": st.get("title"), "actor": {**AGENTS["claude_code"], "account": "vm"},
                    "payload": {"platform": "claude-code", "model": (d.get("message") or {}).get("model") or st.get("model"),
                                "title": st.get("title"), "parent_session_id": None}})
        st["sid"] = sid
    msg = d.get("message") or {}
    content = msg.get("content")
    if kind == "assistant":
        st["model"] = msg.get("model") or st.get("model")
        for b in content if isinstance(content, list) else []:
            if b.get("type") == "tool_use":
                st.setdefault("pending", {})[b.get("id")] = [b.get("name"), summarise_args(b.get("input"))]
        text = _text(content).strip()
        if text and not d.get("isApiErrorMessage"):
            out.append({**base, "event_type": "message.received", "source_id": f"msg:{uid}", "content": text,
                        "reply_to": st.get("last_user"), "actor": {**AGENTS["claude_code"], "account": "vm"},
                        "payload": {"chat": chat, "session_id": sid, "message_id": uid, "role": "assistant",
                                    "model": st.get("model"), "attachments": []}})
        return out
    if d.get("isMeta") or d.get("isCompactSummary"):
        return out
    for b in content if isinstance(content, list) else []:
        if b.get("type") == "tool_result":
            name, args = st.get("pending", {}).pop(b.get("tool_use_id"), [None, None])
            out.append({**base, "event_type": "tool.called", "source_id": f"tool:{uid}:{b.get('tool_use_id')}",
                        "actor": {**AGENTS["claude_code"], "account": "vm"},
                        "payload": {"tool": name or "unknown", "args_summary": args,
                                    "status": "error" if b.get("is_error") else "ok", "output_chars": _chars(b.get("content")),
                                    "output_ref": f"claude_code:{sid}:{uid}", "session_id": sid,
                                    "call_id": b.get("tool_use_id"), "automated": False}})
    origin = (d.get("origin") or {}).get("kind")
    text = REMINDER.sub("", _text(content)).strip()
    if not text or text.startswith(INJECTED) or (origin and origin != "human"):
        return out
    out.append({**base, "event_type": "message.sent", "source_id": f"msg:{uid}", "content": text,
                "actor": {**MONSIEUR, "account": "vm"},
                "payload": {"chat": chat, "session_id": sid, "message_id": uid, "role": "user", "cwd": d.get("cwd"),
                            "attachments": []}})
    st["last_user"] = f"msg:{uid}"
    return out


def parse_codex(d: dict, offset: int, st: dict) -> list[dict]:
    """One Codex rollout line. st: sid, originator, model, last_user, pending function calls."""
    kind, p, ts = d.get("type"), d.get("payload") or {}, d.get("timestamp")
    if kind == "session_meta":
        st.update(sid=p.get("id"), originator=p.get("originator") or p.get("source"), cwd=p.get("cwd"))
    sid = st.get("sid")
    if not sid:
        return []
    interactive = st.get("originator") in CODEX_INTERACTIVE
    base = {"source": "codex", "source_account": st.get("originator") or "unknown", "thread_id": sid,
            "occurred_at": ts or p.get("timestamp")}
    agent = {**AGENTS["codex"], "account": base["source_account"]}
    chat = {"id": sid, "type": "agent", "network": "codex"}
    ref = f"{sid}:{offset}"
    if kind == "session_meta":
        return [{**base, "event_type": "conversation.started", "source_id": f"session:{sid}:start", "actor": agent,
                 "payload": {"platform": "codex", "model": None, "title": None, "parent_session_id": None,
                             "originator": st.get("originator"), "cwd": st.get("cwd"), "cli_version": p.get("cli_version")}}]
    if kind == "turn_context":
        st["model"] = p.get("model") or st.get("model")
        return []
    ptype = p.get("type")
    if kind == "event_msg" and ptype == "user_message" and (p.get("message") or "").strip():
        st["last_user"] = f"msg:{ref}"
        return [{**base, "event_type": "message.sent", "source_id": f"msg:{ref}", "content": p["message"].strip(),
                 "actor": {**(MONSIEUR if interactive else DELEGATOR), "account": base["source_account"]},
                 "payload": {"chat": chat, "session_id": sid, "message_id": ref, "role": "user", "cwd": st.get("cwd"),
                             "automated": not interactive, "attachments": []}}]
    if kind == "event_msg" and ptype == "agent_message" and (p.get("message") or "").strip():
        return [{**base, "event_type": "message.received", "source_id": f"msg:{ref}", "content": p["message"].strip(),
                 "reply_to": st.get("last_user"), "actor": agent,
                 "payload": {"chat": chat, "session_id": sid, "message_id": ref, "role": "assistant",
                             "model": st.get("model"), "attachments": []}}]
    if kind == "response_item" and ptype in ("function_call", "custom_tool_call", "local_shell_call"):
        st.setdefault("pending", {})[p.get("call_id") or p.get("id")] = [
            p.get("name") or ptype, summarise_args(p.get("arguments") or p.get("input") or p.get("action"))]
    if kind == "response_item" and ptype in ("function_call_output", "custom_tool_call_output"):
        name, args = st.get("pending", {}).pop(p.get("call_id"), [None, None])
        out = p.get("output")
        failed = isinstance(out, dict) and out.get("success") is False
        return [{**base, "event_type": "tool.called", "source_id": f"tool:{ref}", "actor": agent,
                 "payload": {"tool": name or "unknown", "args_summary": args, "status": "error" if failed else "ok",
                             "output_chars": _chars(out), "output_ref": f"codex:{ref}", "session_id": sid,
                             "call_id": p.get("call_id"), "automated": not interactive}}]
    return []


def parse_dsh(d: dict, idx: int, st: dict) -> list[dict]:
    """One DeepSeek Harness session-log event (session.v4.jsonl.zstd). Only human `user/message` rows are Monsieur's
    words (hook context, instructions, skill catalogue and runtime snapshots are injected rows)."""
    kind, data = d.get("type"), d.get("data") or {}
    if kind == "session":
        st.update(sid=d.get("id"), cwd=d.get("cwd"))
    sid = st.get("sid")
    if not sid:
        return []
    ms = d.get("time") or d.get("createdAt")
    ts = datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None
    base = {"source": "dsh", "source_account": "vm", "thread_id": sid, "occurred_at": ts}
    agent = {**AGENTS["dsh"], "account": "vm"}
    chat = {"id": sid, "type": "agent", "network": "dsh"}
    ref = f"{sid}:{d.get('seq', idx)}"
    if kind == "session":
        return [{**base, "event_type": "conversation.started", "source_id": f"session:{sid}:start", "actor": agent,
                 "payload": {"platform": "dsh", "model": None, "title": None, "parent_session_id": None, "cwd": st.get("cwd"),
                             "delegation_depth": d.get("delegationDepth")}}]
    if kind == "request/context":
        st["model"] = f"{data.get('provider')}/{data.get('model')}"
    if kind == "tool/call":
        st.setdefault("pending", {})[data.get("callId")] = [data.get("name"), summarise_args(data.get("arguments"))]
    msg = data.get("message") or {}
    if kind == "user/message" and (data.get("source") or {}).get("kind") == "user":
        text = _text(data.get("content")).strip()
        if not text:
            return []
        st["last_user"] = f"msg:{ref}"
        return [{**base, "event_type": "message.sent", "source_id": f"msg:{ref}", "content": text,
                 "actor": {**MONSIEUR, "account": "vm"},
                 "payload": {"chat": chat, "session_id": sid, "message_id": ref, "role": "user", "cwd": st.get("cwd"),
                             "attachments": []}}]
    if kind == "assistant/message":
        text = _text(msg.get("content")).strip()
        served = ((msg.get("source") or {}).get("replayState") or {}).get("response", {}).get("responseModel")
        return [{**base, "event_type": "message.received", "source_id": f"msg:{ref}", "content": text,
                 "reply_to": st.get("last_user"), "actor": agent,
                 "payload": {"chat": chat, "session_id": sid, "message_id": ref, "role": "assistant",
                             "model": st.get("model"), "served_by": served, "attachments": []}}] if text else []
    if kind == "tool/result":
        call = msg.get("toolCallId")
        name, args = st.get("pending", {}).pop(call, [None, None])
        return [{**base, "event_type": "tool.called", "source_id": f"tool:{ref}", "actor": agent,
                 "payload": {"tool": name or "unknown", "args_summary": args, "status": "error" if msg.get("isError") else "ok",
                             "output_chars": _chars(msg.get("content")), "output_ref": f"dsh:{ref}", "session_id": sid,
                             "call_id": call, "automated": False}}]
    return []


PARSERS = {"claude": parse_claude, "codex": parse_codex, "dsh": parse_dsh}


def read_complete_lines(path: Path, offset: int, max_bytes: int = 64 << 20):
    """Yield (line_offset, dict) for complete lines after offset; returns via StopIteration value the new offset."""
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read(max_bytes)
    end = data.rfind(b"\n") + 1
    pos = offset
    for raw in data[:end].split(b"\n")[:-1]:
        line_at, pos = pos, pos + len(raw) + 1
        try:
            yield line_at, json.loads(raw)
        except ValueError:
            continue
    return offset + end


def read_zstd_lines(path: Path, done: int):
    """dsh logs are zstd-compressed JSONL (one frame per flush): decompress whole, skip the `done` first lines;
    returns the new line count. A frame still being written is left for the next run."""
    import zstandard
    with path.open("rb") as f:
        try:
            raw = zstandard.ZstdDecompressor().stream_reader(f, read_across_frames=True).read()
        except zstandard.ZstdError:
            return done
    complete = raw.split(b"\n")[:-1]          # the last piece is empty or a partial line
    for i in range(done, len(complete)):
        try:
            yield i, json.loads(complete[i])
        except ValueError:
            continue
    return max(done, len(complete))


# ───────────────────────── driver ─────────────────────────
def files(runtime: str) -> list[Path]:
    if runtime == "claude":
        return sorted(CLAUDE_DIR.glob("*/*.jsonl"))
    if runtime == "dsh":
        return sorted(DSH_DIR.glob("*/session-*/session.v4.jsonl.zstd"))
    return sorted(CODEX_DIR.glob("*/*/*/rollout-*.jsonl"))


def sync_file(runtime: str, path: Path) -> tuple[int, int]:
    from walter_memory import events, ingestion
    from walter_memory.db import connection
    stream = f"{runtime}:{path}"
    cur = ingestion.get_checkpoint(CONNECTOR, stream)
    offset, st = int(cur.get("offset", 0)), cur.get("state") or {}
    size = path.stat().st_size
    if runtime == "dsh":                      # compressed: offset = lines done; size guards needless decompression
        if size == cur.get("size"):
            return 0, 0
        gen = read_zstd_lines(path, offset)
    else:
        if size < offset:                     # truncated/rewritten: start over (idempotent)
            offset, st = 0, {}
        if size == offset:
            return 0, 0
        gen = read_complete_lines(path, offset)
    batch, last_ts = [], None
    try:
        while True:
            at, d = next(gen)
            evs = PARSERS[runtime](d, at, st)
            batch += evs
            last_ts = next((e["occurred_at"] for e in reversed(evs) if e.get("occurred_at")), last_ts)
    except StopIteration as stop:
        new_offset = stop.value
    if len(st.get("pending", {})) > 500:      # tool calls whose result never came (crash): keep the newest only
        st["pending"] = dict(list(st["pending"].items())[-500:])
    inserted = 0
    with connection() as conn:
        for i in range(0, len(batch), BATCH):
            inserted += events.record_events(batch[i:i + BATCH], conn=conn)["inserted"]
        ingestion.set_checkpoint(CONNECTOR, stream, {"offset": new_offset, "state": st, "size": size},
                                 last_item_at=last_ts, conn=conn)
    return len(batch), inserted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude", action="store_true")
    ap.add_argument("--codex", action="store_true")
    ap.add_argument("--dsh", action="store_true")
    ap.add_argument("--file", help="one transcript (runtime inferred from its path)")
    a = ap.parse_args()
    from walter_memory import ingestion
    try:
        lock_file = LOCK.open("a")
    except OSError:                           # sandboxed caller (dsh hooks): writable temp area only
        lock_file = (Path("/tmp") / LOCK.name).open("a")
    with lock_file as lock:
        for _ in range(120):                  # hooks fire often; runs queue up briefly instead of overlapping
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.5)
        else:
            print("agent_sessions: busy, skipped (next run catches up)")
            return 0
        if a.file:
            p = Path(a.file).resolve()
            runtime = next((r for r, root in ROOTS.items() if str(p).startswith(str(root) + "/")), None)
            targets = [(runtime, p)] if runtime else []          # unknown runtime: never parse with a wrong reader
        else:
            runtimes = [r for r, on in (("claude", a.claude), ("codex", a.codex), ("dsh", a.dsh)) if on] or list(ROOTS)
            targets = [(r, p) for r in runtimes for p in files(r)]
        total = ins = 0
        try:
            for runtime, p in targets:
                n, i = sync_file(runtime, p)
                total, ins = total + n, ins + i
        except Exception as e:
            ingestion.record_failure(CONNECTOR, f"{type(e).__name__}: {e}")
            raise
        ingestion.mark_success(CONNECTOR)
        print(f"agent_sessions: {len(targets)} file(s), {total} event(s) seen, {ins} new "
              f"({datetime.now(timezone.utc):%H:%M:%S}Z)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
