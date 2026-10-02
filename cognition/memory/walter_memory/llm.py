"""The single door to external models (A6, D6): privacy guard + budget guard + accounting.

Every Walter Memory processor calls chat() instead of an SDK. local_only content is refused, redacted_cloud content
is pseudonymised (and the answer restored locally), each call lands in system.model_calls with its budget
('recurring' or 'backfill'), and a call is refused when its monthly envelope is exhausted.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

from . import privacy
from .db import connection

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class PrivacyRefused(PermissionError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def _key() -> str:
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for line in Path("/root/.hermes/.env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError("OPENROUTER_API_KEY not configured")


# Real OpenRouter balance floors (2026-10-02: a backfill under a 50 $ internal envelope drained an ~8 $ account).
# Backfill stops first, so live uses (Hindsight/voice rerank, recurring synthesis) keep a reserve.
ACCOUNT_FLOOR_USD = {"backfill": 5.0, "recurring": 1.0}
_balance: tuple[float, float] | None = None


def account_balance() -> float | None:
    """Remaining OpenRouter credits (cached 5 min); None when unknown."""
    global _balance
    if _balance and time.time() - _balance[0] < 300:
        return _balance[1]
    try:
        r = httpx.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {_key()}"}, timeout=15)
        d = r.json()["data"]
        _balance = (time.time(), float(d["total_credits"]) - float(d["total_usage"]))
        return _balance[1]
    except Exception:
        return None


def budget_status(budget: str) -> dict:
    with connection() as conn:
        return conn.execute(
            """select b.budget, b.monthly_limit_usd as limit_usd, b.hard_stop,
                      coalesce(sum(c.cost_usd) filter (where c.at >= date_trunc('month', now())), 0) as spent_usd
               from system.budgets b left join system.model_calls c on c.budget = b.budget
               where b.budget = %s group by b.budget, b.monthly_limit_usd, b.hard_stop""", (budget,)).fetchone()


def _log(**row) -> None:
    with connection() as conn:
        conn.execute("""insert into system.model_calls (processor, processor_version, provider, model, purpose, budget,
                            privacy_class, input_tokens, cached_tokens, output_tokens, cost_usd, latency_ms, status, error)
                        values (%(processor)s, %(processor_version)s, %(provider)s, %(model)s, %(purpose)s, %(budget)s,
                                %(privacy_class)s, %(input_tokens)s, %(cached_tokens)s, %(output_tokens)s, %(cost_usd)s,
                                %(latency_ms)s, %(status)s, %(error)s)""",
                     {"processor_version": None, "provider": "openrouter", "purpose": None, "input_tokens": None,
                      "cached_tokens": None, "output_tokens": None, "cost_usd": None, "latency_ms": None,
                      "error": None, **row})


def chat(messages: list[dict], *, model: str, processor: str, privacy_class: str, budget: str = "recurring",
         names: list[str] | None = None, processor_version: str | None = None, purpose: str | None = None,
         timeout: float = 180, **params) -> dict:
    """OpenAI-style chat call through OpenRouter. Returns {"content", "usage", "cost_usd"}.
    privacy_class: the strictest class of the data in messages. names: people names to pseudonymise."""
    base = {"processor": processor, "processor_version": processor_version, "model": model, "purpose": purpose,
            "budget": budget, "privacy_class": privacy_class}
    if privacy_class == "local_only":
        _log(**base, status="refused_privacy")
        raise PrivacyRefused(f"{processor}: local_only data cannot be sent to {model}")
    b = budget_status(budget)
    if b and b["hard_stop"] and b["spent_usd"] >= b["limit_usd"]:
        _log(**base, status="refused_budget")
        raise BudgetExceeded(f"{budget} budget exhausted ({b['spent_usd']:.2f}/{b['limit_usd']} USD this month)")
    bal = account_balance()
    if bal is not None and bal < ACCOUNT_FLOOR_USD.get(budget, 1.0):
        _log(**base, status="refused_budget", error=f"OpenRouter balance {bal:.2f} USD below floor")
        raise BudgetExceeded(f"OpenRouter balance {bal:.2f} USD below the {budget} floor {ACCOUNT_FLOOR_USD.get(budget)} USD")
    mapping: dict[str, str] = {}
    if privacy_class == "redacted_cloud":
        red = []
        for m in messages:
            text, mp = privacy.redact(m["content"], names)
            mapping.update(mp)
            red.append({**m, "content": text})
        messages = red
    t0 = time.perf_counter()
    try:
        r = httpx.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {_key()}"}, timeout=timeout,
                       json={"model": model, "messages": messages, "usage": {"include": True}, **params})
        data = r.json()
        if r.status_code >= 400 or "choices" not in data:
            raise RuntimeError(f"HTTP {r.status_code}: {str(data.get('error', data))[:300]}")
    except Exception as e:
        _log(**base, status="error", error=str(e)[:500], latency_ms=int((time.perf_counter() - t0) * 1000))
        raise
    usage = data.get("usage") or {}
    content = data["choices"][0]["message"].get("content") or ""
    if mapping:
        content = privacy.restore(content, mapping)
    _log(**base, status="ok", latency_ms=int((time.perf_counter() - t0) * 1000),
         input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
         cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"), cost_usd=usage.get("cost"))
    return {"content": content, "usage": usage, "cost_usd": usage.get("cost")}
