"""When to move the cut points (a boundary). The one place that weighs cache, cost and quality.

A boundary rewrites the payload from some point on, so the next call re-sends that part uncached. It pays when the
smaller payload, re-read from cache on the following calls, saves more than that rewrite costs:

    cost(option) = next call   [cached prefix x cached_cost + rest x write_cost]
                 + H calls     [payload x cached_cost]          H = expected calls before the next boundary

A cold cache (idle past the provider TTL) makes the rewrite free: everything is re-sent anyway. Quality comes first:
past the model's effective budget the cheapest option back under budget wins even if it costs more, including, as a
last resort, compacting the older steps of the live turn (its last steps always stay verbatim). A record that outgrows its share is condensed
(oldest turns to one line, the owner's request kept whole) down to half its share, so that rewrite stays
rare; a turn is omitted only past the whole share, and the record says so.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..config import Config, Profile
from .layers import Cache, Epoch, View, anchor, body_start, entry_sizes, project, resolve, spans
from .wire import Message, chars, step_starts, turn_starts, wire_hash

Signature = tuple[tuple[str, int], ...]     # (wire hash, tokens) of each payload message, in order


def signature(view: View) -> Signature:
    return tuple((wire_hash(m), chars(m) // 4) for m in view.messages)


def common_prefix(a: Signature, b: Signature) -> int:
    """Tokens of the leading messages two payloads share byte for byte (what a prefix cache can serve)."""
    n = 0
    for (ha, ta), (hb, _) in zip(a, b):
        if ha != hb:
            break
        n += ta
    return n


@dataclass(frozen=True)
class Signals:
    warm: bool                 # the provider cache still holds the previous payload
    last: Signature            # previous payload (empty on the first call)
    calibration: float         # real prompt tokens / estimated tokens (learned from usage)
    horizon: float             # expected cached re-reads before the next boundary


@dataclass(frozen=True)
class Option:
    name: str
    epoch: Epoch
    view: View
    tokens: int                # calibrated payload size
    cached: int                # calibrated tokens the provider cache would serve on the next call
    cost: float


def price(view: View, sig: Signature, s: Signals, p: Profile) -> tuple[int, int, float]:
    total = round(view.tokens * s.calibration)
    cached = round(common_prefix(sig, s.last) * s.calibration) if s.warm else 0
    nxt = cached * p.cached_cost + (total - cached) * p.write_cost
    return total, cached, nxt + s.horizon * total * p.cached_cost


def moves(msgs: list[Message], current: Epoch, view: View, cfg: Config) -> list[tuple[str, Epoch]]:
    """Forward moves of the cut points, gentlest first."""
    h, r, c = view.bounds
    step = replace(current, boundaries=current.boundaries + 1)
    starts = [i for i in turn_starts(msgs, h) if i >= c]
    out: list[tuple[str, Epoch]] = []
    k = cfg.projection.keep_turns
    cut = starts[-1 - k] if len(starts) > k else None          # keep the live turn + k completed turns verbatim
    if cut is not None and cut > c:
        out.append(("compact", replace(step, compact=anchor(msgs, cut))))
        out.append(("fold", replace(step, record=anchor(msgs, cut), compact=anchor(msgs, cut))))
    live = starts[-1] if starts else c
    steps = step_starts(msgs, max(live, c), len(msgs))
    keep = cfg.projection.live_keep_steps
    if len(steps) > keep and steps[-keep] > c:                 # emergency: older steps of the live turn
        inner = anchor(msgs, steps[-keep])
        out.append(("live", replace(step, compact=inner)))
        if live > r:
            out.append(("live+fold", replace(step, record=anchor(msgs, live), compact=inner)))
    return out


def condense(msgs: list[Message], ep: Epoch, view: View, cfg: Config, p: Profile, calibration: float,
             base=None, cache: Cache | None = None) -> Epoch:
    """Bound the record. Oldest turns go to one line (the owner's request stays whole) until the record fits half its
    share of the budget; a turn is omitted only when even one line per turn exceeds the whole share, and the record
    then says so. Both cut points only move forward."""
    limit = cfg.policy.record_share * p.effective_budget
    if view.zones["record"] * calibration <= limit:
        return ep
    h = body_start(msgs)
    r = resolve(msgs, ep.record, h)
    body = msgs[h:r]
    turns = spans(body)
    full, brief = entry_sizes(body, cfg.projection, base, cache)
    target = limit / 2 / calibration
    o = resolve(msgs, ep.omit, h) - h if ep.omit else 0
    omit = sum(1 for a, _ in turns if a < o)
    size = lambda om, nb: sum(brief[om:om + nb]) + sum(full[om + nb:])   # noqa: E731
    nb = max(0, sum(1 for a, _ in turns if a < (resolve(msgs, ep.brief, h) - h if ep.brief else 0)) - omit)
    while omit + nb < len(turns) and size(omit, nb) > target:
        nb += 1
    while omit < len(turns) and size(omit, nb) > limit / calibration:
        omit, nb = omit + 1, max(0, nb - 1)
    at = lambda k: anchor(msgs, h + turns[k][0]) if k < len(turns) else ep.record   # noqa: E731
    return replace(ep, omit=at(omit) if omit else ep.omit, brief=at(omit + nb))


def decide(msgs: list[Message], current: Epoch, view: View, s: Signals, cfg: Config, p: Profile,
           base=None, sig: Signature | None = None, cache: Cache | None = None) -> tuple[Option, list[Option]]:
    """The option to use for this call, and every option weighed (for the trace and the bench)."""
    sig = sig if sig is not None else signature(view)
    t, cached, cost = price(view, sig, s, p)
    stay = Option("stay", current, view, t, cached, cost)
    options = [stay]
    for name, ep in moves(msgs, current, view, cfg):
        v = project(msgs, ep, cfg.projection, base, cache)
        if v is None:
            continue
        dense = condense(msgs, ep, v, cfg, p, s.calibration, base, cache)
        if dense != ep:
            ep, v = dense, project(msgs, dense, cfg.projection, base, cache) or v
        t, cached, cost = price(v, signature(v), s, p)
        if stay.tokens - t >= cfg.policy.min_gain_tokens:
            options.append(Option(name, ep, v, t, cached, cost))
    if stay.tokens > p.effective_budget:      # quality first: under budget if any option can, else the smallest
        pool = [o for o in options if o.tokens <= p.effective_budget] or [min(options, key=lambda o: o.tokens)]
    else:                                     # within budget the live turn is never touched; cost decides
        pool = [o for o in options if not o.name.startswith("live")]
    best = min(pool, key=lambda o: (o.cost, o.tokens))
    if best.name == "compact" and best.view.zones["compact"] > cfg.policy.compact_share * p.effective_budget:
        best = next((o for o in options if o.name == "fold"), best)
    return best, options
