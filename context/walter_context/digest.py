"""Compact renderings of tool traffic: pure functions of (tool, arguments, output, call id).

A digest tells the model what happened (which tool, on what, how big, did it fail) plus a short excerpt and a ref
for the full original, which stays in the session journal (walter_logs) and comes back with `context_recover`.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .config import Projection
from .wire import clip, one_line

# Arguments worth showing first, in this order (covers Hermes, Claude Code, Codex and MCP tool vocabularies).
SALIENT = ("path", "file_path", "command", "cmd", "query", "pattern", "url", "name", "skill", "session", "ref",
           "action", "goal", "prompt", "code")
# Tools whose output is reference material read on demand: the excerpt is pointless once the turn is over.
REFERENCE_TOOLS = {"skill_view", "skill_read", "walter_skill_read", "mcp__walter__skill_read", "tool_describe"}
# Tools whose useful part is usually at the end (errors, final status).
TAIL_TOOLS = {"terminal", "execute_code", "bash", "Bash", "shell", "exec_command"}


def _parse(text: str) -> Any:
    if text[:1] in "{[":
        try:
            return json.loads(text)
        except ValueError:
            return None
    return None


def args_summary(name: str, args: str, limit: int) -> str:
    """`tool(key=value, …)` with the salient arguments first; used by the record zone."""
    parsed = _parse(args)
    if not isinstance(parsed, dict):
        return f"{name}({one_line(args, limit)})" if args else name
    keys = [k for k in SALIENT if k in parsed] + sorted(k for k in parsed if k not in SALIENT)
    parts = []
    for k in keys:
        v = parsed[k]
        if v in (None, "", [], {}):
            continue
        v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
        parts.append(f"{k}={one_line(v, 120)}")
    return f"{name}({one_line(', '.join(parts), limit)})"


def clip_args(args: str, limit: int) -> str:
    """Compact zone: keep the call valid JSON while clipping long string values (file contents, code, patches)."""
    if len(args) <= limit:
        return args
    parsed = _parse(args)
    if not isinstance(parsed, dict):
        return json.dumps({"_clipped": one_line(args, limit)}, ensure_ascii=False)
    budget = max(40, limit // max(1, len(parsed)))
    out = {}
    for k in sorted(parsed):
        v = parsed[k]
        if isinstance(v, str) and len(v) > budget:
            v = v[:budget] + f"… [+{len(v) - budget} chars]"
        elif not isinstance(v, (str, int, float, bool)) and v is not None:
            s = json.dumps(v, ensure_ascii=False, sort_keys=True)
            v = s if len(s) <= budget else s[:budget] + f"… [+{len(s) - budget} chars]"
        out[k] = v
    return json.dumps(out, ensure_ascii=False, sort_keys=True)


def _status(parsed: Any) -> tuple[str, str]:
    """(body, status words) from the usual JSON envelopes of tool results."""
    if not isinstance(parsed, dict):
        return "", ""
    words = []
    for key in ("exit_code", "returncode", "status_code"):
        if parsed.get(key) not in (None, ""):
            words.append(f"exit {parsed[key]}")
            break
    if parsed.get("error"):
        words.append("error: " + one_line(str(parsed["error"]), 120))
    if parsed.get("success") is False:
        words.append("failed")
    body = next((parsed[k] for k in ("output", "content", "result", "text", "stdout") if isinstance(parsed.get(k), str)), "")
    return body, ", ".join(words)


_EXIT = re.compile(r'"(?:exit_code|returncode|status_code)"\s*:\s*(-?\d+)')
_ERROR = re.compile(r'"error"\s*:\s*"((?:[^"\\]|\\.){1,200})')
_FAILED = re.compile(r'"success"\s*:\s*false')


def status_of(output: str) -> str:
    """Status words of a tool output (exit code, error), without parsing it: envelopes put them at either end."""
    ends = output[:400] + "\n" + output[-400:] if len(output) > 800 else output
    words = []
    m = _EXIT.search(ends)
    if m:
        words.append(f"exit {m.group(1)}")
    m = _ERROR.search(ends)
    if m:
        words.append("error: " + one_line(m.group(1), 120))
    if _FAILED.search(ends):
        words.append("failed")
    return ", ".join(words)


def result(tool: str, output: str, ref: str, cfg: Projection) -> str:
    """Tool output as it appears in the compact zone (short outputs are kept verbatim)."""
    if len(output) <= cfg.tool_keep_chars:
        return output
    body, status = _status(_parse(output))
    body = body or output
    lines = body.count("\n") + 1
    head = f"[compacted {tool or 'tool'} output · {len(output):,} chars · {lines:,} lines"
    head += f" · {status}" if status else ""
    head += f" · full original: context_recover ref={ref}]" if ref else " · original in the session journal]"
    if tool in REFERENCE_TOOLS:
        return head + "\n" + one_line(body, min(160, cfg.excerpt_chars))
    if tool in TAIL_TOOLS:
        return head + "\n" + clip(body.strip(), cfg.excerpt_chars)
    return head + "\n" + one_line(body, cfg.excerpt_chars)
