"""Structured model calls of walter-llm (SOCLE A6, 2026-11-11): typed decisions and rerank.

    POST /v1/decisions {state, questions, samples?, straggler_s?, model?, models?, paid_floor_usd?, timeout?}
        → {answers, usage, model, provider, route, samples?, calls, attempts}
        samples > 1: parallel calls of the same model, averaged; once a majority has answered the late ones get
        `straggler_s` (default 0.4 s, null = wait for all) and are then dropped (`samples` = how many were averaged).
    POST /v1/rerank    {query, documents, top_n?, model?, paid_floor_usd?, timeout?}
        → {results: [{index, relevance_score}], model, provider, route, usage, cost_usd, cost_status, attempts}

The Router decides (decision chain = `walter-router decision-chain`, rerank = the `rerank` poste); this module only
executes, in order, and stops at the first model that answers. A model named by the caller must be one the Router
offers for that task (else 400): it narrows the chain, never adds to it. When everything fails the caller gets a
structured list of attempts (provider/model + short reason: HTTP status, exception type or missing grant — never a
secret, a payload or a path).

Provider adapters (the only ones in Walter for these interfaces):
  OpenRouter Decisions API  "vendor/model[:free]"      key OPENROUTER_API_KEY
  Cloudflare Workers AI     "cloudflare/clef" | "clef"  keys CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_AI_TOKEN
  OpenRouter rerank         "vendor/model"             key OPENROUTER_API_KEY

`merge_answers` here is THE implementation of the samples mean (moved from walter_memory.llm, same semantics).
No import of the gateway: its dependencies (key reader, http client, logger) are passed in, so tests run offline.
"""
from __future__ import annotations

import asyncio
import time

OPENROUTER_DECISIONS = "https://openrouter.ai/api/alpha/decisions"
OPENROUTER_RERANK = "https://openrouter.ai/api/v1/rerank"
OPENROUTER_CREDITS = "https://openrouter.ai/api/v1/credits"
CF_RUN = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}"
CF_PRICE = {"clef": 0.24, "clef-flash": 0.09}   # USD per M input tokens (Workers AI catalogue, 2026-10-03)
MAX_SAMPLES = 5
MAX_DOCUMENTS = 1000
DEFAULT_TIMEOUT = 30.0
STRAGGLER_S = 0.4          # samples > 1: once a majority has answered, the late ones get this long (body `straggler_s`)


class MissingGrant(RuntimeError):
    """A provider key this gateway is not granted (the message names the variable and the grant, never a value)."""


def merge_answers(samples: list[dict]) -> dict:
    """The mean of several answers to the same questions. noul: mean probability. choice: mean probability per option,
    the choice = the highest mean, its confidence = the sum of the confidences of the samples that chose it divided
    by the number of samples (a sample that chose otherwise counts 0), `agreement` = the share that chose it."""
    out: dict = {}
    for k, first in samples[0].items():
        got = [s[k] for s in samples if isinstance(s.get(k), dict)]
        if first.get("type") == "noul":
            out[k] = {**first, "noul": sum(g.get("noul") or 0 for g in got) / len(got)}
            continue
        options = list(dict.fromkeys(o for g in got for o in (g.get("probabilities") or {})))
        if not options:
            out[k] = first
            continue
        p = {o: sum((g.get("probabilities") or {}).get(o, 0) for g in got) / len(got) for o in options}
        choice = max(options, key=lambda o: p[o])           # ties: the first sample's order, deterministic
        agree = [g for g in got if g.get("choice") == choice]
        out[k] = {**first, "choice": choice, "probabilities": p,
                  "confidence": sum(g.get("confidence") or 0 for g in agree) / len(got),
                  "agreement": len(agree) / len(got)}
    return out


def provider_of(model: str) -> str:
    return "cloudflare" if model.startswith("cloudflare/") or "/" not in model else "openrouter"


def is_free(model: str) -> bool:
    return model.endswith(":free") or provider_of(model) == "cloudflare"


def reason(exc: BaseException) -> str:
    """A short, safe reason for one failed attempt."""
    if isinstance(exc, MissingGrant):
        return str(exc)[:200]
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        code = getattr(exc, "code", None)
        return f"HTTP {status}" + (f" {code}" if code else "")
    return type(exc).__name__


class ProviderError(RuntimeError):
    def __init__(self, status: int, code=None):
        super().__init__(f"HTTP {status}")
        self.status, self.code = status, (str(code)[:40] if code not in (None, "") else None)


