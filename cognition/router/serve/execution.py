"""Ordered provider routes and execution metadata for Walter consumers.

Native Walter text execution owns its tools and uses the public walter-llm exact-call port.
Hermes direct-provider bindings remain available through the host-owned runtime adapter.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from walter_router import instance
from walter_router.analysis import select as sel

# walter-router provider -> Hermes provider (config.yaml / built-in). Kie has one Hermes provider per protocol:
# `kie` = Anthropic endpoint (/claude, Claude models), `kie-codex` = Responses endpoint (/codex/v1, GPT models).
HERMES_PROVIDERS = {"codex": "openai-codex", "openrouter": "openrouter", "kie": "kie", "arnict": "arnict"}
NATIVE_ONLY = {"venice", "antigravity"}   # providers walter-llm runs itself (2026-10-30), with no Hermes provider
KIE_CODEX_MODELS = {"gpt-6-1-sol", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-5-6-sol", "gpt-5-6-terra",
                    "gpt-5-6-luna", "gpt-5-5"}  # GET https://api.kie.ai/codex/v1/models, 2026-10-02
MIN_CREDIT_USD = 1.0  # below this, OpenRouter routes go last (a 402 after minutes of agent work is worse)
SLOW_MS = 30000  # a 5-token probe slower than this = degraded (Kie Claude took 64 s on 2026-10-02)
REASONING = {"non-reasoning": "none", "minimal": "minimal", "low": "low", "medium": "medium", "high": "high",
             "xhigh": "xhigh", "max": "max"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"


def _runnable(offer: dict) -> tuple[str, str, str] | None:
    """(Hermes provider, model id at that provider, status key) or None when Hermes cannot run this offer."""
    if offer["interface"] != "chat":
        return None
    if offer["provider"] == "claude-pro":
        # Native Walter transport only; never write this provider into Hermes' direct-provider config.
        return None, offer["offer_key"], "claude-pro"
    if offer["provider"] in NATIVE_ONLY:   # no Hermes provider: walter-llm runs them; Hermes consumers skip them
        return None, offer["offer_key"], offer["provider"]
    if offer["provider"] == "kie":  # Kie ids are the canonical ids (claude-opus-5-5, gpt-6-1-sol)
        if offer["model_id"].startswith("claude-"):
            return "kie", offer["model_id"], "kie"
        if offer["model_id"] in KIE_CODEX_MODELS:
            return "kie-codex", offer["model_id"], "kie-codex"
        return None
    hp = (offer.get("pricing") or {}).get("hermes_provider") or HERMES_PROVIDERS.get(offer["provider"])
    return (hp, offer["offer_key"], offer["provider"]) if hp else None


# the owner's fallback order (2026-10-02): subscription (Codex) first, then Kie if available and not dearer than
# OpenRouter by more than KIE_MAX_PREMIUM, then OpenRouter as the last resort. Arnict (unrestricted) ranks with Kie.
PROVIDER_RANK = {"kie": 1, "kie-codex": 1, "arnict": 1, "openrouter": 3}
KIE_MAX_PREMIUM = 1.25
UNRELIABLE_MIN_RUNS, UNRELIABLE_FAIL_RATE, RELIABILITY_DAYS = 3, 0.5, 14


def reliability(conn, provider: str, model: str) -> dict:
    """Recent real executions of this provider x model (models.exec_log, skipped attempts excluded: walter-llm logs a
    subscription's rate-limit refusal as skipped='rate_limit', a burst limit is not unreliability)."""
    r = conn.execute("""select count(*) as n, count(*) filter (where not ok) as failed from (
                          select ok from models.exec_log where provider = %s and model = %s and skipped is null
                          and at > now() - make_interval(days => %s) order by at desc limit 10) x""",
                     (provider, model, RELIABILITY_DAYS)).fetchone()
    unreliable = r["n"] >= UNRELIABLE_MIN_RUNS and r["failed"] / r["n"] >= UNRELIABLE_FAIL_RATE
    return {"runs": r["n"], "failed": r["failed"], "unreliable": unreliable}


QUOTA_SWITCH = 90.0   # weekly meter %: above it a subscription route goes after the paid ones (quota nearly spent)


def subscription_accounts(conn) -> dict[str, list[dict]]:
    """route provider -> its subscriptions in declaration order, each with its own quota and cost price. Several
    accounts may serve one provider (two Claude accounts, 2026-11-07): each becomes its own route. An account with no
    cost row yet (just declared) still gets a route, with its live meters."""
    from walter_router.plan import subscriptions
    by_sub = {r["sub_id"]: dict(r) for r in conn.execute("select * from models.latest_subscription_costs")}
    meters = {r["sub_id"]: float(r["used_percent"]) for r in conn.execute(
        """select sub_id, used_percent from models.latest_subscription_usage
           where window_name = 'weekly' and source <> 'calibration'""")}
    sessions = {r["sub_id"]: float(r["used_percent"]) for r in conn.execute(
        "select sub_id, used_percent from models.latest_subscription_usage where window_name = 'session'")}
    out: dict[str, list[dict]] = {}
    for sub in subscriptions.load():
        if not sub.get("route_provider") or sub.get("retired"):
            continue
        cost = by_sub.get(sub["id"])
        if cost is None and sub["id"] not in meters:
            continue
        out.setdefault(sub["route_provider"], []).append({
            **(cost or {}), "sub_id": sub["id"], "plan": sub.get("plan"),
            "used_percent": meters.get(sub["id"], (cost or {}).get("used_percent")),
            "session_used_percent": sessions.get(sub["id"])})
    return out


def subscription_costs(conn) -> dict[str, dict]:
    """route provider (codex) -> its first subscription: cost price, plan name, quotas (see subscription_accounts)."""
    return {p: subs[0] for p, subs in subscription_accounts(conn).items()}


def host_order(conn, model_id: str, usage: str = "interactive") -> list[dict]:
    """Usable hosts behind OpenRouter for this model, cheapest first (models.usable_endpoints); flex tier only for
    background work."""
    return [dict(r) for r in conn.execute(
        """select tag, host, quantization, service_tier, price_in_1m, price_out_1m, blended_1m, uptime_1d
           from models.usable_endpoints where model_id = %s and (%s = 'background' or coalesce(service_tier, '') <> 'flex')
             and coalesce(service_tier, '') not in ('priority', 'fast', 'ultrafast')   -- 2x-6x the price: never imposed
           order by uptime_1d is null, blended_1m, uptime_1d desc nulls last""", (model_id, usage))]


def routes(conn, model_id: str, variant: str = "", preferred: str | None = None, usage: str = "interactive",
           modes: list[str] | None = None) -> list[dict]:
    """Every way Hermes can run this chat model, in the owner's order: subscription (while its weekly quota is not
    nearly spent, always first then), Kie (if not much dearer), OpenRouter last — on its cheapest usable host
    (2026-10-22). Paid providers whose last probe failed, or that failed most recent real runs, go to their end. Each route carries its price: the
    subscription's cost price per token, Kie's price, the chosen OpenRouter host's price."""
    snaps = sel.latest_snapshots(conn)
    status = {r["provider"]: r for r in conn.execute("select * from models.provider_status")}
    out = []
    need = set(modes or [])   # inputs the task needs besides text (video): only offers that declare them
    for o in sel.load_offers(conn, snaps).get(model_id, []):
        if need and not need <= set(o.get("modes") or []):
            continue
        run = _runnable(o)
        if not run:
            continue
        hp, model, key = run
        st = status.get(key)
        rel = reliability(conn, hp or key, model)
        out.append({"provider": o["provider"], "hermes_provider": hp, "model": model,
                    "reasoning": REASONING.get(variant), "access": o["access"],
                    "blended_1m": sel.blended(o), "probe_ok": None if st is None else st["ok"],
                    "unreliable": rel["unreliable"], "recent_runs": rel["runs"], "recent_failures": rel["failed"]})

    list_in = next((o.get("price_in_1m") for o in sel.load_offers(conn, snaps).get(model_id, [])
                    if o["provider"] == "openrouter" and o["interface"] == "chat" and o.get("price_in_1m") is not None), None)
    list_out = next((o.get("price_out_1m") for o in sel.load_offers(conn, snaps).get(model_id, [])
                     if o["provider"] == "openrouter" and o["interface"] == "chat" and o.get("price_out_1m") is not None), None)
    hosts = None
    accounts = subscription_accounts(conn)
    expanded = []
    for r in out:   # one route per account of a subscription provider, in declaration order (keeps its prompt cache)
        subs = accounts.get(r["provider"]) if r["access"] == "subscription" else None
        if subs and len(subs) > 1:
            expanded += [{**r, "account": c["sub_id"], "_sub": c} for c in subs]
        else:
            expanded.append({**r, "_sub": subs[0]} if subs else r)
    out = expanded
    for r in out:
        c = r.pop("_sub", None)
        if r["access"] == "subscription" and c:
            ratio = c.get("ratio_pace") or c.get("ratio_full")
            r["subscription"] = {"plan": c.get("plan"), "quota_used_percent": c.get("used_percent"),
                                 "session_used_percent": c.get("session_used_percent"),
                                 "cost_ratio": round(ratio, 4) if ratio else None}
            if r.get("account"):
                r["subscription"]["account"] = r["account"]
            if ratio and list_in is not None:
                r["cost_price_1m"] = {"in": round(list_in * ratio, 4), "out": round((list_out or 0) * ratio, 4)}
        if r["hermes_provider"] == "openrouter":
            hosts = hosts if hosts is not None else host_order(conn, model_id, usage)
            if hosts:   # OpenRouter is told which hosts to use, cheapest usable first, the others as fallbacks
                r["or_provider"] = {"order": [h["tag"] for h in hosts[:8]], "allow_fallbacks": True}
                r["host"] = {k: hosts[0][k] for k in ("host", "tag", "quantization", "service_tier", "price_in_1m", "price_out_1m")}
                r["blended_1m"] = hosts[0]["blended_1m"]

    or_price = min((r["blended_1m"] for r in out if r["hermes_provider"] == "openrouter" and r["blended_1m"]),
                   default=None)

    def quota_spent(r: dict) -> bool:
        q = (r.get("subscription") or {}).get("quota_used_percent")
        session = (r.get("subscription") or {}).get("session_used_percent")
        return (q is not None and q >= QUOTA_SWITCH) or (session is not None and session >= 100)

    def rank(r: dict) -> float:
        if r["access"] == "subscription":
            return 3.8 if quota_spent(r) else 0
        base = PROVIDER_RANK.get(r["hermes_provider"], 2)
        if base == 1 and r["provider"] == "kie" and or_price and r["blended_1m"] and \
                r["blended_1m"] > or_price * KIE_MAX_PREMIUM:
            return 3.5  # Kie clearly dearer than OpenRouter here: after it
        return base

    def subscription_first(r: dict) -> bool:
        """A subscription with quota left always goes before every paid route, whatever its recent failures: trying it
        costs one quick refusal at worst, while a paid route ahead of it bills every call (2026-10-28: 40 Opus calls
        on OpenRouter while the Claude subscription had 24 % of its week left; Monsieur, 2026-10-30)."""
        return r["access"] == "subscription" and not quota_spent(r)

    out.sort(key=lambda r: (not subscription_first(r), r["probe_ok"] is False, r["unreliable"], rank(r),
                            r["provider"] != preferred, r["blended_1m"] if r["blended_1m"] is not None else 1e9))
    return out


def _uuid(value) -> str | None:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except ValueError:
        return None


def log(conn, entry: dict) -> int:
    """One routed execution attempt (from the Hermes plugin or the media executor)."""
    keys = ("task", "role", "model_id", "provider", "model", "ok", "skipped", "seconds", "cost_usd", "fallback_for", "kind",
            "run_id", "task_id", "usage", "cost_status", "account")
    row = {k: entry.get(k) for k in keys}
    row["ok"] = bool(row["ok"])
    row["kind"] = row["kind"] or "text"
    # Walter Run Plane: the caller's run and sub-agent task travel as WALTER_RUN_ID / WALTER_TASK_ID.
    row["run_id"] = _uuid(entry["run_id"] if "run_id" in entry else os.environ.get("WALTER_RUN_ID"))
    row["task_id"] = _uuid(entry["task_id"] if "task_id" in entry else os.environ.get("WALTER_TASK_ID"))
    row["usage"] = json.dumps(row["usage"]) if isinstance(row["usage"], dict) else None
    row["cost_status"] = row["cost_status"] if row["cost_status"] in {"unknown", "reported", "estimated", "legacy"} else \
        ("legacy" if row["cost_usd"] is not None else "unknown")
    return conn.execute(f"""insert into models.exec_log ({", ".join(keys)}) values ({", ".join(["%s"] * len(keys))})
                            returning exec_id""", [row[k] for k in keys]).fetchone()["exec_id"]


_TIMEOUT = 90


def _stream_error(data: bytes) -> str:
    """The provider's own reason when an HTTP 200 stream ends on an error event (Kie: « no_available_account »)."""
    m = re.search(rb'"error"\s*:\s*\{[^{}]*?"message"\s*:\s*"([^"]{1,160})"', data)
    return f" : {m.group(1).decode('utf-8', 'replace')}" if m else ""


def _kie_media(kie: str) -> tuple[bool, str]:
    """Kie's media API (video, image, music tasks) is another service than its Claude chat API: usable when the
    account answers and has credit. No generation is started (2026-10-26: a Claude-only outage at Kie had sent
    every Kie video and image to OpenRouter)."""
    try:
        req = Request("https://api.kie.ai/api/v1/chat/credit", headers={"Authorization": f"Bearer {kie}", "User-Agent": UA})
        with urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 (fixed provider endpoint)
            body = json.loads(resp.read())
    except HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read(200).decode('utf-8', 'replace')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:200]
    credit = body.get("data")
    if body.get("code") != 200 or not isinstance(credit, (int, float)):
        return False, f'HTTP 200 (réponse inattendue : {str(body.get("msg"))[:120]})'
    if credit <= 0:
        return False, f"crédit épuisé : {credit} crédits"
    return True, f"HTTP 200, crédit {credit} crédits"


