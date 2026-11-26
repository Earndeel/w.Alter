"""Payload trace (lot 0 of the payload plan, owner 2026-11-23): what each model call of the engine really sent, part
by part — sizes, the share the provider served from its cache, and a fingerprint of the stable parts (system parts,
tool definitions), whose text is kept once per version (content-addressed, like a git object).

Observability only: nothing here changes a payload, and a failure here never touches the turn (the caller swallows
it). Rows: `<state>/payload/trace-<day>.jsonl` (0600); texts: `<state>/payload/blobs/<sha>.txt`. The per-message
Context pack is not stored here: walter-context's own journal keeps it, joined by `run_id`.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

PACK_TAG = "<walter-context>"
# where the MCP server's module layer starts in its instructions (French heading until lot 3c, then English)
MODULES_HEADS = ("\n## Modules W.Alter", "\n## W.Alter modules")
STABLE = ("soul", "engine_rules", "conduct", "walter_doc", "skills_map", "mcp_preface", "mcp_modules", "tools")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:20]


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def split_mcp(text: str) -> list[tuple[str, str]]:
    """The MCP server's instructions = an English preface + the module layer (M0 lines)."""
    i = min((j for j in (("\n" + text).find(h) for h in MODULES_HEADS) if j >= 0), default=-1)
    if i < 0:
        return [("mcp_preface", text)]
    return [("mcp_preface", text[:i].strip()), ("mcp_modules", text[i:].strip())]


class Trace:
    def __init__(self, root: Path):
        self.root = root
        self.blobs = root / "blobs"

    def _keep(self, sha: str, text: str) -> None:
        p = self.blobs / f"{sha}.txt"
        if p.exists():
            return
        self.blobs.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, p)

    def row(self, *, sys_parts: list[tuple[str, str]], messages: list[dict], tools: list[dict] | None,
            usage: dict | None) -> dict:
        """The measures of one call (pure: no I/O but the blobs of stable parts)."""
        parts: dict[str, dict] = {}
        for name, text in sys_parts:
            for k, t in (split_mcp(text) if name == "mcp_instructions" else [(name, text)]):
                if not t:
                    continue
                d = {"chars": len(t)}
                if k in STABLE:
                    d["sha"] = _sha(t)
                    self._keep(d["sha"], t)
                parts[k] = d
        tools_json = json.dumps(tools or [], ensure_ascii=False, sort_keys=True)
        if tools:
            sha = _sha(tools_json)
            self._keep(sha, tools_json)
            parts["tools"] = {"chars": len(tools_json), "sha": sha, "n": len(tools)}
        kinds = {"pack": 0, "owner": 0, "assistant": 0, "tool_results": 0, "other_user": 0}
        counts = dict.fromkeys(kinds, 0)
        for m in messages[1:] if messages and messages[0].get("role") == "system" else messages:
            role, text = m.get("role"), _text(m.get("content"))
            if role == "user" and text.lstrip().startswith(PACK_TAG):
                k = "pack"
            elif role == "user":
                k = "owner"
            elif role == "assistant":
                k = "assistant"
                text += json.dumps(m.get("tool_calls") or "", ensure_ascii=False) if m.get("tool_calls") else ""
            elif role == "tool":
                k = "tool_results"
            else:
                k = "other_user"
            kinds[k] += len(text)
            counts[k] += 1
        # the owner's latest message is the last owner row; earlier ones are history
        last_owner = next((len(_text(m.get("content"))) for m in reversed(messages)
                           if m.get("role") == "user" and not _text(m.get("content")).lstrip().startswith(PACK_TAG)), 0)
        hist = {k: v for k, v in kinds.items() if v}
        system_chars = len(_text(messages[0].get("content"))) if messages and messages[0].get("role") == "system" else 0
        total = system_chars + sum(kinds.values()) + (len(tools_json) if tools else 0)
        u = usage or {}
        prompt = u.get("prompt_tokens") or u.get("input_tokens") or 0
        cached = u.get("cached_tokens") or (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        out = {"parts": parts, "system_chars": system_chars, "messages": {"chars": hist, "n": {k: v for k, v in counts.items() if v},
               "last_owner_chars": last_owner}, "total_chars": total,
               "usage": {"prompt": prompt, "cached": cached, "completion": u.get("completion_tokens") or u.get("output_tokens") or 0}}
        if prompt and total:
            r = prompt / total
            out["tokens_est"] = {"system": round(system_chars * r), "tools": round((len(tools_json) if tools else 0) * r),
                                 **{k: round(v * r) for k, v in hist.items()}}
        return out

    def record(self, base: dict, **kw) -> None:
        row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **base, **self.row(**kw)}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.root / f"trace-{time.strftime('%Y-%m-%d', time.gmtime())}.jsonl",
                     os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
