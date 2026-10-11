"""One conversation's context state, whatever the runtime. Ports (Hermes, DSH, a future Walter runtime, the bench)
drive it with the same four calls:

    select(messages)   → the payload for this call (+ a trace)    every provider request
    observe(usage)     → learn the real token count after the call
    turn_complete()    → learn how many calls a turn takes (the boundary horizon)
    compact_all(msgs)  → the strongest projection, materialised (only when the host insists on compressing)

State is tiny and disposable: an Epoch (a few anchors) plus a few learned numbers. Losing it only costs one cache
rewrite; the conversation itself always stays whole in the host and in the session journal.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from .config import Config, Profile, load
from .layers import Base, Cache, Epoch, anchor, body_start, project
from .policy import Signals, Signature, common_prefix, condense, decide, signature
from .wire import Message, step_starts, turn_starts


@dataclass
class Selection:
    messages: list[Message]
    changed: bool                         # False → the host's own list is the payload (no zone in use)
    trace: dict[str, Any] = field(default_factory=dict)


class Session:
    def __init__(self, cfg: Config | None = None, model: str = "", clock: Callable[[], float] = time.time):
        self.cfg = cfg or load()
        self.clock = clock
        self.model = model
        self.cache = Cache()
        self.reset()

    # -- lifecycle ---------------------------------------------------------------------------------------------
    def reset(self) -> None:
        self.epoch = Epoch()
        self.cache.clear()
        self.last: Signature = ()
        self.last_at: float | None = None
        self.last_estimate = 0
        self.calibration = 1.0
        self.calls = 0
        self.calls_this_turn = 0
        self.calls_per_turn: float | None = None
        self.live_start: int | None = None
        self.weighed_at = 0                # payload size when moves were last weighed this turn

    def set_model(self, model: str) -> None:
        if model != self.model:
            self.model = model
            self.last = ()                 # another model = another cache
            self.calibration = 1.0

    @property
    def profile(self) -> Profile:
        return self.cfg.profile(self.model)

    # -- the hot path --------------------------------------------------------------------------------------------
    def select(self, messages: list[Message], base: Base | None = None) -> Selection:
        t0 = time.perf_counter()
        now = self.clock()
        p, cfg = self.profile, self.cfg
        reason = ""
        view = project(messages, self.epoch, cfg.projection, base, self.cache)
        if view is None:                                   # the host rewrote history under our anchors
            self.epoch, reason = Epoch(boundaries=self.epoch.boundaries), "reset"
            self.cache.clear()
            view = project(messages, self.epoch, cfg.projection, base, self.cache)
        starts = turn_starts(messages)
        live = starts[-1] if starts else 0
        new_turn = live != self.live_start
        if new_turn:
            self.live_start, self.weighed_at = live, 0
        warm = self.last_at is not None and now - self.last_at < p.cache_ttl_s and bool(self.last)
        signals = Signals(warm=warm, last=self.last, calibration=self.calibration,
                          horizon=self.calls_per_turn or cfg.policy.horizon_calls)
        sig = signature(view)
        estimate = round(view.tokens * self.calibration)
        over = estimate > p.effective_budget and estimate - self.weighed_at >= cfg.policy.regret_tokens
        weighed = 0
        if new_turn or over:
            self.weighed_at = estimate
            best, options = decide(messages, self.epoch, view, signals, cfg, p, base, sig, self.cache)
            weighed = len(options)
            if best.name != "stay":
                self.epoch, view, reason = best.epoch, best.view, best.name
                sig = signature(view)
        cached = round(common_prefix(sig, self.last) * self.calibration) if warm else 0
        self.last, self.last_at, self.last_estimate = sig, now, view.tokens
        self.calls += 1
        self.calls_this_turn += 1
        h, r, c = view.bounds
        trace = {
            "call": self.calls, "model": self.model, "epoch": self.epoch.boundaries, "boundary": reason,
            "tokens": round(view.tokens * self.calibration), "predicted_cached": cached, "warm": warm,
            "zones": {k: round(v * self.calibration) for k, v in view.zones.items()},
            "bounds": [h, r, c, len(messages)], "weighed": weighed, "ms": round((time.perf_counter() - t0) * 1000, 1),
        }
        return Selection(view.messages, changed=(r > h or c > r), trace=trace)

    # -- learning --------------------------------------------------------------------------------------------------
    def observe(self, usage: dict[str, Any] | None) -> None:
        """Calibrate the estimator on the provider's real prompt size (EMA; bounded against outliers)."""
        if not usage or not self.last_estimate:
            return
        real = usage.get("prompt_tokens") or usage.get("input_tokens")
        if not real or real <= 0:
            return
        ratio = max(0.5, min(3.0, real / self.last_estimate))
        self.calibration = ratio if self.calls <= 1 else 0.7 * self.calibration + 0.3 * ratio

    def turn_complete(self) -> None:
        if self.calls_this_turn:
            n = float(self.calls_this_turn)
            self.calls_per_turn = n if self.calls_per_turn is None else 0.7 * self.calls_per_turn + 0.3 * n
        self.calls_this_turn = 0

    # -- the host insists (manual /compress, emergency) ---------------------------------------------------------
    def compact_all(self, messages: list[Message], base: Base | None = None) -> list[Message]:
        """Everything before the live turn folded into the record (condensed to its share), older live steps
        compacted if still over budget. The host then keeps this list as its history: our epoch restarts."""
        cfg, p = self.cfg, self.profile
        h = body_start(messages)
        starts = [i for i in turn_starts(messages) if i >= h]
        live = starts[-1] if starts else h
        ep = replace(self.epoch, boundaries=self.epoch.boundaries + 1)
        if live > h:
            ep = replace(ep, record=anchor(messages, live), compact=anchor(messages, live))
        view = project(messages, ep, cfg.projection, base, self.cache) or project(messages, Epoch(), cfg.projection, base)
        ep = condense(messages, ep, view, cfg, p, self.calibration, base, self.cache)
        view = project(messages, ep, cfg.projection, base, self.cache) or view
        if view.tokens * self.calibration > p.effective_budget:
            steps = step_starts(messages, live, len(messages))
            keep = cfg.projection.live_keep_steps
            if len(steps) > keep:
                view = project(messages, replace(ep, compact=anchor(messages, steps[-keep])), cfg.projection, base,
                               self.cache) or view
        boundaries = ep.boundaries
        self.reset()
        self.epoch = Epoch(boundaries=boundaries)
        return view.messages
