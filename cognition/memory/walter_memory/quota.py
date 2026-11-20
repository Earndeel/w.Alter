"""Real provider limits for Memory's model work (owner, 2026-11-20: « aucune limitation artificielle de quota »).

There is no percentage gate any more (the A4 gate at 70 % of the Codex week, 2026-11-19, is gone). Memory's calls go
through Walter Router like every other module's: the Router uses each subscription up to its provider's real limit
and, when one refuses, fails over to another allowed route — paid routes within their explicit dollar limits only
(`walter_memory.llm` monthly budgets with hard stop, the paid-balance floor, the gateway's test budget).

Memory waits only when the Router itself could not answer because of a real limit: every route refused the call for
rate or usage limits (HTTP 429, « every route failed » with only rate-limit refusals, a provider's usage-limit text).
The first such refusal records one hold for that poste (extraction.state 'provider_hold'), until the reset the
Router reports for an exhausted subscription or a short retry for a burst limit. While it lasts every caller of the
poste waits without calling (`Waiting`: queue keys are parked at `until` with their attempts unchanged, extraction
threads stay dirty), so nothing is lost, nothing loops, and the work resumes by itself afterwards.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone

POSTE = "memory_extraction"      # the poste of Memory's costly work (extraction, cards, Kardex, plans)
HOLD_KEY = "provider_hold"
RETRY_S = 900                    # a burst limit (or a limit without a known reset): ask again in 15 min
RESET_MARGIN_S = 300             # an exhausted subscription: resume 5 min after the reset its provider reports
SUBSCRIPTIONS = {"codex": "openai-plus"}   # route provider -> Walter Router subscription, for the reset time

_LIMIT = re.compile(r"(?i)(\bHTTP 429\b|rate.?limit|usage.?limit|insufficient_quota|quota (exceeded|exhausted)|"
                    r"too many requests)")


class Waiting(RuntimeError):
    """A real provider limit holds this poste. Not a failure: the caller parks its work until `until`."""

    def __init__(self, verdict: dict):
        self.verdict = verdict
        self.until = _dt(verdict.get("until")) or datetime.now(timezone.utc) + timedelta(seconds=RETRY_S)
        super().__init__(verdict.get("reason") or "provider limit")


def _dt(v) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def real_limit(exc: BaseException) -> bool:
    """True when the Router could not answer because of a provider's real limit, not for any other failure.
    « every route failed » counts only when every attempt was a rate-limit refusal."""
    text = str(exc)
    if "every route failed" in text:
        attempts = re.findall(r"[\w.-]+/[\w.:@-]+: (\w+)", text)
        return bool(attempts) and all(a == "RateLimitError" for a in attempts)
    return bool(_LIMIT.search(text))


def _reset_of(text: str, now: datetime) -> datetime | None:
    """The reset of an exhausted subscription named in the refusal, from Walter Router's live meter."""
    for provider, sub in SUBSCRIPTIONS.items():
        if f"{provider}/" not in text:
            continue
        try:
            r = subprocess.run(["walter-router", "subscriptions", "show", sub], capture_output=True, text=True,
                               timeout=60)
            rows = json.loads(r.stdout or "[]")
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        for s in rows if isinstance(rows, list) else []:
            m = s.get("meter") or {}
            reset = _dt(m.get("resets_at"))
            if s.get("id") == sub and float(m.get("used_percent") or 0) >= 100 and reset and reset > now:
                return reset
    return None


def until_for(exc: BaseException, now: datetime | None = None, reset: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    reset = reset if reset is not None else _reset_of(str(exc), now)
    return reset + timedelta(seconds=RESET_MARGIN_S) if reset else now + timedelta(seconds=RETRY_S)


def _read(conn) -> dict:
    r = conn.execute("select value from extraction.state where key = %s", (HOLD_KEY,)).fetchone()
    return dict(r["value"]) if r and isinstance(r["value"], dict) else {}


def gate(poste: str = POSTE, now: datetime | None = None) -> dict:
    """{"ok": True} unless a real limit holds the poste: {"ok": False, "reason", "until", "since"}."""
    from .db import connection
    now = now or datetime.now(timezone.utc)
    try:
        with connection() as conn:
            h = _read(conn).get(poste)
    except Exception:  # noqa: BLE001 — no hold readable: the call itself will meet any real limit
        return {"ok": True}
    if h and (_dt(h.get("until")) or now) > now:
        return {"ok": False, **h}
    return {"ok": True}


def hold(poste: str, exc: BaseException, now: datetime | None = None) -> dict:
    """Record (or extend) the poste's hold after a real refusal; the verdict callers park on."""
    from .db import connection
    now = now or datetime.now(timezone.utc)
    until = until_for(exc, now)
    v = {"reason": f"limite réelle du fournisseur : {str(exc)[:200]}", "until": until.isoformat(),
         "since": now.isoformat()}
    with connection() as conn:
        cur = _read(conn).get(poste) or {}
        if cur and (_dt(cur.get("until")) or now) > now:
            v["since"] = cur.get("since") or v["since"]
        conn.execute("""insert into extraction.state (key, value, updated_at) values (%s, jsonb_build_object(%s::text, %s::jsonb), now())
                        on conflict (key) do update set value = extraction.state.value || excluded.value, updated_at = now()""",
                     (HOLD_KEY, poste, json.dumps(v)))
    return {"ok": False, **v}


def release(poste: str = POSTE) -> None:
    from .db import connection
    with connection() as conn:
        conn.execute("update extraction.state set value = value - %s::text, updated_at = now() where key = %s",
                     (poste, HOLD_KEY))


def require(poste: str = POSTE) -> dict:
    """Before a call of the poste: its verdict when free, else Waiting (no call is made while a real limit holds)."""
    v = gate(poste)
    if not v["ok"]:
        raise Waiting(v)
    return v
