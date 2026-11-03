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
# Walter Router postes (2026-10-16): chat(poste=...) sends the call to the walter-llm gateway with model = the router
# task; the router picks the model and its routes (Codex subscription, Kie, OpenRouter), the gateway holds the keys.
GATEWAY_URL = "http://127.0.0.1:8894/v1/chat/completions"
GATEWAY_TOKEN_FILE = Path("/root/.hermes/walter-llm/walter-memory.env")


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


_PICKS: dict[str, tuple[float, str]] = {}


def router_model(task: str, default: str) -> str:
    """OpenRouter id of Walter Router's model for a non-chat poste (rerank, stt…), cached 10 min; `default` when the
    router is unreachable (the router is advice, never a dependency of a recall)."""
    hit = _PICKS.get(task)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        import json
        import subprocess
        r = subprocess.run(["walter-router", "pick", task], capture_output=True, text=True,
                           timeout=30)
        model = json.loads(r.stdout).get("openrouter_id") or default
    except Exception:  # noqa: BLE001
        model = hit[1] if hit else default
    _PICKS[task] = (time.time(), model)
    return model


def _gateway_token() -> str:
    for line in GATEWAY_TOKEN_FILE.read_text().splitlines():
        if line.startswith("WALTER_LLM_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"no WALTER_LLM_TOKEN in {GATEWAY_TOKEN_FILE}")


def chat(messages: list[dict], *, model: str | None = None, poste: str | None = None, processor: str,
         privacy_class: str, budget: str = "recurring", names: list[str] | None = None,
         processor_version: str | None = None, purpose: str | None = None, timeout: float = 180, **params) -> dict:
    """OpenAI-style chat call. Returns {"content", "usage", "cost_usd", "model", "provider"}.
    poste: a Walter Router task (summarization, memory_extraction…) — the router chooses the model, the walter-llm
    gateway runs its routes (preferred: Monsieur's rule, no hardcoded model). model: an explicit OpenRouter id.
    privacy_class: the strictest class of the data in messages. names: people names to pseudonymise."""
    if bool(model) == bool(poste):
        raise ValueError("chat(): give exactly one of model= or poste=")
    base = {"processor": processor, "processor_version": processor_version, "model": model or f"router:{poste}",
            "purpose": purpose, "budget": budget, "privacy_class": privacy_class,
            "provider": "walter-llm" if poste else "openrouter"}
    if not privacy.model_may_receive(privacy_class):
        _log(**base, status="refused_privacy")
        raise PrivacyRefused(f"{processor}: {privacy_class} data cannot be sent to {model}")
    b = budget_status(budget)
    if b and b["hard_stop"] and b["spent_usd"] >= b["limit_usd"]:
        _log(**base, status="refused_budget")
        raise BudgetExceeded(f"{budget} budget exhausted ({b['spent_usd']:.2f}/{b['limit_usd']} USD this month)")
    bal = None if poste else account_balance()   # a poste goes subscription / Kie first: no OpenRouter floor
    if bal is not None and bal < ACCOUNT_FLOOR_USD.get(budget, 1.0):
        _log(**base, status="refused_budget", error=f"OpenRouter balance {bal:.2f} USD below floor")
        raise BudgetExceeded(f"OpenRouter balance {bal:.2f} USD below the {budget} floor {ACCOUNT_FLOOR_USD.get(budget)} USD")
    mapping: dict[str, str] = {}
    if privacy_class == "redacted_cloud" and privacy.pseudonymise():
        red = []
        for m in messages:
            text, mp = privacy.redact(m["content"], names)
            mapping.update(mp)
            red.append({**m, "content": text})
        messages = red
    t0 = time.perf_counter()
    try:
        if poste:   # the router decides the reasoning level of the route
            params.pop("reasoning", None)
            r = httpx.post(GATEWAY_URL, headers={"Authorization": f"Bearer {_gateway_token()}"}, timeout=timeout,
                           json={"model": poste, "messages": messages, **params})
        else:
            r = httpx.post(OPENROUTER_URL, headers={"Authorization": f"Bearer {_key()}"}, timeout=timeout,
                           json={"model": model, "messages": messages, "usage": {"include": True}, **params})
        data = r.json()
        if r.status_code >= 400 or "choices" not in data:
            raise RuntimeError(f"HTTP {r.status_code}: {str(data.get('error') or data.get('detail') or data)[:300]}")
    except Exception as e:
        _log(**base, status="error", error=str(e)[:500], latency_ms=int((time.perf_counter() - t0) * 1000))
        raise
    if poste:   # the route that answered ("kie/gpt-6-luna"), for the ledger and the derived items' provenance
        prov, _, used = (r.headers.get("x-walter-route") or "walter-llm/").partition("/")
        base.update(provider=prov, model=used or base["model"])
    usage = data.get("usage") or {}
    content = data["choices"][0]["message"].get("content") or ""
    if mapping:
        content = privacy.restore(content, mapping)
    _log(**base, status="ok", latency_ms=int((time.perf_counter() - t0) * 1000),
         input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
         cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"), cost_usd=usage.get("cost"))
    return {"content": content, "usage": usage, "cost_usd": usage.get("cost"), "model": base["model"],
            "provider": base["provider"]}


# --- structured decisions (System One contract) on Cloudflare Workers AI -------------------------------------

CF_RUN = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}"
CF_PRICE = {"clef": 0.24, "clef-flash": 0.09}  # USD per M input tokens (Workers AI catalogue, 2026-10-03)
HERMES_ENV = "/root/.hermes/.env"


def _hermes_env(name: str) -> str | None:
    try:
        for line in open(HERMES_ENV).read().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    except OSError:
        return None
    return None


def _redact_tree(value, names, mapping):
    if isinstance(value, str):
        text, mp = privacy.redact(value, names)
        mapping.update(mp)
        return text
    if isinstance(value, list):
        return [_redact_tree(v, names, mapping) for v in value]
    if isinstance(value, dict):
        return {k: _redact_tree(v, names, mapping) for k, v in value.items()}
    return value


DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
# 2026-10-14 (AA Decision Index v1.0): Mercury Decide free is on our real-cost Pareto frontier (52.7, 0 $, reads
# images) and dominates Clef (48.6, free allocation, rarely says "I don't know"); Clef stays as the last resort,
# outside OpenRouter. Paid OpenRouter decision models respect the account floor of the budget.
DECIDE_CHAIN = ("inception/mercury-decide:free", "cloudflare/clef")   # fallback only: the router's chain comes first
_ROUTER_CHAIN: tuple[float, tuple[str, ...]] | None = None


def decide_chain() -> tuple[str, ...]:
    """Decision models in Monsieur's order, read from Walter Router (2026-10-16): its pinned / best 'decision' model
    from the 48 h cycle and `knowledge.json` decision.order (best_first since 2026-10-14), then the free fallbacks.
    Cached 10 min; DECIDE_CHAIN when the router is unreachable, so a decision never depends on the router being up."""
    global _ROUTER_CHAIN
    if _ROUTER_CHAIN and time.time() - _ROUTER_CHAIN[0] < 600:
        return _ROUTER_CHAIN[1]
    try:
        import json
        import subprocess
        r = subprocess.run(["walter-router", "decision-chain"], capture_output=True, text=True, timeout=30)
        chain = tuple(json.loads(r.stdout).get("chain") or ()) or DECIDE_CHAIN
    except Exception as e:  # noqa: BLE001 — the router is advice, not a dependency
        import logging
        logging.getLogger("walter.llm").warning("Walter Router decision chain unavailable, using DECIDE_CHAIN: %s", e)
        chain = DECIDE_CHAIN
    _ROUTER_CHAIN = (time.time(), chain)
    return chain


def _decide_once(model: str, state: dict, questions: dict, timeout: float) -> tuple[dict, str]:
    if model.startswith("cloudflare/") or "/" not in model:
        short = model.split("/", 1)[-1]
        account, token = _hermes_env("CLOUDFLARE_ACCOUNT_ID"), _hermes_env("CLOUDFLARE_AI_TOKEN")
        if not (account and token):
            raise RuntimeError("Cloudflare Workers AI credentials missing (CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_AI_TOKEN)")
        r = httpx.post(CF_RUN.format(account=account, model=short), headers={"Authorization": f"Bearer {token}"},
                       json={"model": short, "state": state, "questions": questions}, timeout=timeout)
        data = r.json()
        if r.status_code >= 400 or not data.get("success"):
            raise RuntimeError(f"HTTP {r.status_code}: {str(data.get('errors'))[:300]}")
        res = data["result"]
        tok = (res.get("usage") or {}).get("input_tokens") or 0
        return {**res, "cost_usd": tok * CF_PRICE.get(short, 0.24) / 1e6, "input_tokens": tok}, "cloudflare"
    r = httpx.post(DECISIONS_URL, headers={"Authorization": f"Bearer {_key()}"}, timeout=timeout,
                   json={"model": model, "state": state, "questions": questions})
    data = r.json()
    if r.status_code >= 400 or "answers" not in data:
        raise RuntimeError(f"HTTP {r.status_code}: {str(data.get('error', data))[:300]}")
    usage = data.get("usage") or {}
    return {**data, "cost_usd": usage.get("cost"), "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens")}, \
        "openrouter"