def _error_code(data) -> str | None:
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            return err.get("code") or err.get("type")
        errs = data.get("errors")
        if isinstance(errs, list) and errs and isinstance(errs[0], dict):
            return errs[0].get("code")
    return None


def _json(resp):
    try:
        return resp.json()
    except ValueError:
        return None


def _float(value) -> float | None:
    try:
        return float(value) if value is not None and not isinstance(value, bool) else None
    except (TypeError, ValueError):
        return None


async def decide_once(client, key, model: str, state: dict, questions: dict, timeout: float) -> dict:
    """One decision call on its provider → {answers, usage, model, cost_usd, cost_status, input_tokens}."""
    if provider_of(model) == "cloudflare":
        short = model.split("/", 1)[-1]
        account, token = key("CLOUDFLARE_ACCOUNT_ID"), key("CLOUDFLARE_AI_TOKEN")
        r = await client.post(CF_RUN.format(account=account, model=short), headers={"Authorization": f"Bearer {token}"},
                              json={"model": short, "state": state, "questions": questions}, timeout=timeout)
        data = _json(r)
        if r.status_code >= 400 or not isinstance(data, dict) or not data.get("success") \
                or not isinstance((data.get("result") or {}).get("answers"), dict):
            raise ProviderError(r.status_code, _error_code(data))
        res = data["result"]
        tok = (res.get("usage") or {}).get("input_tokens") or 0
        return {"answers": res["answers"], "usage": res.get("usage") or {}, "model": model,
                "cost_usd": tok * CF_PRICE.get(short, 0.24) / 1e6, "cost_status": "estimated", "input_tokens": tok}
    r = await client.post(OPENROUTER_DECISIONS, headers={"Authorization": f"Bearer {key('OPENROUTER_API_KEY')}"},
                          json={"model": model, "state": state, "questions": questions}, timeout=timeout)
    data = _json(r)
    if r.status_code >= 400 or not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
        raise ProviderError(r.status_code, _error_code(data))
    usage = data.get("usage") or {}
    cost = _float(usage.get("cost"))
    return {"answers": data["answers"], "usage": usage, "model": data.get("model") or model,
            "cost_usd": cost, "cost_status": "reported" if cost is not None else "unknown",
            "input_tokens": usage.get("prompt_tokens") or usage.get("input_tokens")}


def _requested(body: dict, offered: list[str]) -> tuple[list[str] | None, str | None]:
    """The models to try: the Router's list, or the caller's narrowing of it (each must be offered)."""
    asked = body.get("models") if body.get("models") is not None else ([body["model"]] if body.get("model") else None)
    if asked is None:
        return list(offered), None
    if not isinstance(asked, list) or not asked or not all(isinstance(m, str) and m for m in asked):
        return None, "model/models must name models"
    unknown = [m for m in asked if m not in offered]
    if unknown:
        return None, "model not offered by the Router for this task: " + ", ".join(m[:80] for m in unknown)
    return list(dict.fromkeys(asked)), None


def _floor(body: dict) -> float | None:
    value = _float(body.get("paid_floor_usd"))
    return value if value is not None and value >= 0 else None


def _timeout(body: dict) -> float:
    value = _float(body.get("timeout"))
    return max(1.0, min(value, 120.0)) if value else DEFAULT_TIMEOUT


def _straggler(body: dict) -> float | None:
    """Seconds the late samples are given once a majority has answered; `straggler_s: null` waits for all of them."""
    if "straggler_s" in body and body["straggler_s"] is None:
        return None
    value = _float(body.get("straggler_s"))
    return STRAGGLER_S if value is None else max(0.0, min(value, 30.0))


async def _samples(once, n: int, grace: float | None) -> tuple[list, list[float]]:
    """n parallel samples. Once a majority has answered, the others get `grace` seconds, then are dropped: the mean
    is made of those that came (13/11/2026: one sample in three took 9.6 s and held the whole decision of a message
    past the time its caller waits). Returns (results of the finished samples, seconds of each dropped one)."""
    t0 = time.perf_counter()
    tasks = [asyncio.ensure_future(once()) for _ in range(n)]
    pending = set(tasks)
    need = n // 2 + 1
    while pending and sum(1 for t in tasks if t.done() and t.result()[1] is not None) < need:
        _, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
    dropped: list[float] = []
    if pending:
        _, pending = await asyncio.wait(pending, timeout=grace)
        for t in pending:
            t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            dropped = [round(time.perf_counter() - t0, 3)] * len(pending)
    return [t.result() for t in tasks if not t.cancelled()], dropped


