"""From a chosen model to something Hermes can run: ordered execution routes and live provider probes.

A route = (walter provider, Hermes provider name, model id at that provider, reasoning level). The Hermes plugin
runs the first route with `hermes chat --oneshot --provider P -m M` and falls back to the next one on failure.
"""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import collect
from . import select as sel

# walter-router provider -> Hermes provider (config.yaml / built-in). Kie has one Hermes provider per protocol:
# `kie` = Anthropic endpoint (/claude, Claude models), `kie-codex` = Responses endpoint (/codex/v1, GPT models).
HERMES_PROVIDERS = {"codex": "openai-codex", "openrouter": "openrouter", "kie": "kie", "arnict": "arnict"}
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
    if offer["provider"] == "kie":  # Kie ids are the canonical ids (claude-opus-5-5, gpt-6-1-sol)
        if offer["model_id"].startswith("claude-"):
            return "kie", offer["model_id"], "kie"
        if offer["model_id"] in KIE_CODEX_MODELS:
            return "kie-codex", offer["model_id"], "kie-codex"
        return None
    hp = (offer.get("pricing") or {}).get("hermes_provider") or HERMES_PROVIDERS.get(offer["provider"])
    return (hp, offer["offer_key"], offer["provider"]) if hp else None


# Monsieur's fallback order (2026-10-02): subscription (Codex) first, then Kie if available and not dearer than
# OpenRouter by more than KIE_MAX_PREMIUM, then OpenRouter as the last resort. Arnict (unrestricted) ranks with Kie.
PROVIDER_RANK = {"kie": 1, "kie-codex": 1, "arnict": 1, "openrouter": 3}
KIE_MAX_PREMIUM = 1.25
UNRELIABLE_MIN_RUNS, UNRELIABLE_FAIL_RATE, RELIABILITY_DAYS = 3, 0.5, 14


def reliability(conn, provider: str, model: str) -> dict:
    """Recent real executions of this provider x model (models.exec_log, skipped attempts excluded)."""
    r = conn.execute("""select count(*) as n, count(*) filter (where not ok) as failed from (
                          select ok from models.exec_log where provider = %s and model = %s and skipped is null
                          and at > now() - make_interval(days => %s) order by at desc limit 10) x""",
                     (provider, model, RELIABILITY_DAYS)).fetchone()
    unreliable = r["n"] >= UNRELIABLE_MIN_RUNS and r["failed"] / r["n"] >= UNRELIABLE_FAIL_RATE
    return {"runs": r["n"], "failed": r["failed"], "unreliable": unreliable}


def routes(conn, model_id: str, variant: str = "", preferred: str | None = None) -> list[dict]:
    """Every way Hermes can run this chat model, in Monsieur's order: subscription, Kie (if not much dearer),
    OpenRouter last. Providers whose last probe failed, or that failed most recent real runs, go to the end."""
    snaps = sel.latest_snapshots(conn)
    status = {r["provider"]: r for r in conn.execute("select * from models.provider_status")}
    out = []
    for o in sel.load_offers(conn, snaps).get(model_id, []):
        run = _runnable(o)
        if not run:
            continue
        hp, model, key = run
        st = status.get(key)
        rel = reliability(conn, hp, model)
        out.append({"provider": o["provider"], "hermes_provider": hp, "model": model,
                    "reasoning": REASONING.get(variant), "access": o["access"],
                    "blended_1m": sel.blended(o), "probe_ok": None if st is None else st["ok"],
                    "unreliable": rel["unreliable"], "recent_runs": rel["runs"], "recent_failures": rel["failed"]})
    or_price = min((r["blended_1m"] for r in out if r["hermes_provider"] == "openrouter" and r["blended_1m"]),
                   default=None)

    def rank(r: dict) -> float:
        if r["access"] == "subscription":
            return 0
        base = PROVIDER_RANK.get(r["hermes_provider"], 2)
        if base == 1 and r["provider"] == "kie" and or_price and r["blended_1m"] and \
                r["blended_1m"] > or_price * KIE_MAX_PREMIUM:
            return 3.5  # Kie clearly dearer than OpenRouter here: after it
        return base

    out.sort(key=lambda r: (r["probe_ok"] is False, r["unreliable"], rank(r), r["provider"] != preferred,
                            r["blended_1m"] if r["blended_1m"] is not None else 1e9))
    return out


def log(conn, entry: dict) -> int:
    """One routed execution attempt (from the Hermes plugin or the media executor)."""
    keys = ("task", "role", "model_id", "provider", "model", "ok", "skipped", "seconds", "cost_usd", "fallback_for", "kind")
    row = {k: entry.get(k) for k in keys}
    row["ok"] = bool(row["ok"])
    row["kind"] = row["kind"] or "text"
    return conn.execute(f"""insert into models.exec_log ({", ".join(keys)}) values ({", ".join(["%s"] * len(keys))})
                            returning exec_id""", [row[k] for k in keys]).fetchone()["exec_id"]


_TIMEOUT = 90


def _post(url: str, body: dict, headers: dict, timeout: int | None = None, must: str | None = None) -> tuple[bool, str]:
    """POST and read the whole answer (SSE included); ok = HTTP 200, non-empty, containing `must` when given
    (a Kie stream can be HTTP 200 and still end without a message)."""
    req = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                 "User-Agent": UA, **headers})
    try:
        with urlopen(req, timeout=timeout or _TIMEOUT) as resp:  # noqa: S310 (fixed provider endpoints)
            data = resp.read(200000)
            ok = resp.status == 200 and bool(data.strip()) and (must is None or must.encode() in data)
            return ok, f"HTTP {resp.status}" + ("" if ok else " (réponse incomplète)")
    except HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read(200).decode('utf-8', 'replace')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:200]


def probe(conn, only: str | None = None, timeout: int = 90) -> dict:
    """Tiny live call per API provider (max 5 output tokens, streamed when the provider streams for Hermes).
    A provider that answers but slower than SLOW_MS is recorded not ok ('dégradé'). Codex is the subscription
    Hermes itself uses all day: not probed here (the Hermes run falls back if it fails)."""
    key = collect._env_value
    kie = key("KIE_API_KEY") or ""
    checks = {
        "kie": lambda: _post("https://api.kie.ai/claude/v1/messages",
                             {"model": "claude-sonnet-5", "max_tokens": 5, "stream": True,
                              "messages": [{"role": "user", "content": "OK"}]},
                             {"x-api-key": kie, "Authorization": f"Bearer {kie}", "anthropic-version": "2023-06-01"},
                             must="message_stop"),
        "kie-codex": lambda: _post("https://api.kie.ai/codex/v1/responses",
                                   {"model": "gpt-6-luna", "input": "OK", "stream": False, "max_output_tokens": 16},
                                   {"Authorization": f"Bearer {kie}"}),
        "openrouter": lambda: _post("https://openrouter.ai/api/v1/chat/completions",
                                    {"model": "openai/gpt-6-luna", "max_tokens": 5,
                                     "messages": [{"role": "user", "content": "OK"}]},
                                    {"Authorization": f'Bearer {key("OPENROUTER_API_KEY")}'}),
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
