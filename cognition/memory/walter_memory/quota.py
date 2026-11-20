"""The Codex weekly quota as the gate of Memory's costly model work (A4, 2026-11-19).

L3 extraction, its backfills and subject cards run on Walter Router's `memory_extraction` poste, today the owner's
ChatGPT (Codex) plan. Those calls are booked at $0, so no dollar budget ever stops them: this gate does. It reads the
plan's weekly meter from Walter Router (`walter-router subscriptions show|refresh`: the live /wham/usage reading,
never an estimate) and answers ok only when a reading younger than `[quota] max_age_s` is under
`[quota] codex_weekly_max` %. No reading, a stale one, an estimated one or a failed refresh = not ok: the costly work
waits (nothing is lost, pending messages stay uncovered).
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone

SUB = "openai-plus"
CACHE_S = 120                    # one Router read per two minutes per process (a backfill asks before each segment)
_last: dict = {}


def _meter(action: str) -> dict | None:
    try:
        r = subprocess.run(["walter-router", "subscriptions", action, SUB], capture_output=True, text=True, timeout=90)
        subs = json.loads(r.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    for s in subs if isinstance(subs, list) else []:
        if s.get("id") == SUB:
            return s.get("meter") or None
    return None


def _age(m: dict) -> float | None:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(m["read_at"]))).total_seconds()
    except (KeyError, TypeError, ValueError):
        return None


def _reset_passed(m: dict) -> bool:
    try:
        return datetime.fromisoformat(str(m["resets_at"])) <= datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return False


def judge(m: dict | None, limit: float, max_age: float) -> dict:
    """Pure verdict on one meter reading (tests)."""
    if not m or m.get("used_percent") is None:
        return {"ok": False, "reason": "codex quota unknown (no reading from Walter Router)"}
    age = _age(m)
    out = {"used_percent": float(m["used_percent"]), "limit": limit, "read_at": str(m.get("read_at")),
           "age_s": round(age) if age is not None else None, "resets_at": str(m.get("resets_at"))}
    if m.get("estimated"):
        return {**out, "ok": False, "reason": "codex quota only estimated"}
    if age is None or age > max_age:
        return {**out, "ok": False, "reason": f"codex quota reading too old ({out['age_s']} s)"}
    if _reset_passed(m):
        return {**out, "ok": False, "reason": "codex quota reading from before the weekly reset"}
    if out["used_percent"] >= limit:
        return {**out, "ok": False, "reason": f"codex weekly quota {out['used_percent']:.0f} % ≥ {limit:.0f} %"}
    return {**out, "ok": True}


def codex(*, fresh: bool = False) -> dict:
    """{"ok", "used_percent", "limit", "read_at", "age_s", "resets_at"[, "reason"]}."""
    from . import organic
    cfg = organic.settings().get("quota") or {}
    limit, max_age = float(cfg.get("codex_weekly_max", 70)), float(cfg.get("max_age_s", 1800))
    if not fresh and _last and time.monotonic() - _last["t"] < CACHE_S:
        return _last["v"]
    m = _meter("show")
    if not m or (_age(m) or 1e9) > max_age / 2 or _reset_passed(m):
        m = _meter("refresh") or m          # a live read through the Router (it records the reading)
    v = judge(m, limit, max_age)
    _last.update(t=time.monotonic(), v=v)
    return v


# ───────────────────────────── waiting for the quota (E2E 20/11) ─────────────────────────────
RETRY_UNKNOWN_S = 1800           # no reliable reading: ask again in 30 min
RESET_MARGIN_S = 300             # over the cap: resume 5 min after the weekly reset (a fresh reading is then taken)


class Waiting(RuntimeError):
    """Raised before a Codex-dependent model call while the gate is closed. Not a failure: the queue keeps the key,
    due again at `until`, attempts unchanged (processing.wait), so nothing is lost and nothing is retried in a loop."""

    def __init__(self, verdict: dict):
        self.verdict = verdict
        self.until = retry_at(verdict)
        super().__init__(verdict.get("reason") or "codex quota gate closed")


def retry_at(v: dict, now: datetime | None = None) -> datetime:
    from datetime import timedelta
    now = now or datetime.now(timezone.utc)
    try:
        if v.get("used_percent") is not None and float(v["used_percent"]) >= float(v.get("limit") or 0):
            r = datetime.fromisoformat(str(v["resets_at"]))
            if r > now:
                return r + timedelta(seconds=RESET_MARGIN_S)
    except (KeyError, TypeError, ValueError):
        pass
    return now + timedelta(seconds=RETRY_UNKNOWN_S)


def require() -> dict:
    """The gate for one Codex-dependent call (Kardex enrichment, dated plans…): the verdict when open, else Waiting.
    Called inside the model call itself, so answers already recorded (processing.decide_once) are still reused and the
    deterministic work around it never stops."""
    v = codex()
    if not v["ok"]:
        raise Waiting(v)
    return v
