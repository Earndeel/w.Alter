"""Wire vocabulary. OpenAI chat messages are the lingua franca between runtimes and providers.

Everything here is pure: the same messages always give the same bytes, hashes and sizes. That property is what
prompt caches reward, so nothing in this package may depend on time, randomness or dict order.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

Message = dict[str, Any]

# Provider replay sidecars (reasoning, encrypted continuations, exact replay items). Kept untouched in the live zone,
# never carried into compacted history: a compacted message is plain role/content/tool_calls.
CORE_KEYS = ("role", "content", "tool_calls", "tool_call_id", "name")
INJECTED = re.compile(r"\s*<(memory-context|walter-context)>.*?</\1>\s*", re.S)


def text_of(content: Any) -> str:
    """Readable text of a message content (string or multimodal parts); images become a marker."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict):
                kind = part.get("type", "")
                if "text" in part and isinstance(part["text"], str):
                    out.append(part["text"])
                elif "image" in kind:
                    out.append("[image]")
                elif "audio" in kind or "file" in kind:
                    out.append(f"[{kind}]")
        return "\n".join(out)
    return str(content)


def strip_injected(text: str) -> str:
    """Remove per-turn injected context (recalled memory, Walter context blocks): stale once the turn is over."""
    return INJECTED.sub("\n\n", text).strip()


def calls(msg: Message) -> list[tuple[str, str, str]]:
    """(id, name, arguments) of an assistant message's tool calls."""
    out = []
    for tc in msg.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        args = fn.get("arguments", tc.get("arguments", ""))
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False, sort_keys=True)
        out.append((str(tc.get("id") or tc.get("call_id") or ""), str(fn.get("name") or tc.get("name") or ""), args))
    return out


class _Memo:
    """Per-object memo for the pure per-message functions. Keyed by id() and guarded by identity, so a recycled id
    can never return another message's value. Hosts that clone messages on every call simply get no hits."""

    def __init__(self, limit: int = 200_000):
        self.limit, self.data, self.enabled = limit, {}, False   # off by default: only long-lived lists benefit

    def get(self, kind: str, msg: Message, fn):
        if not self.enabled:
            return fn(msg)
        k = (kind, id(msg))
        hit = self.data.get(k)
        if hit is not None and hit[0] is msg:
            return hit[1]
        if len(self.data) >= self.limit:
            self.data.clear()
        v = fn(msg)
        self.data[k] = (msg, v)
        return v

    def clear(self) -> None:
        self.data.clear()


MEMO = _Memo()


def fingerprint(msg: Message) -> str:
    return MEMO.get("fp", msg, _fingerprint)


def wire_hash(msg: Message) -> str:
    return MEMO.get("wh", msg, _wire_hash)


def chars(msg: Message) -> int:
    return MEMO.get("ch", msg, _chars)


def _fingerprint(msg: Message) -> str:
    """Identity of a message for anchoring: role, text and tool linkage; replay sidecars excluded on purpose."""
    h = hashlib.sha1()
    for part in (msg.get("role", ""), text_of(msg.get("content")), msg.get("tool_call_id") or "",
                 "|".join(f"{i}:{n}" for i, n, _ in calls(msg))):
        h.update(str(part).encode("utf-8", "surrogatepass"))
        h.update(b"\x1f")
    return h.hexdigest()[:16]


def _wire_hash(msg: Message) -> str:
    """Hash of the exact bytes a message puts on the wire (sidecars included): equal hashes = cache-equal prefix."""
    return hashlib.sha1(json.dumps(msg, ensure_ascii=False, sort_keys=True, default=str)
                        .encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _chars(msg: Message) -> int:
    """Approximate wire size in characters (content, tool calls, replay sidecars, per-message framing)."""
    n = 12 + len(text_of(msg.get("content")))
    for _, name, args in calls(msg):
        n += 24 + len(name) + len(args)
    for k, v in msg.items():
        if k not in CORE_KEYS and v:
            n += len(v) if isinstance(v, str) else len(json.dumps(v, ensure_ascii=False, default=str))
    return n


def tokens(msgs: Iterable[Message]) -> int:
    return sum(chars(m) for m in msgs) // 4


def is_head(msg: Message) -> bool:
    return msg.get("role") in ("system", "developer")


def turn_starts(msgs: list[Message], start: int = 0) -> list[int]:
    """Indices where a user turn begins (a user message not directly preceded by another user message)."""
    out = []
    for i in range(start, len(msgs)):
        if msgs[i].get("role") == "user" and (i == start or msgs[i - 1].get("role") != "user"):
            out.append(i)
    return out


def step_starts(msgs: list[Message], start: int, end: int) -> list[int]:
    """Indices of assistant messages in [start, end): safe cut points that never split a call from its results."""
    return [i for i in range(start, end) if msgs[i].get("role") == "assistant"]


def clip(text: str, limit: int, note: str = "") -> str:
    """Head + tail of a long text, with an explicit marker (never silent)."""
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return f"{text[:head]}\n[… {len(text) - limit} chars clipped{note} …]\n{text[-tail:]}"


def one_line(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: max(0, limit - 1)] + "…"
