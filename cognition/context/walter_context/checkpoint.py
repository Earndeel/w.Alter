"""Portable checkpoint contract for hosts whose request must replay from a journal.

Hermes can use Session's request-only four-zone projection. Event-sourced hosts
such as DSH cannot: they commit a single checkpoint through their own transaction
API. The checkpoint policy and rendering still belong here, not in the host.
"""
from __future__ import annotations

from dataclasses import replace

from .config import Config, load
from .layers import body_start, record
from .wire import Message, tokens, turn_starts, text_of


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


def summarize(messages: list[Message], *, cfg: Config | None = None, model: str = "", budget_tokens: int = 0) -> dict:
    """Return a deterministic inert record of an already selected, balanced span.

    The host retains originals in its journal and checks that the result saves
    tokens before replacing the span. This operation never mutates the input.
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
    users = [text_of(m.get('content')) for m in body if m.get('role') == 'user']
    # Includes previous checkpoints (DSH persists those as user messages). No heuristic
    # can reliably identify which sentence is a constraint: preserve the whole text.
    if tokens([{'role':'user','content':'\n\n'.join(users)}]) > limit:
        raise ValueError('checkpoint cannot preserve user constraints within its budget')
    projection = replace(cfg.projection, record_user_chars=max(cfg.projection.record_user_chars,
                         sum(len(x) for x in users) + 2 * len(users)))
    out = record(body, projection, lambda m: text_of(m.get('content')))
    refs = list(dict.fromkeys(str(m['tool_call_id']) for m in body if m.get('role') == 'tool' and m.get('tool_call_id')))
    if refs:
        out['content'] += '\n\nRecoverable original tool results: ' + ', '.join(refs)
    if tokens([out]) > limit:
        raise ValueError('checkpoint exceeds record budget; originals remain in the host journal')
    return {"version": 1, "engine": "walter-context", "mode": "checkpoint",
            "content": out["content"], "input_messages": len(body),
            "input_tokens": tokens(body), "output_tokens": tokens([out])}