def _post(url: str, body: dict, headers: dict, timeout: int | None = None, must: str | None = None) -> tuple[bool, str]:
    """POST and read the whole answer (SSE included); ok = HTTP 200, non-empty, containing `must` when given
    (a Kie stream can be HTTP 200 and still end without a message)."""
    req = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                 "User-Agent": UA, **headers})
    try:
        with urlopen(req, timeout=timeout or _TIMEOUT) as resp:  # noqa: S310 (fixed provider endpoints)
            data = resp.read(200000)
            ok = resp.status == 200 and bool(data.strip()) and (must is None or must.encode() in data)
            return ok, f"HTTP {resp.status}" + ("" if ok else f" (réponse incomplète{_stream_error(data)})")
    except HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read(200).decode('utf-8', 'replace')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:200]


def probe(conn, only: str | None = None, timeout: int = 90) -> dict:
    """Tiny live call per API provider (max 5 output tokens, streamed when the provider streams for Hermes).
    A provider that answers but slower than SLOW_MS is recorded not ok ('dégradé'). Codex is the subscription
    Hermes itself uses all day: not probed here (the Hermes run falls back if it fails). Kie has three services
    probed apart: `kie` = its Claude chat API, `kie-codex` = its Codex responses API, `kie-media` = its media
    tasks (account and credit, no generation)."""
    key = instance.env_value
    kie = key("KIE_API_KEY") or ""
    checks = {
        "kie": lambda: _post("https://api.kie.ai/claude/v1/messages",
                             {"model": "claude-sonnet-5", "max_tokens": 5, "stream": True,
                              "messages": [{"role": "user", "content": "OK"}]},
                             {"x-api-key": kie, "Authorization": f"Bearer {kie}", "anthropic-version": "2023-06-01"},
                             must="message_stop"),
        "kie-media": lambda: _kie_media(kie),
        "kie-codex": lambda: _post("https://api.kie.ai/codex/v1/responses",
                                   {"model": "gpt-6-luna", "input": "OK", "stream": False, "max_output_tokens": 16},
                                   {"Authorization": f"Bearer {kie}"}),
        "openrouter": lambda: _post("https://openrouter.ai/api/v1/chat/completions",
                                    {"model": "openai/gpt-6-luna", "max_tokens": 5,
                                     "messages": [{"role": "user", "content": "OK"}]},
                                    {"Authorization": f'Bearer {key("OPENROUTER_API_KEY")}'}),
        "venice": lambda: _post("https://api.venice.ai/api/v1/chat/completions",
                                {"model": "deepseek-v4-1-flash-1017-uncensored", "max_tokens": 5,
                                 "messages": [{"role": "user", "content": "OK"}]},
                                {"Authorization": f'Bearer {instance.secret_value("VENICE_API_KEY")}'}),
        "arnict": lambda: _post("https://api.arnict.com/v1/chat/completions",
                                {"model": "zai/glm-5.3-flash-uncensored", "max_tokens": 5,
                                 "messages": [{"role": "user", "content": "OK"}]},
                                {"Authorization": f'Bearer {key("ARNICT_API_KEY")}'}),
    }
    def openrouter() -> tuple[bool, str]:
        """A paid route is only usable with credit left: the 5-token call can pass on a tiny negative balance."""
        ok, detail = _post("https://openrouter.ai/api/v1/chat/completions",
                           {"model": "openai/gpt-6-luna", "max_tokens": 5, "messages": [{"role": "user", "content": "OK"}]},
                           {"Authorization": f'Bearer {key("OPENROUTER_API_KEY")}'})
        try:
            req = Request("https://openrouter.ai/api/v1/credits", headers={"Authorization": f'Bearer {key("OPENROUTER_API_KEY")}'})
            with urlopen(req, timeout=20) as resp:  # noqa: S310
                c = json.loads(resp.read())["data"]
            left = c["total_credits"] - c["total_usage"]
            if left < MIN_CREDIT_USD:
                return False, f"crédit épuisé : {left:.2f} $ restant"
            return ok, f"{detail}, crédit {left:.2f} $"
        except Exception:  # noqa: BLE001 — balance unknown: keep the call verdict
            return ok, detail

    checks["openrouter"] = openrouter
    out = {}
    global _TIMEOUT
    _TIMEOUT = timeout
    for provider, fn in checks.items():
        if only and provider != only:
            continue
        t0 = time.monotonic()
        ok, detail = fn()
        ms = int((time.monotonic() - t0) * 1000)
        if ok and ms > SLOW_MS:
            ok, detail = False, f"dégradé : {ms / 1000:.0f} s pour 5 tokens"
        conn.execute("""insert into models.provider_status (provider, ok, checked_at, latency_ms, detail)
                        values (%s, %s, now(), %s, %s) on conflict (provider) do update set ok = excluded.ok,
                        checked_at = excluded.checked_at, latency_ms = excluded.latency_ms, detail = excluded.detail""",
                     (provider, ok, ms, detail))
        out[provider] = {"ok": ok, "ms": ms, "detail": detail}
    return out
