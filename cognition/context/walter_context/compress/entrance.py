"""entrance: a large tool output reduced when it ENTERS the context, before the model reads it.

The projection (`layers`) compacts tool outputs of finished turns; a host that keeps its own history (Claude Code)
never lets us rewrite those. What it does allow is replacing a tool output on its way in (PostToolUse
`updatedToolOutput`). Done there, the cut is cache-safe: nothing already sent is rewritten, the reduced text is what
gets cached.

The model is still working on that output, so the excerpt is generous compared to the compact zone: head, tail and
the "signal" lines in between (errors, failures), with line numbers, plus where the full original lives.

    walter-context-entrance            Claude Code PostToolUse event on stdin (sent by walter_hook)
    walter-context-entrance --report [--days N] [--json]

Modes (`[entrance].mode`): `shadow` records what would have been cut (numbers only, no content) in
`@instance/state/context/shadow/entrance-<day>.jsonl`; `off` does nothing. Replacing the output for real needs the
original to be journaled by the hook first: walter_logs records the text the model saw, so a reduced output would
lose its original. Until that exists, `on` is refused.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config import DEFAULT_PATH
from .wire import text_of

# Tools whose source can be queried again by the model itself (a file, a search): the hint says how.
REQUERYABLE = {"Read": "Read {path} with offset/limit", "Grep": "Grep again with a narrower pattern or head_limit",
               "Glob": "Glob with a narrower pattern"}


@dataclass(frozen=True)
class Entrance:
    mode: str
    min_chars: int
    head_chars: int
    tail_chars: int
    signal_lines: int
    signal_line_chars: int
    signal_words: tuple[str, ...]
    exempt_tools: tuple[str, ...]
    chars_per_token: float


def load(path: Path = DEFAULT_PATH) -> Entrance:
    raw = tomllib.loads(Path(path).read_text())["entrance"]
    raw["signal_words"] = tuple(raw["signal_words"])
    raw["exempt_tools"] = tuple(raw["exempt_tools"])
    if raw["mode"] not in ("off", "shadow"):
        raise ValueError(f"[entrance].mode={raw['mode']!r}: only off|shadow (no original journaling yet, see module doc)")
    return Entrance(**raw)


def output_text(tool: str, response: Any) -> str:
    """The text the model reads for a Claude Code tool response (shapes differ per tool); "" for images."""
    if isinstance(response, str):
        return response
    if isinstance(response, list):
        return text_of(response)
    if not isinstance(response, dict):
        return "" if response is None else json.dumps(response, ensure_ascii=False)
    if response.get("type") == "image" or response.get("isImage"):
        return ""
    if "stdout" in response or "stderr" in response:                     # Bash
        out, err = response.get("stdout") or "", response.get("stderr") or ""
        return out + ("\n" + err if err else "")
    file = response.get("file")
    if isinstance(file, dict) and isinstance(file.get("content"), str):  # Read
        return file["content"]
    for key in ("content", "result", "output", "text"):                  # Grep content mode, WebFetch, MCP
        value = response.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list) and value:
            return text_of(value)
    if isinstance(response.get("filenames"), list):                      # Glob, Grep files mode
        return "\n".join(map(str, response["filenames"]))
    return json.dumps(response, ensure_ascii=False)


def _take(lines: list[str], budget: int, from_end: bool = False) -> int:
    """How many lines fit in `budget` chars, counted from the start (or the end)."""
    n, used = 0, 0
    for line in (reversed(lines) if from_end else lines):
        used += len(line) + 1
        if used > budget:
            break
        n += 1
    return n


def reduce(tool: str, text: str, ref: str, cfg: Entrance, path: str = "") -> dict | None:
    """The reduced rendering of one tool output, or None when it is kept as is (small, or exempt tool)."""
    if len(text) < cfg.min_chars or tool in cfg.exempt_tools:
        return None
    lines = text.splitlines()
    head_n = _take(lines, cfg.head_chars)
    tail_n = min(_take(lines, cfg.tail_chars, from_end=True), max(0, len(lines) - head_n))
    middle = range(head_n, len(lines) - tail_n)
    words = re.compile("|".join(re.escape(w) for w in cfg.signal_words), re.IGNORECASE)
    signal = [i for i in middle if words.search(lines[i])][: cfg.signal_lines]
    if not head_n or not tail_n or head_n + tail_n >= len(lines):   # huge lines (minified JSON, base64): cut by chars
        body = (text[: cfg.head_chars] + f"\n[… {len(text) - cfg.head_chars - cfg.tail_chars:,} chars …]\n"
                + text[-cfg.tail_chars:])
    else:
        parts = lines[:head_n]
        last = head_n - 1
        for i in signal:
            parts.append(f"[… lines {last + 2}-{i} …]" if i > last + 1 else "")
            parts.append(f"{i + 1}: {lines[i][: cfg.signal_line_chars]}")
            last = i
        hidden = len(lines) - tail_n - (last + 1)
        if hidden > 0:
            parts.append(f"[… lines {last + 2}-{len(lines) - tail_n} ({hidden:,} lines) …]")
        parts += lines[len(lines) - tail_n:]
        body = "\n".join(p for p in parts if p != "")
    hint = REQUERYABLE.get(tool, "").format(path=path or "the file")
    where = f"full original: walter-context recover {ref} (MCP logs_get)" if ref else "original in the session journal"
    header = (f"[reduced {tool or 'tool'} output · {len(text):,} chars · {len(lines):,} lines · kept: head, tail"
              f"{f', {len(signal)} signal lines' if signal else ''} · {where}{' · or ' + hint if hint else ''}]")
    out = header + "\n" + body
    if len(out) >= len(text):
        return None
    return {"text": out, "orig_chars": len(text), "kept_chars": len(out), "lines": len(lines), "signal": len(signal)}


# ---- shadow records (numbers only) ---------------------------------------------------------------------------

def _folder() -> Path | None:
    override = os.environ.get("WALTER_CONTEXT_SHADOW_DIR")
    if override:
        return Path(override)
    try:
        root = subprocess.run(["walter", "instance", "path"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(root) / "state" / "context" / "shadow" if root else None


def record(row: dict, folder: Path | None = None) -> None:
    folder = folder or _folder()
    if folder is None:
        return
    folder.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    path = folder / f"entrance-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def handle(ev: dict, cfg: Entrance, folder: Path | None = None) -> dict | None:
    """One PostToolUse event → the shadow row (also recorded), or None when the output is kept."""
    if cfg.mode == "off":
        return None
    tool = ev.get("tool_name") or ""
    response = ev.get("tool_response")
    if isinstance(response, dict) and response.get("persistedOutputPath"):
        return None                      # the host already saved it to a file and showed the model a short preview
    text = output_text(tool, response)
    path = str((ev.get("tool_input") or {}).get("file_path") or "")
    cut = reduce(tool, text, ev.get("tool_use_id") or "", cfg, path)
    if cut is None:
        return None
    sid = ev.get("session_id") or ""
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mode": cfg.mode,
           "session": f"claude_code/vm/{sid}" if sid else None, "call_id": ev.get("tool_use_id"), "tool": tool,
           **{k: cut[k] for k in ("orig_chars", "kept_chars", "lines", "signal")}}
    record(row, folder)
    return row


def rows(folder: Path, days: int) -> list[dict]:
    out = []
    for k in range(days):
        path = folder / f"entrance-{datetime.now(timezone.utc) - timedelta(days=k):%Y-%m-%d}.jsonl"
        if path.exists():
            out += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return out


def report(folder: Path, days: int, cfg: Entrance) -> dict:
    rs = rows(folder, days)
    by_tool: dict[str, Counter] = defaultdict(Counter)
    for r in rs:
        c = by_tool[r["tool"]]
        c["outputs"] += 1
        c["orig_chars"] += r["orig_chars"]
        c["saved_chars"] += r["orig_chars"] - r["kept_chars"]
    saved = sum(c["saved_chars"] for c in by_tool.values())
    orig = sum(c["orig_chars"] for c in by_tool.values())
    return {"days": days, "outputs": len(rs), "sessions": len({r.get("session") for r in rs}),
            "orig_chars": orig, "saved_chars": saved, "saved_share": round(saved / orig, 3) if orig else None,
            "saved_tokens_est": round(saved / cfg.chars_per_token),
            "by_tool": {t: dict(c) for t, c in sorted(by_tool.items(), key=lambda kv: -kv[1]["saved_chars"])}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="walter-context-entrance", description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", action="store_true", help="what the shadow would have cut, from the records")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    cfg = load()
    if a.report:
        folder = _folder()
        out = report(folder, a.days, cfg) if folder else {"error": "no instance"}
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"{out.get('outputs', 0)} large outputs over {a.days} d, {out.get('sessions', 0)} sessions: "
                  f"{out.get('saved_chars', 0):,} chars would have been cut "
                  f"(~{out.get('saved_tokens_est', 0):,} tokens, {100 * (out.get('saved_share') or 0):.0f} % of them)")
            for tool, c in (out.get("by_tool") or {}).items():
                print(f"  {tool:28s} {c['outputs']:5d} outputs  {c['saved_chars']:>11,} chars cut")
        return 0
    try:                                   # hook side: never raise, never print in shadow (fail-open)
        handle(json.loads(sys.stdin.read() or "{}"), cfg)
    except Exception as e:                 # noqa: BLE001
        print(f"walter-context-entrance: {type(e).__name__}: {e}"[:300], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
