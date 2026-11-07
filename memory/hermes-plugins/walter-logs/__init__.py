"""walter-logs tools for Hermes (plugin; Hermes core is never patched).

The raw session log of every agent that works for Monsieur (Hermes and all its profiles, Claude Code, Codex, DSH)
lives in Postgres `walter_logs` (/opt/walter-memory, walter_memory/logs.py). These tools read it through the
walter-memory CLI in cloud-safe mode: secrets are masked at write, local-only content is hidden, redacted content is
pseudonymised. Hermes' own `session_search` only sees this profile's state.db; these see every runtime.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Mapping

logger = logging.getLogger(__name__)
CLI = os.environ.get("WALTER_MEMORY_CLI", "/usr/local/bin/walter-memory")
TYPES = ["user/message", "assistant/message", "assistant/reasoning", "tool/call", "tool/result", "compaction/summary",
         "model/selection", "system/message"]


async def _cli(*args: str, timeout: int = 60) -> str:
    proc = await asyncio.create_subprocess_exec(CLI, "logs", *args, "--cloud-safe", stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        return "walter-logs error: " + (err or out).decode("utf-8", "replace")[-500:]
    return out.decode("utf-8", "replace")


def _flags(args: Mapping[str, Any], names: tuple[str, ...]) -> list[str]:
    out = []
    for n in names:
        v = args.get(n)
        if v not in (None, ""):
            out += [f"--{n.replace('_', '-')}" if n != "event_type" else "--type", str(v)]
    return out


async def _search(args: Mapping[str, Any], **_: Any) -> str:
    try:
        return await _cli("search", str(args.get("query") or ""), "--limit", str(min(int(args.get("limit") or 20), 100)),
                          *_flags(args, ("runtime", "event_type", "tool", "session", "since", "until")))
    except Exception as exc:  # noqa: BLE001
        return f"walter_logs_search: {exc}"


async def _timeline(args: Mapping[str, Any], **_: Any) -> str:
    try:
        extra = ["--seq", str(int(args["seq"]))] if args.get("seq") not in (None, "", -1) else []
        return await _cli("timeline", str(args["session"]), *extra,
                          *_flags(args, ("before", "after", "event_type", "max_chars")))
    except Exception as exc:  # noqa: BLE001
        return f"walter_logs_timeline: {exc}"


async def _get(args: Mapping[str, Any], **_: Any) -> str:
    try:
        return await _cli("get", str(args["session"]), "--seq", str(int(args["seq"])))
    except Exception as exc:  # noqa: BLE001
        return f"walter_logs_get: {exc}"


SEARCH_SCHEMA = {
    "name": "walter_logs_search",
    "description": (
        "Search what Walter's agents DID in past sessions, any runtime (this Hermes and its other profiles, Claude "
        "Code, Codex, DSH): messages, reasoning, tool calls with full arguments, tool results in full, compaction "
        "summaries. Use it to find how something was done before, a past error and its fix, a command, a file path, "
        "a result already computed. Words (accent-insensitive) or an exact string. Each hit has a ref "
        "'session#seq': open the surrounding flow with walter_logs_timeline, the full event with walter_logs_get."),
    "parameters": {"type": "object", "properties": {
        "query": {"type": "string", "description": "Words or exact string; empty = latest events matching the filters."},
        "runtime": {"type": "string", "enum": ["hermes", "claude_code", "codex", "dsh"]},
        "event_type": {"type": "string", "enum": TYPES},
        "tool": {"type": "string", "description": "Tool name (part of it), e.g. terminal, Bash, walter_route."},
        "session": {"type": "string", "description": "Session id or part of it."},
        "since": {"type": "string", "description": "ISO date/time."},
        "until": {"type": "string", "description": "ISO date/time."},
        "limit": {"type": "integer", "description": "Max hits (default 20)."}}},
}
TIMELINE_SCHEMA = {
    "name": "walter_logs_timeline",
    "description": ("The flow of one agent session in order (request → reasoning → tool call → result → answer), "
                    "around an event (seq from a walter_logs_search ref) or the latest events."),
    "parameters": {"type": "object", "required": ["session"], "properties": {
        "session": {"type": "string", "description": "Session id (or part of it), from a search ref 'session#seq'."},
        "seq": {"type": "integer", "description": "Anchor event; omit for the latest events."},
        "before": {"type": "integer", "description": "Events before the anchor (default 5)."},
        "after": {"type": "integer", "description": "Events after the anchor (default 15)."},
        "event_type": {"type": "string", "enum": TYPES},
        "max_chars": {"type": "integer", "description": "Text per event (default 600)."}}},
}
GET_SCHEMA = {
    "name": "walter_logs_get",
    "description": "One walter-logs event in full (complete tool result, reasoning or message) with its linked call/result.",
    "parameters": {"type": "object", "required": ["session", "seq"], "properties": {
        "session": {"type": "string"}, "seq": {"type": "integer"}}},
}


def _available() -> bool:
    return os.path.exists(CLI)


def register(ctx: Any) -> None:
    if not callable(getattr(ctx, "register_tool", None)):
        logger.error("WALTER_LOGS_DEGRADED register_tool_missing")
        return
    for schema, handler, emoji in ((SEARCH_SCHEMA, _search, "🗂️"), (TIMELINE_SCHEMA, _timeline, "🧵"),
                                   (GET_SCHEMA, _get, "📄")):
        kwargs = {"name": schema["name"], "toolset": "walter-logs", "schema": schema, "handler": handler,
                  "check_fn": _available, "is_async": True, "emoji": emoji}
        try:
            ctx.register_tool(**kwargs)
        except TypeError:
            for k in ("emoji", "is_async", "toolset"):
                kwargs.pop(k, None)
            try:
                ctx.register_tool(**kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.error("WALTER_LOGS_DEGRADED register %s: %s", schema["name"], exc)
