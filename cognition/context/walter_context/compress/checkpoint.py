"""Portable checkpoint contract for hosts whose request must replay from a journal.

Hermes can use Session's request-only four-zone projection. Event-sourced hosts
such as DSH cannot: they commit a single checkpoint through their own transaction
API. The checkpoint policy and rendering still belong here, not in the host.
"""
from __future__ import annotations

from ..config import Config, load
from .layers import RECORD_HEADER, body_start, entry_sizes, record
from .wire import Message, clip, tokens, turn_starts, text_of

# Source kinds a host may set on user-role messages (`src`): only the owner's words are dialogue.
OWNER_KINDS = ("user", None, "")
CHECKPOINT_KIND = "compact-checkpoint"


def _record(body: list[Message], cfg: Config) -> str:
    """The record of the selected span, rendered exactly like the projection's full level (layers.dialogue): every
    owner and visible assistant text verbatim and in order, including intermediate explanations, every action with
    its ref. Only the checks are checkpoint-specific: a tool output needs a recoverable ref, and only dialogue and
    tool roles can be flattened."""
    for message in body:
        role = message.get('role')
        if role == 'tool' and not message.get('tool_call_id'):
            raise ValueError('checkpoint tool output lacks a recoverable reference')
        if role not in ('user', 'assistant', 'tool'):
            raise ValueError('checkpoint contains an unsupported message role')
    return record(body, cfg.projection, None)['content']


def plan(messages: list[Message], *, model: str = "", measured_tokens: int = 0,
         budget_tokens: int = 0, force: bool = False, cfg: Config | None = None) -> dict:
    cfg = cfg or load()
    profile = cfg.profile(model)
    budget = min(profile.effective_budget, budget_tokens) if budget_tokens > 0 else profile.effective_budget
    estimate = measured_tokens or tokens(messages)
    head = body_start(messages)
    starts = turn_starts(messages, head)
    # Preserve the live request plus configured completed turns, even on overflow.
    # A host must report an indivisible live-turn overflow instead of deleting it.
    keep = cfg.projection.keep_turns + 1
    end = starts[-keep] if len(starts) > keep else head
    pressure = force or estimate >= budget
    useful = end > head and pressure
    # Under pressure, oversized tool outputs the model has already read are trimmed first (head + tail kept, the
    # original stays in the host journal for context_recover): the only reduction available inside a live turn.
    # 2026-11-07: one deep-research turn read 52 pages (331K chars) and overflowed the window, nothing being
    # cuttable before the live turn. `prune_tools` is the decision; the host's pruner is only the mechanism.
    return {"version": 1, "engine": "walter-context", "mode": "checkpoint",
            "start": head, "end": end if useful else head, "needed": useful, "prune_tools": pressure,
            "estimated_tokens": estimate, "budget_tokens": budget,
            "kept_turns": keep, "reason": "pressure" if useful else "no_safe_useful_range"}


def summarize(messages: list[Message], *, cfg: Config | None = None, model: str = "", budget_tokens: int = 0) -> dict:
    """Return a deterministic inert record of an already selected, balanced span (a host's manual range: the
    automatic path is window.decide, which renders from the session's original turns).

    The host retains originals in its journal and checks that the result saves tokens before replacing the span.
    This operation never mutates the input. Since 2026-11-11 a record that outgrows its share is bounded instead of
    refused (a long session could no longer be compacted at all): oldest turns go to one line with the owner's
    request whole, then leave with an explicit note; an earlier record inside the span is carried, clipped with a
    marker past half the share. Machine-injected user messages (context packs, agent instructions, runtime notices;
    `src` set by the host) never enter the record: the host re-injects what it owns.
    """
    cfg = cfg or load()
    body = messages[body_start(messages):]
    if not body:
        raise ValueError("checkpoint requires conversation messages")
    # Role-bearing instructions cannot be flattened into an inert user record.
    # A system/developer update in the selected span must remain on the host surface.
    if any(m.get("role") in ("system", "developer") for m in body):
        raise ValueError("checkpoint cannot replace in-history system/developer messages")
    profile = cfg.profile(model)
    budget = min(profile.effective_budget, budget_tokens) if budget_tokens > 0 else profile.effective_budget
    limit = int(budget * cfg.policy.record_share)
    earlier = [text_of(m.get("content")) for m in body if m.get("role") == "user" and m.get("src") == CHECKPOINT_KIND]
    kept = [m for m in body if not (m.get("role") == "user" and m.get("src") not in OWNER_KINDS)]
    carried = clip("\n\n".join(earlier), limit * 2, " from the earlier record") if earlier else ""
    content, omitted, brief = carried, 0, 0
    if kept:
        _record(kept, cfg)                               # validates roles and recoverable refs
        full_sizes, brief_sizes = entry_sizes(kept, cfg.projection)
        n, room = len(full_sizes), limit - len(carried) // 4 - len(RECORD_HEADER) // 4
        size = lambda om, nb: sum(brief_sizes[om:om + nb]) + sum(full_sizes[om + nb:])   # noqa: E731
        while brief < n and size(0, brief) > room:
            brief += 1
        while omitted < n - 1 and size(omitted, brief - omitted) > room:
            omitted += 1
        rendered = record(kept, cfg.projection, None, omitted, brief - omitted)["content"]
        content = f"{carried}\n\n{rendered}" if carried else rendered
    if not content:
        raise ValueError("checkpoint span holds no dialogue")
    out = {"role": "user", "content": content}
    return {"version": 1, "engine": "walter-context", "mode": "checkpoint",
            "content": out["content"], "input_messages": len(body), "brief_turns": brief - omitted,
            "omitted_turns": omitted, "input_tokens": tokens(body), "output_tokens": tokens([out])}