# A route that cannot answer for a reason of its own — the model is gone at the provider (HTTP 404 / 410), the
# gateway has no grant or key for it — is set aside for a while instead of being asked again at every decision
# (2026-11-13: with the OpenRouter credit empty, each preflight decision spent 4.4 s on two such routes before
# failing, most of the time the caller waits). It is still named in `attempts` and `calls`, and asked again after.
UNAVAILABLE_S = 600.0
_unavailable: dict[str, tuple[float, str]] = {}


def _route_level(why: str) -> bool:
    return why.startswith(("HTTP 404", "HTTP 410", "missing_grant", "key_unavailable"))


async def decisions(body: dict, *, chain: list[str], key, client, log, balance=None) -> tuple[int, dict]:
    """Execute a decision request along the Router's chain. `log(entry)` receives one entry per physical call."""
    state, questions = body.get("state"), body.get("questions")
    if not isinstance(state, dict) or not isinstance(questions, dict) or not questions:
        return 400, {"error": "state (object) and questions (non-empty object) required"}
    samples = body.get("samples", 1)
    if isinstance(samples, bool) or not isinstance(samples, int) or not 1 <= samples <= MAX_SAMPLES:
        return 400, {"error": f"samples must be an integer 1..{MAX_SAMPLES}"}
    if not chain:
        return 503, {"error": "no_decision_chain", "attempts": []}
    models, refused = _requested(body, chain)
    if refused:
        return 400, {"error": refused, "chain": chain}
    floor, timeout = _floor(body), _timeout(body)
    attempts: list[dict] = []
    calls: list[dict] = []
    for model in models:
        provider = provider_of(model)
        aside = _unavailable.get(model)
        if aside and time.monotonic() < aside[0]:
            call = {"provider": provider, "model": model, "ok": False, "skipped": "route_unavailable",
                    "error": aside[1], "seconds": 0}
            attempts.append({"provider": provider, "model": model, "reason": f"route_unavailable: {aside[1]}"})
            calls.append(call)
            log({**call})
            continue
        if floor is not None and balance is not None and not is_free(model):
            bal = await balance()
            if bal is not None and bal < floor:
                attempts.append({"provider": provider, "model": model, "reason": "balance_below_floor"})
                calls.append({"provider": provider, "model": model, "ok": False, "skipped": "balance_below_floor",
                              "seconds": 0})
                log({"provider": provider, "model": model, "ok": False, "seconds": 0, "skipped": "balance_below_floor"})
                continue

        async def once(model=model, provider=provider):
            t0 = time.perf_counter()
            try:
                res = await decide_once(client, key, model, state, questions, timeout)
            except Exception as exc:  # noqa: BLE001 — the next model of the chain
                call = {"provider": provider, "model": model, "ok": False, "error": reason(exc),
                        "seconds": round(time.perf_counter() - t0, 3)}
                log({**call})
                return call, None
            call = {"provider": provider, "model": model, "ok": True, "seconds": round(time.perf_counter() - t0, 3),
                    "cost_usd": res["cost_usd"], "cost_status": res["cost_status"], "input_tokens": res["input_tokens"]}
            log({**call, "usage": {"in": res["input_tokens"], "out": 0, "cached": None}})
            return call, res
        got, dropped = await _samples(once, samples, _straggler(body))
        calls += [c for c, _ in got]
        for seconds in dropped:              # a sample the answer did not wait for: counted, not an error of the model
            call = {"provider": provider, "model": model, "ok": False, "skipped": "straggler", "seconds": seconds}
            calls.append(call)
            log({**call})
        ok = [res for _, res in got if res is not None]
        if not ok:
            why = str(got[0][0]["error"])
            attempts.append({"provider": provider, "model": model, "reason": why})
            if all(_route_level(str(c.get("error") or "")) for c, _ in got):
                _unavailable[model] = (time.monotonic() + UNAVAILABLE_S, why[:120])
            continue
        _unavailable.pop(model, None)
        first = ok[0]
        out = {"answers": first["answers"] if len(ok) == 1 else merge_answers([r["answers"] for r in ok]),
               "usage": first["usage"], "model": first["model"] if provider == "openrouter" else model,
               "provider": provider, "route": f"{provider}/{model}", "calls": calls, "attempts": attempts}
        if samples > 1:
            out["samples"] = len(ok)
        return 200, out
    return 502, {"error": "no decision model answered", "attempts": attempts, "calls": calls}


