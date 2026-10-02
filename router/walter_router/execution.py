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

# walter-router provider -> Hermes provider (config.yaml / built-in). Kie's Hermes provider is its Anthropic
# endpoint (/claude), so only Claude models can run through it.
HERMES_PROVIDERS = {"codex": "openai-codex", "openrouter": "openrouter", "kie": "kie", "arnict": "arnict"}
REASONING = {"non-reasoning": "none", "minimal": "minimal", "low": "low", "medium": "medium", "high": "high",
             "xhigh": "xhigh", "max": "max"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"


def _runnable(offer: dict) -> str | None:
    hp = (offer.get("pricing") or {}).get("hermes_provider") or HERMES_PROVIDERS.get(offer["provider"])
    if not hp or offer["interface"] != "chat":
        return None
    if offer["provider"] == "kie" and not offer["offer_key"].startswith("claude-"):
        return None
    return hp


def routes(conn, model_id: str, variant: str = "", preferred: str | None = None) -> list[dict]:
    """Every way Hermes can run this chat model: preferred provider, then subscription, then paid by blended
    price; providers whose last live probe failed go last (kept as a last resort, flagged)."""
    snaps = sel.latest_snapshots(conn)
    status = {r["provider"]: r for r in conn.execute("select * from models.provider_status")}
    out = []
    for o in sel.load_offers(conn, snaps).get(model_id, []):
        hp = _runnable(o)
        if not hp:
            continue
        st = status.get(o["provider"])
        out.append({"provider": o["provider"], "hermes_provider": hp, "model": o["offer_key"],
                    "reasoning": REASONING.get(variant), "access": o["access"],
                    "blended_1m": sel.blended(o), "probe_ok": None if st is None else st["ok"]})
    out.sort(key=lambda r: (r["probe_ok"] is False, r["provider"] != preferred, r["access"] != "subscription",
                            r["blended_1m"] if r["blended_1m"] is not None else 1e9))
    return out


def _post(url: str, body: dict, headers: dict, timeout: int = 60) -> tuple[bool, str]:
    req = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
                                                                 "User-Agent": UA, **headers})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed provider endpoints)
            return resp.status == 200, f"HTTP {resp.status}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read(200).decode('utf-8', 'replace')}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"[:200]


def probe(conn) -> dict:
    """Tiny live call per API provider (max 5 output tokens). Codex is a subscription used by Hermes itself
    every day: not probed here (the Hermes run falls back if it fails)."""
    key = collect._env_value
    checks = {
        "kie": lambda: _post("https://api.kie.ai/claude/v1/messages",
                             {"model": "claude-sonnet-5", "max_tokens": 5, "messages": [{"role": "user", "content": "OK"}]},
                             {"x-api-key": key("KIE_API_KEY") or "", "Authorization": f'Bearer {key("KIE_API_KEY")}',
                              "anthropic-version": "2023-06-01"}),
        "openrouter": lambda: _post("https://openrouter.ai/api/v1/chat/completions",
                                    {"model": "openai/gpt-6-luna", "max_tokens": 5,
                                     "messages": [{"role": "user", "content": "OK"}]},
                                    {"Authorization": f'Bearer {key("OPENROUTER_API_KEY")}'}),
        "arnict": lambda: _post("https://api.arnict.com/v1/chat/completions",
                                {"model": "zai/glm-5.3-flash-uncensored", "max_tokens": 5,
                                 "messages": [{"role": "user", "content": "OK"}]},
                                {"Authorization": f'Bearer {key("ARNICT_API_KEY")}'}),
    }
    out = {}
    for provider, fn in checks.items():
        t0 = time.monotonic()
        ok, detail = fn()
        ms = int((time.monotonic() - t0) * 1000)
        conn.execute("""insert into models.provider_status (provider, ok, checked_at, latency_ms, detail)
                        values (%s, %s, now(), %s, %s) on conflict (provider) do update set ok = excluded.ok,
                        checked_at = excluded.checked_at, latency_ms = excluded.latency_ms, detail = excluded.detail""",
                     (provider, ok, ms, detail))
        out[provider] = {"ok": ok, "ms": ms, "detail": detail}
    return out
