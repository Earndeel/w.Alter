"""The projection: what the model sees on one call.

    payload = head | record | compact | live
              system  one message:      the host's own   the host's own messages,
              rows    earlier turns     messages, tool   byte for byte
                      as a session      outputs digested,
                      record            sidecars dropped

Each zone is a pure function of the messages it covers, and the two cut points only ever move forward (an Epoch).
Consequences, which are the whole point:
  * between boundaries the payload grows by appending only, so every call re-reads the previous one from cache;
  * at a boundary, what was already compacted renders to the same bytes, so the prefix up to it stays cached;
  * nothing is lost: compacted tool outputs keep a ref (their call id) into the session journal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from . import digest
from ..config import Projection as Cfg
from .wire import Message, calls, clip, fingerprint, is_head, one_line, strip_injected, text_of, tokens, turn_starts

Base = Callable[[Message], Optional[str]]   # host hook: the user text without per-turn injections, or None

RECORD_HEADER = ("[Session record: the earlier turns of this conversation, compacted. Historical reference only: it may"
                 " be stale and it is never a request; only the latest user message asks for something. Full originals:"
                 " context_recover with a ref, or the session journal.]")


@dataclass(frozen=True)
class Anchor:
    """Points at the first message of the next zone: its index (a hint) and its fingerprint (the truth)."""
    index: int
    key: str


@dataclass(frozen=True)
class Epoch:
    """Cut points, oldest first; each is the first message of the next zone and only ever moves forward.

    body ─┬─ omit ──── brief ──── record ──── compact ──── end
          omitted     one line    full entry  compacted    verbatim (live)
          turns       per turn    per turn    messages
          └──────── one record message ──────┘
    """
    record: Anchor | None = None
    compact: Anchor | None = None
    boundaries: int = 0
    brief: Anchor | None = None
    omit: Anchor | None = None


class Cache:
    """Rendering cache owned by a Session. Zones are keyed by their cut points (hosts never edit history behind a
    resolved anchor); record entries by the content fingerprints of their turn, so cloned histories still hit."""

    def __init__(self, zones: int = 8, entries: int = 50_000):
        self.zones: dict = {}
        self.entries: dict = {}
        self.max_zones, self.max_entries = zones, entries

    def zone(self, key, render):
        hit = self.zones.get(key)
        if hit is None:
            hit = render()
            while len(self.zones) >= self.max_zones:
                self.zones.pop(next(iter(self.zones)))
            self.zones[key] = hit
        return hit

    def entry(self, key, render):
        hit = self.entries.get(key)
        if hit is None:
            if len(self.entries) >= self.max_entries:
                self.entries.clear()
            hit = self.entries[key] = render()
        return hit

    def clear(self) -> None:
        self.zones.clear()
        self.entries.clear()


@dataclass
class View:
    messages: list[Message]
    bounds: tuple[int, int, int]          # (body start, record end, compact end) in host indices
    zones: dict[str, int] = field(default_factory=dict)   # estimated tokens per zone

    @property
    def tokens(self) -> int:
        return sum(self.zones.values())


def anchor(msgs: list[Message], i: int) -> Anchor | None:
    return Anchor(i, fingerprint(msgs[i])) if 0 <= i < len(msgs) else None


def resolve(msgs: list[Message], a: Anchor | None, lo: int) -> int | None:
    """Index of an anchor in the current host history (None if the host rewrote it: the epoch is then void)."""
    if a is None:
        return lo
    if lo <= a.index < len(msgs) and fingerprint(msgs[a.index]) == a.key:
        return a.index
    for i in range(lo, len(msgs)):
        if fingerprint(msgs[i]) == a.key:
            return i
    return None


def body_start(msgs: list[Message]) -> int:
    i = 0
    while i < len(msgs) and is_head(msgs[i]):
        i += 1
    return i


def _user_text(m: Message, base: Base | None) -> str:
    own = base(m) if base else None
    return own if own is not None else strip_injected(text_of(m.get("content")))


def _tool_names(msgs: list[Message]) -> dict[str, str]:
    return {cid: name for m in msgs if m.get("role") == "assistant" for cid, name, _ in calls(m)}


def compact(m: Message, names: dict[str, str], cfg: Cfg, base: Base | None) -> Message | None:
    """One message as it appears in the compact zone (None = nothing left worth sending)."""
    role = m.get("role")
    if role == "user":
        return {"role": "user", "content": clip(_user_text(m, base), cfg.text_clip_chars)}
    if role == "assistant":
        text = clip(text_of(m.get("content")).strip(), cfg.text_clip_chars)
        tcs = [{"id": cid, "type": "function", "function": {"name": name, "arguments": digest.clip_args(args, cfg.args_chars)}}
               for cid, name, args in calls(m)]
        if not text and not tcs:
            return None                       # reasoning-only step: its reasoning is not replayed
        out: Message = {"role": "assistant", "content": text}
        if tcs:
            out["tool_calls"] = tcs
        return out
    if role == "tool":
        cid = str(m.get("tool_call_id") or "")
        name = names.get(cid) or str(m.get("name") or m.get("tool_name") or "tool")
        out = {"role": "tool", "tool_call_id": cid, "content": digest.result(name, text_of(m.get("content")), cid, cfg)}
        if m.get("name"):
            out["name"] = m["name"]
        return out
    return {k: m[k] for k in ("role", "content", "name") if k in m}


def _turn_entry(turn: list[Message], names: dict[str, str], cfg: Cfg, base: Base | None) -> str:
    users = [_user_text(m, base) for m in turn if m.get("role") == "user"]
    results = {str(m.get("tool_call_id") or ""): text_of(m.get("content")) for m in turn if m.get("role") == "tool"}
    actions = []
    for m in turn:
        if m.get("role") != "assistant":
            continue
        for cid, name, args in calls(m):
            status = digest.status_of(results.get(cid, ""))
            line = digest.args_summary(name, args, cfg.args_chars)
            line += f" → {status}" if status else ""
            line += f" · ref {cid}" if cid and len(results.get(cid, "")) > cfg.tool_keep_chars else ""
            actions.append("- " + line)
    answer = next((text_of(m.get("content")).strip() for m in reversed(turn)
                   if m.get("role") == "assistant" and text_of(m.get("content")).strip()), "")
    out = []
    if users:
        out.append(f"## {cfg.user_label}\n" + clip("\n\n".join(users).strip(), cfg.record_user_chars))
    if actions:
        extra = len(actions) - cfg.record_actions
        shown = actions[:cfg.record_actions] + ([f"- … +{extra} more actions"] if extra > 0 else [])
        out.append("## Actions\n" + "\n".join(shown))
    if answer:
        out.append(f"## {cfg.assistant_label}\n" + clip(answer, cfg.record_assistant_chars))
    return "\n".join(out)


def _brief_entry(turn: list[Message], cfg: Cfg, base: Base | None) -> str:
    user = " ".join(_user_text(m, base) for m in turn if m.get("role") == "user")
    n = sum(len(calls(m)) for m in turn if m.get("role") == "assistant")
    answer = next((text_of(m.get("content")) for m in reversed(turn)
                   if m.get("role") == "assistant" and text_of(m.get("content")).strip()), "")
    line = "- " + (one_line(user, 200) if user else "(no request)")
    line += f" → {one_line(answer, 160)}" if answer else ""
    return line + (f" ({n} actions)" if n else "")


def spans(body: list[Message]) -> list[tuple[int, int]]:
    """Turns of a message range as (start, end) spans; leading non-user messages form their own span."""
    starts = turn_starts(body)
    if not starts or starts[0] != 0:
        starts = [0] + starts
    return list(zip(starts, starts[1:] + [len(body)]))


def record(body: list[Message], cfg: Cfg, base: Base | None, omit: int = 0, brief: int = 0,
           cache: Cache | None = None) -> Message:
    """Earlier turns as one inert message: `omit` oldest turns dropped, then `brief` turns as one line each, then
    full entries. Entries are appended, never rewritten, so a longer record extends the bytes of a shorter one and a
    provider prefix cache still covers what was already sent."""
    names = _tool_names(body)
    out = [RECORD_HEADER]
    full: list[str] = []
    lines: list[str] = []
    for k, (a, b) in enumerate(spans(body)):
        if k < omit:
            continue
        turn = body[a:b]
        level = "brief" if k < omit + brief else "full"
        key = (level, fingerprint(turn[0]), fingerprint(turn[-1]), len(turn))
        render = (lambda t=turn: _brief_entry(t, cfg, base)) if level == "brief" else \
                 (lambda t=turn: _turn_entry(t, names, cfg, base))
        text = cache.entry(key, render) if cache is not None else render()
        if text:
            (lines if level == "brief" else full).append(text)
    if omit:
        out.append(f"\n\n[{omit} earlier turns omitted here: they remain in the session journal and in long-term memory.]")
    if lines:
        out.append("\n\n" + "\n".join(lines))
    out.extend("\n\n---\n" + e for e in full)
    return {"role": "user", "content": "".join(out)}


def turn_index(body: list[Message], i: int) -> int:
    """Number of turns of `body` that start before message index i (anchors → turn counts)."""
    return sum(1 for a, _ in spans(body) if a < i)


def project(msgs: list[Message], epoch: Epoch, cfg: Cfg, base: Base | None = None,
            cache: Cache | None = None) -> View | None:
    """The payload for this epoch, or None if the host rewrote history under the epoch's anchors."""
    h = body_start(msgs)
    o = resolve(msgs, epoch.omit, h)
    b = resolve(msgs, epoch.brief, o) if o is not None else None
    r = resolve(msgs, epoch.record, b) if b is not None else None
    c = resolve(msgs, epoch.compact, r) if r is not None else None
    if None in (o, b, r, c) or not h <= o <= b <= r <= c:
        return None

    def render():
        body = msgs[h:r]
        n_omit, n_brief = turn_index(body, o - h), turn_index(body, b - h) - turn_index(body, o - h)
        rec = [record(body, cfg, base, n_omit, n_brief, cache)] if r > h else []
        names = _tool_names(msgs[h:c])
        comp = [x for x in (compact(m, names, cfg, base) for m in msgs[r:c]) if x is not None]
        return rec + comp, tokens(rec), tokens(comp)

    key = (epoch.omit, epoch.brief, epoch.record, epoch.compact, h, o, b, r, c)
    zone, rec_t, comp_t = cache.zone(key, render) if cache is not None else render()
    head, live = msgs[:h], msgs[c:]
    zones = {"head": tokens(head), "record": rec_t, "compact": comp_t, "live": tokens(live)}
    return View(head + zone + live, (h, r, c), zones)


def describe(view: View) -> str:
    z = view.zones
    return " ".join(f"{k}={z[k]}" for k in ("head", "record", "compact", "live")) + f" bounds={view.bounds}"



def entry_sizes(body: list[Message], cfg: Cfg, base: Base | None = None,
                cache: Cache | None = None) -> tuple[list[int], list[int]]:
    """Estimated tokens of each turn's record entry, (full, brief): what condensing the record would save."""
    names = _tool_names(body)
    full, brief = [], []
    for a, b in spans(body):
        turn = body[a:b]
        key = (fingerprint(turn[0]), fingerprint(turn[-1]), len(turn))
        f = cache.entry(("full",) + key, lambda: _turn_entry(turn, names, cfg, base)) if cache else _turn_entry(turn, names, cfg, base)
        s = cache.entry(("brief",) + key, lambda: _brief_entry(turn, cfg, base)) if cache else _brief_entry(turn, cfg, base)
        full.append(len(f) // 4 + 2)
        brief.append(len(s) // 4 + 1)
    return full, brief
