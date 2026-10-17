"""Portable checkpoint contract for hosts whose request must replay from a journal.

Hermes can use Session's request-only four-zone projection. Event-sourced hosts
such as DSH cannot: they commit a single checkpoint through their own transaction
API. The checkpoint policy and rendering still belong here, not in the host.
"""
from __future__ import annotations

from .config import Config, load
from .layers import body_start, record
from .wire import Message, tokens, turn_starts


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
    useful = end > head and (force or estimate >= budget)
    return {"version": 1, "engine": "walter-context", "mode": "checkpoint",
            "start": head, "end": end if useful else head, "needed": useful,
            "estimated_tokens": estimate, "budget_tokens": budget,
            "kept_turns": keep, "reason": "pressure" if useful else "no_safe_useful_range"}


def summarize(messages: list[Message], *, cfg: Config | None = None) -> dict:
    """Return a deterministic inert record of an already selected, balanced span.

    The host retains originals in its journal and checks that the result saves
    tokens before replacing the span. This operation never mutates the input.
    """
    cfg = cfg or load()
    body = messages[body_start(messages):]
    if not body:
        raise ValueError("checkpoint requires conversation messages")
    out = record(body, cfg.projection, None)
    return {"version": 1, "engine": "walter-context", "mode": "checkpoint",
            "content": out["content"], "input_messages": len(body),
            "input_tokens": tokens(body), "output_tokens": tokens([out])}