async def rerank_once(client, key, model: str, query: str, documents: list[str], top_n: int, timeout: float) -> dict:
    r = await client.post(OPENROUTER_RERANK, headers={"Authorization": f"Bearer {key('OPENROUTER_API_KEY')}"},
                          json={"model": model, "query": query, "documents": documents, "top_n": top_n}, timeout=timeout)
    data = _json(r)
    if r.status_code >= 400 or not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ProviderError(r.status_code, _error_code(data))
    results = []
    for row in data["results"]:
        idx = row.get("index") if isinstance(row, dict) else None
        if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(documents):
            results.append({"index": idx, "relevance_score": _float(row.get("relevance_score"))})
    if not results and documents:
        raise ProviderError(r.status_code, "empty_results")
    usage = data.get("usage") or {}
    cost = _float(usage.get("cost"))
    return {"results": results, "usage": usage, "model": data.get("model") or model, "cost_usd": cost,
            "cost_status": "reported" if cost is not None else "unknown"}


async def rerank(body: dict, *, routes: list[dict], key, client, log, balance=None) -> tuple[int, dict]:
    """Execute a rerank request on the Router's `rerank` poste routes, in order."""
    query, documents = body.get("query"), body.get("documents")
    if not isinstance(query, str) or not query.strip():
        return 400, {"error": "query (non-empty string) required"}
    if not isinstance(documents, list) or not documents or len(documents) > MAX_DOCUMENTS \
            or not all(isinstance(d, str) for d in documents):
        return 400, {"error": f"documents must be 1..{MAX_DOCUMENTS} strings"}
    top_n = body.get("top_n") or len(documents)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        return 400, {"error": "top_n must be a positive integer"}
    top_n = min(top_n, len(documents))
    offered = [r["model"] for r in routes if r.get("model")]
    if not offered:
        return 503, {"error": "no_rerank_route", "attempts": []}
    models, refused = _requested(body, offered)
    if refused:
        return 400, {"error": refused, "offered": offered}
    floor, timeout = _floor(body), _timeout(body)
    attempts = []
    for route in [r for r in routes if r.get("model") in models]:
        provider, model = route.get("provider"), route["model"]
        base = {"provider": provider, "model": model}
        if provider != "openrouter":
            attempts.append({**base, "reason": f"no_adapter:{provider}"})
            continue
        if floor is not None and balance is not None and not is_free(model):
            bal = await balance()
            if bal is not None and bal < floor:
                attempts.append({**base, "reason": "balance_below_floor"})
                log({**base, "ok": False, "seconds": 0, "skipped": "balance_below_floor"})
                continue
        t0 = time.perf_counter()
        try:
            res = await rerank_once(client, key, model, query, documents, top_n, timeout)
        except Exception as exc:  # noqa: BLE001 — next route of the poste
            attempts.append({**base, "reason": reason(exc)})
            log({**base, "ok": False, "seconds": round(time.perf_counter() - t0, 3), "error": reason(exc)})
            continue
        seconds = round(time.perf_counter() - t0, 3)
        log({**base, "ok": True, "seconds": seconds, "cost_usd": res["cost_usd"], "cost_status": res["cost_status"],
             "usage": {"in": res["usage"].get("prompt_tokens") or res["usage"].get("total_tokens"), "out": 0,
                       "cached": None}})
        return 200, {"results": res["results"], "model": model, "provider": provider, "route": f"{provider}/{model}",
                     "usage": res["usage"], "cost_usd": res["cost_usd"], "cost_status": res["cost_status"],
                     "seconds": seconds, "attempts": attempts}
    return 502, {"error": "no rerank route answered", "attempts": attempts}


class Balance:
    """OpenRouter's remaining credit, cached 5 minutes; None when unknown (never blocks a free model)."""

    def __init__(self, client, key, ttl: float = 300):
        self.client, self.key, self.ttl = client, key, ttl
        self.value: tuple[float, float | None] | None = None

    async def __call__(self) -> float | None:
        if self.value and time.time() - self.value[0] < self.ttl:
            return self.value[1]
        try:
            r = await self.client.get(OPENROUTER_CREDITS, headers={"Authorization": f"Bearer {self.key('OPENROUTER_API_KEY')}"},
                                      timeout=15)
            d = r.json()["data"]
            value = float(d["total_credits"]) - float(d["total_usage"])
        except Exception:  # noqa: BLE001 — unknown balance: the floor cannot refuse
            value = None
        self.value = (time.time(), value)
        return value