def decide(state: dict, questions: dict, *, processor: str, privacy_class: str, names: list[str] | None = None,
           model: str | None = None, models: tuple[str, ...] | None = None, purpose: str | None = None,
           budget: str = "recurring", timeout: float = 30) -> dict:
    """Typed decisions (System One contract: one call, a probability per option) from a decision model.
    Tries `model` alone, else `models`, else Walter Router's decision chain (decide_chain()), in order ("vendor/model" = OpenRouter Decisions API,
    "cloudflare/clef" or "clef" = Workers AI). local_only state is refused; redacted_cloud state is pseudonymised
    (strings, recursively) before leaving the VM. Returns {"answers": {...}, "usage": {...}, "model": ...}."""
    chain = (model,) if model else (models or decide_chain())
    if not privacy.model_may_receive(privacy_class):
        _log(processor=processor, model=chain[0], purpose=purpose, budget=budget, privacy_class=privacy_class,
             status="refused_privacy")
        raise PrivacyRefused(f"{processor}: {privacy_class} data cannot be sent to {chain[0]}")
    if privacy_class == "redacted_cloud" and privacy.pseudonymise():
        state = _redact_tree(state, names, {})
    errors = []
    for m in chain:
        free = m.endswith(":free") or m.startswith("cloudflare/") or "/" not in m
        base = {"processor": processor, "model": m, "purpose": purpose, "budget": budget, "privacy_class": privacy_class,
                "provider": "cloudflare" if m.startswith("cloudflare/") or "/" not in m else "openrouter"}
        if not free:
            bal = account_balance()
            if bal is not None and bal < ACCOUNT_FLOOR_USD.get(budget, 1.0):
                _log(**base, status="refused_budget", error=f"OpenRouter balance {bal:.2f} USD below floor")
                errors.append(f"{m}: balance below floor")
                continue
        t0 = time.perf_counter()
        try:
            res, provider = _decide_once(m, state, questions, timeout)
        except Exception as e:  # noqa: BLE001 — next decision model
            _log(**base, status="error", error=str(e)[:500], latency_ms=int((time.perf_counter() - t0) * 1000))
            errors.append(f"{m}: {str(e)[:120]}")
            continue
        _log(**base, status="ok", latency_ms=int((time.perf_counter() - t0) * 1000), input_tokens=res.get("input_tokens"),
             output_tokens=0, cost_usd=res.get("cost_usd"))
        return {"answers": res["answers"], "usage": res.get("usage") or {},
                "model": res.get("model") if provider == "openrouter" and res.get("model") else m}
    raise RuntimeError("no decision model answered: " + "; ".join(errors))
