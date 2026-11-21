"""The window of an owner turn: what the completed turns of a session become before the new message enters.

Decision A1 (2026-11-11). A host that replays its journal (Walter Engine) used to carry the whole technical history
of a conversation until the model budget was reached: a message arriving the next day paid for yesterday's tool
outputs, and nothing chose what was still relevant. Here walter-context decides, at each owner-turn boundary:

    verbatim   the last completed turn(s), only while recent and small (the working data of a live exchange)
    full       turns of the message's thread, and any recent turn: every owner and assistant text, each action
               with its status and ref (tool payloads stay behind `context_recover`)
    brief      every other turn: the owner's request whole, the answer in one line
    omitted    only when even that exceeds the record budget, oldest first, and the record says so

The record is rendered from the ORIGINAL turns the host journal still holds (never from a previous record), so a
level is a pure function of (turns, thread of the new message, clock) and no summary of a summary ever builds up.
Machine-injected user messages (context packs, agent instructions, runtime notices) never enter the record: the host
re-injects what it owns, and a pack is stale once its turn is over.

A boundary rewrites the payload after the system head, so it happens only when it pays: any real gain when the
provider cache is cold (idle past its TTL: everything is re-sent anyway), `policy.min_gain_tokens` when it is warm,
and always under pressure. Stdlib only, no model call, no clock or randomness beyond the `now` the host passes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DEFAULT_PATH, Config, load
from .layers import RECORD_HEADER, _brief_entry, _results, dialogue
from .wire import Message, strip_injected, text_of, tokens

# Source kinds of user-role messages (host vocabulary). Only the owner's words are dialogue.
OWNER_KINDS = ("user", None, "")
PACK_KIND = "walter-intake"

RELEVANCE_KEYS = {"keep_turns": int, "recent_s": (int, float), "verbatim_budget_tokens": int,
                  "thread_full_turns": int, "record_budget_tokens": int, "min_gain_cold_tokens": int,
                  "frame_tokens": int}


def settings(path: str | Path | None = None) -> dict:
    """[relevance] of config/walter-context.toml (the only place these tunables live)."""
    import tomllib
    raw = tomllib.loads(Path(path or DEFAULT_PATH).read_text()).get("relevance")
    if not isinstance(raw, dict):
        raise ValueError("[relevance] missing from the walter-context configuration")
    missing = sorted(set(RELEVANCE_KEYS) - raw.keys())
    if missing:
        raise ValueError(f"[relevance]: missing {missing}")
    for k, t in RELEVANCE_KEYS.items():
        if not isinstance(raw[k], t) or isinstance(raw[k], bool) or raw[k] < 0:
            raise ValueError(f"[relevance].{k}: invalid value")
    return {k: raw[k] for k in RELEVANCE_KEYS}


@dataclass
class Turn:
    number: int
    messages: list[Message] = field(default_factory=list)

    @property
    def visible(self) -> bool:
        return bool(self.messages) and all(m.get("visible") for m in self.messages)

    @property
    def shadowed(self) -> bool:
        return not any(m.get("visible") for m in self.messages)

    @property
    def tok(self) -> int:
        return sum(int(m.get("tok") or 0) for m in self.messages)

    @property
    def ended_ms(self) -> int:
        return max((int(m.get("at") or 0) for m in self.messages), default=0)

    @property
    def thread(self) -> str | None:
        """The thread the preflight attached this turn to (carried by the turn's context pack)."""
        for m in self.messages:
            if m.get("src") == PACK_KIND and m.get("thread"):
                return str(m["thread"])
        return None

    def dialogue(self) -> list[Message]:
        """What a record may render: the owner's words, the assistant's, the tool traffic. No injected message."""
        out = []
        for m in self.messages:
            if m.get("role") == "user":
                if m.get("src") not in OWNER_KINDS:
                    continue
                text = strip_injected(text_of(m.get("content")))
                if not text or text.startswith(RECORD_HEADER[:24]):
                    continue                              # an unmarked earlier record: originals are rendered instead
                out.append({"role": "user", "content": text})
            elif m.get("role") in ("assistant", "tool"):
                out.append(m)
        return out


def turns_of(messages: list[Message]) -> list[Turn]:
    out: list[Turn] = []
    for m in messages:
        if m.get("role") in ("system", "developer"):
            continue
        n = int(m.get("turn") or 0)
        if not out or out[-1].number != n:
            out.append(Turn(n))
        out[-1].messages.append(m)
    return out


def _stamp(ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000)) if ms else "date inconnue"


def _entry(turn: Turn, level: str, cfg: Config) -> str:
    body = turn.dialogue()
    if not body:
        return ""
    if level == "brief":
        line = _brief_entry(body, cfg.projection, None)
        return f"- [{_stamp(turn.ended_ms)}] {line[2:]}"
    text = dialogue(body, _results(body), cfg.projection, None)
    return f"[{_stamp(turn.ended_ms)}]\n{text}" if text else ""


def render(turns: list[Turn], levels: list[str], cfg: Config, cache: dict | None = None) -> str:
    """One inert record message, chronological. Consecutive one-line entries form a list; full entries are framed."""
    cache = cache if cache is not None else {}
    omitted = sum(1 for lv in levels if lv == "omit")
    out = [RECORD_HEADER]
    if omitted:
        out.append(f"\n\n[{omitted} earlier turns are not shown here, the owner's requests included, because the record"
                   f" exceeded its budget: they remain in the session journal (logs_search) and in long-term memory.]")
    previous = None
    for i, (turn, level) in enumerate(zip(turns, levels)):
        if level == "omit":
            continue
        if (i, level) not in cache:
            cache[(i, level)] = _entry(turn, level, cfg)
        text = cache[(i, level)]
        if not text:
            continue
        if level == "brief":
            out.append(("\n" if previous == "brief" else "\n\n") + text)
        else:
            out.append("\n\n---\n" + text)
        previous = level
    return "".join(out)


