"""The single door to external models (A6, D6): privacy guard + budget guard + accounting.

Every Walter Memory processor calls chat() / decide() / rerank() instead of an SDK; all of them execute through the
walter-llm gateway (Walter Router), never on a provider directly (SOCLE A6, 2026-11-11). local_only content is refused, redacted_cloud content
is pseudonymised (and the answer restored locally), each call lands in system.model_calls with its budget
('recurring' or 'backfill'), and a call is refused when its monthly envelope is exhausted.
"""
from __future__ import annotations

import os
import time

import httpx

from . import privacy
from .db import connection

# The Router is the single execution path (SOCLE A6, 2026-11-11): every model call of Memory — chat by poste or by
# named model, typed decisions, rerank — goes to the walter-llm gateway (Walter Router's code) with Memory's own agent
# token. Memory keeps its door: privacy refusal, pseudonymisation, monthly budgets, the system.model_calls ledger. It
# holds no provider key, no provider endpoint and no model name. When the gateway is down the call fails and says so
# (callers already handle exceptions); there is no built-in fallback.
GATEWAY = os.environ.get("WALTER_LLM_URL", "http://127.0.0.1:8894").rstrip("/")
GATEWAY_URL = GATEWAY + "/v1/chat/completions"
# Memory's own walter-llm agent token: @instance/bootstrap/walter-llm/walter-memory.env (0600), resolved through the
# instance interface (2026-11-11: no ~/.hermes path any more).
GATEWAY_TOKEN_PARTS = ("bootstrap", "walter-llm", "walter-memory.env")


class PrivacyRefused(PermissionError):
    pass


class BudgetExceeded(RuntimeError):
    pass


# Real OpenRouter balance floors (2026-10-02: a backfill under a 50 $ internal envelope drained an ~8 $ account).
# Backfill stops first, so live uses keep a reserve. Since SOCLE A6 the floor is enforced by the gateway, which knows
# the route: Memory sends its budget's floor (`paid_floor_usd` / X-Walter-Paid-Floor-USD) and a paid OpenRouter route is
# skipped below it; free models and subscriptions are never refused by it.
ACCOUNT_FLOOR_USD = {"backfill": 5.0, "recurring": 1.0}
_balance: tuple[float, float | None] | None = None


def account_balance() -> float | None:
    """Remaining OpenRouter credit as the gateway sees it (GET /v1/balance, cached 5 min); None when unknown. For
    health reports only: the floor itself is applied by the gateway on each paid route."""
    global _balance
    if _balance and time.time() - _balance[0] < 300:
        return _balance[1]
    try:
        r = httpx.get(GATEWAY + "/v1/balance", headers={"Authorization": f"Bearer {_gateway_token()}"}, timeout=15)
        value = r.json()["openrouter"]["remaining_usd"]
        value = None if value is None else float(value)
    except Exception:  # noqa: BLE001
        value = None
    _balance = (time.time(), value)
    return value


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
                     {"processor_version": None, "provider": "walter-llm", "purpose": None, "input_tokens": None,
                      "cached_tokens": None, "output_tokens": None, "cost_usd": None, "latency_ms": None,
                      "error": None, **row})


_TOKEN_FILE: list = []


