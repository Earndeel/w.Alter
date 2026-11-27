"""Shared pacing of search requests (2026-11-27): one cadence per provider, shared by every Browse call.

Each search is its own `universal-scraper --search` process, started by any conversation, door or sub-agent, so
the cadence lives in Browse's state folder and is shared through a file lock — no service. A search reserves the
next start time of its provider (a light queue: requests still overlap in flight, only their starts are spaced);
a reservation further than the caller accepts is refused, so the caller takes its fallback instead of queuing for
ever. The cadence starts from a default per provider, then follows what the provider declares in its
`X-RateLimit-*` headers (a plan upgrade is picked up on the next answer); a monthly quota at zero closes the
provider until its reset. A refusal (429) pushes the next start past the provider's reset time, so the retries of
a burst are spread over the queue instead of firing together.

Measured 27/11: Brave plan = 1 request/s + 2 000/month; a burst of 4 got three 429 in 0.6 s, and their fallback
(DuckDuckGo, all at once) timed out at 8 s — the « recherches qui expirent » of the observation.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Mapping

# Seconds between two request starts, before the provider has declared its limits.
DEFAULT_INTERVAL = {"brave": 1.1, "ddg": 1.5, "parallel": 0.2}
SAFETY = 1.1          # margin over the declared rate (window edges, clock skew between processes)
MIN_INTERVAL, MAX_INTERVAL = 0.05, 10.0


def _state_dir() -> Path:
    try:
        from walter_paths import state_home
        root = state_home()
    except Exception:  # noqa: BLE001 — no instance (tests, bare runs): a private folder still serialises processes
        root = Path(os.environ.get("TMPDIR", "/tmp")) / "walter-browse"
    path = root / "search-pace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _numbers(value: str | None) -> list[float]:
    out = []
    for part in (value or "").split(","):
        try:
            out.append(float(part.strip()))
        except ValueError:
            out.append(float("nan"))
    return out


class Pacer:
    """The cadence of one provider, shared between processes."""

    def __init__(self, backend: str, *, state_dir: Path | None = None, clock=time.time) -> None:
        self.backend = backend
        self.dir = state_dir or _state_dir()
        self.clock = clock
        self.default = DEFAULT_INTERVAL.get(backend, 1.0)

    @contextlib.contextmanager
    def _locked(self):
        with open(self.dir / f"{self.backend}.lock", "a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            path = self.dir / f"{self.backend}.json"
            try:
                state = json.loads(path.read_text()) if path.exists() else {}
            except (OSError, ValueError):
                state = {}
            box = {"state": state, "dirty": False}
            try:
                yield box
            finally:
                if box["dirty"]:
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(json.dumps(box["state"]))
                    tmp.replace(path)
                fcntl.flock(handle, fcntl.LOCK_UN)

    def reserve(self, max_wait: float) -> float | None:
        """Seconds to wait before starting, or None when the queue is longer than `max_wait` / the quota is spent."""
        with self._locked() as box:
            state, now = box["state"], self.clock()
            if float(state.get("closed_until") or 0) > now:
                return None
            start = max(now, float(state.get("next_free") or 0))
            if start - now > max_wait:
                return None
            state["next_free"] = start + float(state.get("interval") or self.default)
            box["dirty"] = True
            return start - now

    def refused(self, headers: Mapping[str, Any] | None) -> None:
        """A 429: nobody starts before the provider's reset (+ jitter, so the queued retries do not align)."""
        headers = headers or {}
        wait = _numbers(headers.get("Retry-After") or headers.get("retry-after"))
        resets = _numbers(headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset"))
        delay = next((v for v in wait + resets[:1] if v == v and v >= 0), None)
        delay = min(30.0, delay if delay is not None else 1.0) + random.uniform(0.05, 0.3)
        with self._locked() as box:
            state, now = box["state"], self.clock()
            state["next_free"] = max(float(state.get("next_free") or 0), now + delay)
            box["dirty"] = True
        self.learn(headers)

    def learn(self, headers: Mapping[str, Any] | None) -> None:
        """Follow the limits the provider declares: `X-RateLimit-Policy: 1;w=1, 2000;w=2592000` + Limit/Remaining/Reset."""
        if not headers:
            return
        get = lambda name: headers.get(name) or headers.get(name.lower())  # noqa: E731
        policy, remaining, reset = get("X-RateLimit-Policy"), get("X-RateLimit-Remaining"), get("X-RateLimit-Reset")
        if not policy:
            return
        windows = []
        for part in policy.split(","):
            match = re.match(r"\s*(\d+)\s*;\s*w\s*=\s*(\d+)", part)
            if match:
                windows.append((int(match.group(1)), int(match.group(2))))
        if not windows:
            return
        rem, res = _numbers(remaining), _numbers(reset)
        short = [w / max(1, n) * SAFETY for n, w in windows if w <= 60]
        with self._locked() as box:
            state, now = box["state"], self.clock()
            if short:
                state["interval"] = round(min(MAX_INTERVAL, max(MIN_INTERVAL, max(short))), 3)
            for index, (_, w) in enumerate(windows):
                if w > 3600 and index < len(rem) and rem[index] == 0 and index < len(res) and res[index] == res[index]:
                    state["closed_until"] = now + res[index]   # quota of the period spent: closed until it resets
            state["declared"] = policy[:120]
            box["dirty"] = True