def levels_for(turns: list[Turn], thread: str | None, now_ms: int, rel: dict, cfg: Config) -> tuple[list[str], str]:
    """A level per turn, then the record budget: oldest full entries go to one line, then the oldest lines leave
    (the most recent turn keeps its line: a record never forgets what was just said)."""
    recent = rel["recent_s"] * 1000
    wanted = [i for i, t in enumerate(turns)
              if (thread and t.thread == thread) or (now_ms and now_ms - t.ended_ms <= recent)]
    full = set(wanted[-rel["thread_full_turns"]:]) if rel["thread_full_turns"] else set()
    levels = ["full" if i in full else "brief" for i in range(len(turns))]
    budget, cache = rel["record_budget_tokens"], {}
    text = render(turns, levels, cfg, cache)
    for target, lower, last in (("full", "brief", len(turns)), ("brief", "omit", len(turns) - 1)):
        for i in range(last):
            if len(text) // 4 <= budget:
                return levels, text
            if levels[i] == target:
                levels[i] = lower
                text = render(turns, levels, cfg, cache)
    return levels, text


def decide(messages: list[Message], *, model: str = "", budget_tokens: int = 0, measured_tokens: int = 0,
           now_ms: int = 0, plan: dict | None = None, live_turn: int | None = None, checkpoint_tokens: int = 0,
           force: bool = False, cfg: Config | None = None, rel: dict | None = None) -> dict:
    """The window decision for one boundary. `messages` are the session's original conversation messages in order,
    each annotated by the host: `turn`, `at` (ms), `src` (source kind), `visible` (still verbatim on the surface),
    `tok` (the host's own token count when visible), and `thread` on a context pack. `cut` is the index of the first
    message that stays verbatim; `content` replaces everything before it (previous record included)."""
    cfg = cfg or load()
    rel = rel or settings()
    profile = cfg.profile(model)
    budget = min(profile.effective_budget, budget_tokens) if budget_tokens > 0 else profile.effective_budget
    base = {"version": 1, "engine": "walter-context", "mode": "window", "needed": False, "cut": None,
            "content": None, "budget_tokens": budget, "measured_tokens": measured_tokens}
    turns = turns_of(messages)
    live = [t for t in turns if live_turn is not None and t.number == live_turn]
    done = [t for t in turns if live_turn is None or t.number != live_turn]
    if live and turns[-1] is not live[0]:
        return {**base, "reason": "irregular_surface"}
    if not done:
        return {**base, "reason": "no_completed_turn"}
    # What is still verbatim must be a suffix of the conversation: anything else is a surface this policy did not
    # shape (a manual range, a mid-turn cut); it is left to the host rather than guessed at.
    first_visible = next((i for i, t in enumerate(done) if not t.shadowed), len(done))
    if any(not t.visible for t in done[first_visible:]) or any(not t.shadowed for t in done[:first_visible]):
        return {**base, "reason": "irregular_surface"}
    over = measured_tokens >= budget if measured_tokens else False
    keep: list[Turn] = []
    if not force and not over:
        for t in reversed(done[first_visible:]):
            if len(keep) >= rel["keep_turns"] or not now_ms or now_ms - t.ended_ms > rel["recent_s"] * 1000:
                break
            if sum(k.tok for k in keep) + t.tok > rel["verbatim_budget_tokens"]:
                break
            keep.insert(0, t)
    recorded = done[:len(done) - len(keep)]
    leaving = recorded[first_visible:]
    thread = (plan or {}).get("thread") or None
    levels, content = levels_for(recorded, thread, now_ms, rel, cfg)
    before = checkpoint_tokens + sum(t.tok for t in leaving)
    after = tokens([{"role": "user", "content": content}]) + rel["frame_tokens"]
    last_call = max((int(m.get("at") or 0) for m in messages if m.get("role") == "assistant"), default=0)
    warm = bool(now_ms and last_call and now_ms - last_call < profile.cache_ttl_s * 1000)
    threshold = cfg.policy.min_gain_tokens if warm else rel["min_gain_cold_tokens"]
    gain = before - after
    needed = bool(leaving or checkpoint_tokens) and (gain >= threshold or ((force or over) and gain > 0))
    kept_first = keep[0].messages[0] if keep else (live[0].messages[0] if live and live[0].messages else None)
    cut = next((i for i, m in enumerate(messages) if m is kept_first), len(messages)) if kept_first else len(messages)
    reason = ("pressure" if (force or over) else "cold_cache" if not warm else "gain") if needed else \
             ("nothing_to_replace" if not (leaving or checkpoint_tokens) else "gain_below_threshold")
    return {**base, "needed": needed, "cut": cut, "content": content if needed else None, "reason": reason,
            "warm": warm, "thread": thread, "prune_tools": bool(force or over),
            "turns": {"verbatim": len(keep), "full": levels.count("full"), "brief": levels.count("brief"),
                      "omitted": levels.count("omit"), "leaving": len(leaving)},
            "tokens": {"before": before, "after": after, "gain": gain, "threshold": threshold}}