def _gateway_token() -> str:
    """Memory's walter-llm token. The file's place is resolved once per process (`walter instance path` is a
    subprocess: ~0.2 s, measured on the preflight's path 2026-11-11); the file itself is re-read on every call, so a
    rotated token is picked up at once."""
    if not _TOKEN_FILE:
        from .purge import _instance
        path = _instance(*GATEWAY_TOKEN_PARTS)
        if path is None:
            raise RuntimeError("no active Walter instance for the walter-llm token")
        _TOKEN_FILE.append(path)
    path = _TOKEN_FILE[0]
    for line in path.read_text().splitlines():
        if line.startswith("WALTER_LLM_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"no WALTER_LLM_TOKEN in {path}")


def chat(messages: list[dict], *, model: str | None = None, poste: str | None = None, processor: str,
         privacy_class: str, budget: str = "recurring", names: list[str] | None = None,
         processor_version: str | None = None, purpose: str | None = None, timeout: float = 180, **params) -> dict:
    """OpenAI-style chat call through the walter-llm gateway. Returns {"content", "usage", "cost_usd", "model", "provider"}.
    poste: a Walter Router task (summarization, memory_extraction…) — the router chooses the model, the gateway runs
    its routes (preferred: Monsieur's rule, no hardcoded model). model: a model named by the caller (benches), sent as
    the gateway's `exact:<model>` task: the Router validates it and runs exactly that model, never another; the
    budget's paid-balance floor travels with it (X-Walter-Paid-Floor-USD).
    privacy_class: the strictest class of the data in messages. names: people names to pseudonymise."""
    if bool(model) == bool(poste):
        raise ValueError("chat(): give exactly one of model= or poste=")
    base = {"processor": processor, "processor_version": processor_version, "model": model or f"router:{poste}",
            "purpose": purpose, "budget": budget, "privacy_class": privacy_class,
            "provider": "walter-llm"}
    if not privacy.model_may_receive(privacy_class):
        _log(**base, status="refused_privacy")
        raise PrivacyRefused(f"{processor}: {privacy_class} data cannot be sent to {model}")
    b = budget_status(budget)
    if b and b["hard_stop"] and b["spent_usd"] >= b["limit_usd"]:
        _log(**base, status="refused_budget")
        raise BudgetExceeded(f"{budget} budget exhausted ({b['spent_usd']:.2f}/{b['limit_usd']} USD this month)")
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
        headers = {"Authorization": f"Bearer {_gateway_token()}"}
        if poste:   # the router decides the reasoning level of the route
            params.pop("reasoning", None)
        else:       # a named model: exactly that one (Router-validated), the paid floor of this budget applies
            headers["X-Walter-Paid-Floor-USD"] = repr(ACCOUNT_FLOOR_USD.get(budget, 1.0))
        r = httpx.post(GATEWAY_URL, headers=headers, timeout=timeout,
                       json={"model": poste or f"exact:{model}", "messages": messages, **params})
        data = r.json()
        if r.status_code >= 400 or "choices" not in data:
            raise RuntimeError(f"HTTP {r.status_code}: {str(data.get('error') or data.get('detail') or data)[:300]}")
    except Exception as e:
        _log(**base, status="error", error=str(e)[:500], latency_ms=int((time.perf_counter() - t0) * 1000))
        raise
    usage = data.get("usage") or {}
    cost = usage.get("cost")
    # the route that answered ("kie/gpt-6-luna"), for the ledger and the derived items' provenance
    prov, _, used = (r.headers.get("x-walter-route") or "walter-llm/").partition("/")
    base.update(provider=prov, model=used or base["model"])
    if cost is None and r.headers.get("x-walter-cost-usd"):   # providers that report no cost: the gateway's price
        try:
            cost = float(r.headers["x-walter-cost-usd"])
        except ValueError:
            cost = None
    content = data["choices"][0]["message"].get("content") or ""
    if mapping:
        content = privacy.restore(content, mapping)
    _log(**base, status="ok", latency_ms=int((time.perf_counter() - t0) * 1000),
         input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
         cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens"), cost_usd=cost)
    return {"content": content, "usage": usage, "cost_usd": cost, "model": base["model"],
            "provider": base["provider"]}


# --- structured decisions (System One contract) and rerank, executed by the gateway ----------------------------

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


class GatewayError(RuntimeError):
    """The walter-llm gateway refused or every model of the Router's chain failed (explicit, never a silent default)."""

    def __init__(self, message: str, attempts: list | None = None, calls: list | None = None):
        super().__init__(message)
        self.attempts, self.calls = attempts or [], calls or []


def _structured(path: str, body: dict, timeout: float) -> dict:
    """POST to a structured gateway endpoint; GatewayError with the attempts on any refusal or failure."""
    try:
        r = httpx.post(GATEWAY + path, headers={"Authorization": f"Bearer {_gateway_token()}"}, json=body,
                       timeout=timeout)
    except Exception as exc:  # noqa: BLE001 — gateway down: said, the Router is the only path
        raise GatewayError(f"walter-llm unreachable ({type(exc).__name__})") from None
    try:
        data = r.json()
    except ValueError:
        data = None
    if r.status_code >= 400 or not isinstance(data, dict):
        err = (data or {}).get("error") if isinstance(data, dict) else None
        err = err if isinstance(err, dict) else {"message": err or (data or {}).get("detail") if isinstance(data, dict) else None}
        attempts = err.get("attempts") or []
        why = "; ".join(f"{a.get('provider', '?')}/{a.get('model', '?')}: {a.get('reason')}" for a in attempts)
        raise GatewayError(f"walter-llm {path} HTTP {r.status_code}: {str(err.get('message'))[:200]}"
                           + (f" ({why[:400]})" if why else ""), attempts, err.get("calls"))
    return data


def _book_calls(base: dict, calls: list[dict]) -> None:
    """One system.model_calls row per physical call the gateway made (the ledger keeps its shape)."""
    for c in calls or []:
        row = {**base, "provider": c.get("provider") or "walter-llm", "model": c.get("model") or base["model"],
               "latency_ms": int(float(c.get("seconds") or 0) * 1000)}
        if c.get("skipped") == "straggler":     # a late sample the gateway did not wait for (the mean was made of
            _log(**row, status="dropped", error="straggler")            # the others): not a failure of the decision
        elif c.get("skipped") == "route_unavailable":   # set aside by the gateway (model gone, no grant): a failure
            _log(**row, status="error", error=f"route_unavailable: {c.get('error') or ''}"[:200])   # of the route
        elif c.get("skipped"):
            _log(**row, status="refused_budget", error=str(c["skipped"])[:200])
        elif c.get("ok"):
            _log(**row, status="ok", input_tokens=c.get("input_tokens"), output_tokens=0, cost_usd=c.get("cost_usd"))
        else:
            _log(**row, status="error", error=str(c.get("error"))[:500])


def decide(state: dict, questions: dict, *, processor: str, privacy_class: str, names: list[str] | None = None,
           model: str | None = None, models: tuple[str, ...] | None = None, purpose: str | None = None,
           budget: str = "recurring", timeout: float = 30, samples: int = 1) -> dict:
    """Typed decisions (System One contract: one call, a probability per option) from a decision model, executed by
    the walter-llm gateway (POST /v1/decisions) on Walter Router's decision chain, in order, first model that answers.
    `samples` > 1 asks the same model that many times in parallel and averages the answers (the gateway's
    merge_answers): the decision APIs sample, so one call on the same inputs can land either side of a threshold
    (preflight 2026-11-09: cap_memory 0.37–0.55 on one message); the mean of 3 cuts that spread by √3.
    `model` / `models`: a request to narrow the Router's chain (the gateway refuses a model the Router does not offer).
    local_only state is refused; redacted_cloud state is pseudonymised (strings, recursively) before leaving Memory.
    Paid models are skipped by the gateway when OpenRouter's credit is under this budget's floor.
    Returns {"answers": {...}, "usage": {...}, "model": ..., "provider": ..., "route": ...[, "samples": n]}."""
    asked = [model] if model else (list(models) if models else None)
    label = asked[0] if asked else "router:decision"
    base = {"processor": processor, "model": label, "purpose": purpose, "budget": budget, "privacy_class": privacy_class}
    if not privacy.model_may_receive(privacy_class):
        _log(**base, provider="walter-llm", status="refused_privacy")
        raise PrivacyRefused(f"{processor}: {privacy_class} data cannot be sent to a decision model")
    if privacy_class == "redacted_cloud" and privacy.pseudonymise():
        state = _redact_tree(state, names, {})
    body = {"state": state, "questions": questions, "samples": samples, "timeout": timeout,
            "paid_floor_usd": ACCOUNT_FLOOR_USD.get(budget, 1.0), **({"models": asked} if asked else {})}
    t0 = time.perf_counter()
    try:
        out = _structured("/v1/decisions", body, timeout * 3 + 10)   # the gateway may try up to the whole chain
    except GatewayError as exc:
        if exc.calls:
            _book_calls(base, exc.calls)
        else:
            _log(**base, provider="walter-llm", status="error", error=str(exc)[:500],
                 latency_ms=int((time.perf_counter() - t0) * 1000))
        raise RuntimeError(f"no decision model answered: {exc}") from None
    _book_calls(base, out.get("calls"))
    res = {"answers": out["answers"], "usage": out.get("usage") or {}, "model": out.get("model"),
           "provider": out.get("provider"), "route": out.get("route")}
    if samples > 1:
        res["samples"] = out.get("samples")
    return res


def rerank(query: str, documents: list[str], *, top_n: int | None = None, processor: str, privacy_class: str,
           budget: str = "recurring", timeout: float = 8, model: str | None = None) -> dict:
    """Rerank through the gateway (POST /v1/rerank, Walter Router's `rerank` poste). The caller has already filtered
    and pseudonymised the documents; this door checks the privacy class, the monthly budget and books the call.
    Returns {"results": [{"index", "relevance_score"}], "model", "provider", "usage", "cost_usd"}."""
    base = {"processor": processor, "model": model or "router:rerank", "purpose": "rerank", "budget": budget,
            "privacy_class": privacy_class}
    if not privacy.model_may_receive(privacy_class):
        _log(**base, provider="walter-llm", status="refused_privacy")
        raise PrivacyRefused(f"{processor}: {privacy_class} data cannot be reranked by a cloud model")
    b = budget_status(budget)
    if b and b["hard_stop"] and b["spent_usd"] >= b["limit_usd"]:
        _log(**base, provider="walter-llm", status="refused_budget")
        raise BudgetExceeded(f"{budget} budget exhausted")
    body = {"query": query, "documents": documents, "timeout": timeout,
            "paid_floor_usd": ACCOUNT_FLOOR_USD.get(budget, 1.0),
            **({"top_n": top_n} if top_n else {}), **({"model": model} if model else {})}
    t0 = time.perf_counter()
    try:
        out = _structured("/v1/rerank", body, timeout * 2 + 5)
    except GatewayError as exc:
        # Upstream bodies may echo private input: the gateway's reasons are short codes, never content.
        _log(**base, provider="walter-llm", status="error", error=str(exc)[:500],
             latency_ms=int((time.perf_counter() - t0) * 1000))
        raise
    usage = out.get("usage") or {}
    _log(**{**base, "model": out.get("model") or base["model"]}, provider=out.get("provider") or "walter-llm",
         status="ok", input_tokens=usage.get("prompt_tokens") or usage.get("total_tokens"), output_tokens=0,
         cost_usd=out.get("cost_usd"), latency_ms=int((time.perf_counter() - t0) * 1000))
    return out


def retrieval(operation: str, *, processor: str, privacy_class: str, payload: dict, model: str | None = None,
              names: list[str] | None = None, budget: str = 'backfill', timeout: float = 60) -> dict:
    """Guarded specialized retrieval calls for isolated benchmarks and adapters.

    Operations: `rerank` (through the gateway's /v1/rerank, the Router's rerank poste; `model` = a request the Router
    validates). `embeddings`: refused explicitly — walter-llm has no embeddings endpoint (Memory's search embeddings
    are local). Rejects local_only and secrets before any network call; pseudonymises redacted_cloud recursively.
    The caller must enforce canonical provenance before supplying memory records.
    """
    if operation not in ('embeddings', 'rerank'):
        raise ValueError('retrieval operation must be embeddings or rerank')
    if privacy_class not in privacy.ORDER or budget not in ACCOUNT_FLOOR_USD:
        raise ValueError('invalid privacy class or budget')
    if not isinstance(payload, dict) or 'model' in payload:
        raise ValueError('model-free payload required (model= is a separate request)')
    base = dict(processor=processor, model=model or f'router:{operation}', purpose=operation, budget=budget,
                privacy_class=privacy_class, provider='walter-llm')
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
    if privacy_class == 'local_only' or any(
            category == 'secret' for text in strings(payload) for category, _ in privacy.detect(text)):
        _log(**base, status='refused_privacy')
        raise PrivacyRefused(f'{processor}: retrieval payload is not cloud-readable')
    b = budget_status(budget)
    if b and b['hard_stop'] and b['spent_usd'] >= b['limit_usd']:
        _log(**base, status='refused_budget')
        raise BudgetExceeded(f'{budget} budget exhausted')
    if privacy_class == 'redacted_cloud' and privacy.pseudonymise():
        payload = _redact_tree(payload, names, {})
    if operation == 'embeddings':
        _log(**base, status='error', error='no embeddings endpoint in walter-llm')
        raise GatewayError('walter-llm has no embeddings endpoint: cloud embeddings are not available')
    return rerank(payload.get('query'), payload.get('documents'), top_n=payload.get('top_n'), processor=processor,
                  privacy_class=privacy_class, budget=budget, timeout=timeout, model=model)
