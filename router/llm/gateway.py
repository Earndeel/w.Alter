#!/bin/sh
"""exec" "$(dirname "$(readlink -f "$0")")/venv/bin/python3" "$0" "$@"  # sh: run on the module venv
walter-llm — W.Alter's model gateway (P8.5 + P8.7): one OpenAI-compatible endpoint for every agent runtime.

    agent (DeepSeek Harness, Codex, scripts…) ──token──▶ walter-llm (127.0.0.1:8894)
        model = a Walter Router task ("coding", "document"…) or "auto"
        ├─ Walter Router  → ordered routes (provider, model, reasoning) for the task      [choice]
        ├─ walter-secrets → provider key read from the instance's vault, kept in RAM here [secrets]
        └─ LiteLLM        → provider protocol (Anthropic, Responses, OpenAI-compatible)   [adapters]

Agents never hold a provider key: they get a local per-agent token (sha256 in agents.json, 0600) that only allows
model calls through here (DeepSeek Harness' own docs: file permissions cannot keep keys away from an agent whose
tools run as the same user — a gateway can). Every attempt is logged (no content) to
the instance's log (config gateway.json) and to Walter Router's models.exec_log, so the router learns from these runs too.
A route that fails before its first token falls through to the next one.

Run:   gateway.py serve                 (127.0.0.1:8894)
       gateway.py add-agent NAME FILE   new token for NAME, written into a dsh credentials YAML or env:FILE[:VAR] (never printed)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request  # module level: FastAPI resolves endpoint annotations from module globals

HERE = Path(__file__).resolve().parent
ROUTER = "walter-router"   # Walter Router CLI on the PATH


def _walter(*args: str) -> str:
    """Walter's public interface (`walter` on the PATH): module roots and the active instance."""
    out = subprocess.run(["walter", *args], capture_output=True, text=True, timeout=30)
    if out.returncode or not out.stdout.strip():
        raise RuntimeError(f"walter {' '.join(args)} failed")
    return out.stdout.strip()


def _instance_path(value: str) -> Path:
    if value == "@instance" or value.startswith("@instance/"):
        return Path(_walter("instance", "path")) / value[len("@instance"):].lstrip("/")
    return Path(value).expanduser()


# Settings: the instance's config/llm/gateway.json, else the shipped default (log file, agent token hashes).
_CONF = json.loads(Path(_walter("instance", "config", "llm", "gateway.json")).read_text())
AGENTS = _instance_path(_CONF["agents"])
LOG = _instance_path(_CONF["log"])
sys.path.insert(0, _walter("path", "secrets"))   # walter-secrets public library (vault, mapping)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
DEFAULT_TASK = "coding"
# Codex routes = W.Alter's OWN Codex subscription session (grant `codex-subscription` of walter-secrets, also used by
# walter-skills), never Hermes' session. walter-secrets serves the access token and has the Codex CLI — the single
# writer of its rotating refresh token — renew it before expiry.
CODEX_GRANT = "codex-subscription"
CHATGPT_DIR = HERE / "chatgpt"                      # LiteLLM wants a token dir; nothing is ever stored there
os.environ.setdefault("CHATGPT_TOKEN_DIR", str(CHATGPT_DIR))
# LiteLLM prepends the Codex CLI's coding-agent prompt (~1.7k tokens) to every call: a neutral one for module jobs
os.environ.setdefault("CHATGPT_DEFAULT_INSTRUCTIONS", "You are a precise assistant for W.Alter's background jobs. Follow "
                      "the system and user instructions exactly; answer in the language of the request.")
KEY_TTL, ROUTE_TTL = 600, 600
KIE_GPT = ("gpt-",)
PAID = {"kie", "openrouter", "arnict", "venice"}   # providers billed per call (subscriptions are not)
# A subscription's rate-limit refusal is a burst limit (two parallel DSH calls, 2026-10-28), not an empty quota: wait
# and retry it before any paid route. The refusal is then logged skipped='rate_limit' (not counted as unreliability).
RATE_LIMIT_WAITS = (4, 12)
# Tests (walter-scenario, walter-lab: runs of channel `test`) may spend at most this on paid providers per window;
# above it every paid route is refused to them until the owner approves more (Monsieur, 2026-10-30: « au-dessus de
# 2 € les tests doivent être validés manuellement »). Ledger = the tests' paid calls and the owner's approvals.
TEST_BUDGET = {"paid_limit_eur": 2.0, "usd_per_eur": 1.10, "window_hours": 24,
               "ledger": "@instance/state/llm/test-spend.jsonl", **(_CONF.get("test_budget") or {})}


# ───────────────────────── secrets (Bitwarden through walter-secrets) ─────────────────────────
_keys: dict[str, tuple[float, str]] = {}
_keys_lock = threading.Lock()


def provider_key(env_name: str) -> str:
    """Value of the vault item mapped to `env_name` (walter_secrets.mapping), cached in this process only. A stale
    value is served while it is re-read in the background (a Bitwarden read takes seconds; a phone call cannot wait)."""
    with _keys_lock:
        hit = _keys.get(env_name)
        if hit and time.time() - hit[0] < KEY_TTL:
            return hit[1]
        if hit:
            _keys[env_name] = (time.time(), hit[1])   # one background re-read per TTL
            threading.Thread(target=_read_key, args=(env_name,), daemon=True).start()
            return hit[1]
    return _read_key(env_name)


def _read_key(env_name: str) -> str:
    from walter_secrets.mapping import entry
    from walter_secrets.vault import VAULT, audit
    e = entry(env_name)
    value = VAULT.value(e["item_id"], e["field"])
    audit("use", {"id": e["item_id"], "name": e["item"]}, e["field"], tool="walter-llm")
    with _keys_lock:
        _keys[env_name] = (time.time(), value)
    return value


# ───────────────────────── test budget ─────────────────────────
def _ledger() -> Path:
    return _instance_path(TEST_BUDGET["ledger"])


def _ledger_add(entry: dict) -> None:
    import fcntl
    path = _ledger()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps({"ts": time.time(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            **entry}, ensure_ascii=False) + "\n")


def test_budget() -> dict:
    """Paid spend of test runs over the window against the cap (+ the owner's approvals in the same window), USD."""
    since = time.time() - float(TEST_BUDGET["window_hours"]) * 3600
    spent = approved = 0.0
    notified = False
    try:
        lines = _ledger().read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if float(e.get("ts") or 0) < since:
            continue
        if e.get("kind") == "approval":
            approved += float(e.get("usd") or 0)
        elif e.get("kind") == "notice":
            notified = True
        else:
            spent += float(e.get("usd") or 0)
    rate = float(TEST_BUDGET["usd_per_eur"])
    limit = float(TEST_BUDGET["paid_limit_eur"]) * rate + approved
    return {"spent_usd": round(spent, 4), "limit_usd": round(limit, 4), "approved_usd": round(approved, 4),
            "spent_eur": round(spent / rate, 2), "limit_eur": round(limit / rate, 2),
            "window_hours": TEST_BUDGET["window_hours"], "notified": notified}


def _price_usd(route: dict, usage: dict | None, body: dict) -> float:
    """Cost of one call from its usage (or, before the call, from the request size) at the route's price."""
    host = route.get("host") or {}
    p_in, p_out, blended = host.get("price_in_1m"), host.get("price_out_1m"), route.get("blended_1m")
    if usage:
        t_in, t_out = float(usage.get("in") or 0), float(usage.get("out") or 0)
    else:   # ~4 characters per token; the answer is unknown before the call
        t_in, t_out = len(json.dumps(body.get("messages") or [], default=str)) / 4, 0.0
    if p_in is not None:
        return (t_in * float(p_in) + t_out * float(p_out if p_out is not None else p_in)) / 1e6
    return (t_in + t_out) * float(blended or 0) / 1e6


def _priced(route: dict, telemetry: dict, body: dict) -> dict:
    """A paid call the provider reports no cost for (Venice, Kie…) gets its cost at the router's price for this
    route, marked `estimated_price`; without a known price it stays unknown (never zero)."""
    host = route.get("host") or {}
    if (telemetry.get("cost_usd") is None and route.get("provider") in PAID and telemetry.get("usage")
            and (host.get("price_in_1m") is not None or route.get("blended_1m"))):
        telemetry.update(cost_usd=round(_price_usd(route, telemetry["usage"], body), 6), cost_status="estimated_price")
    return telemetry


def test_gate(route: dict, body: dict) -> str | None:
    """None when this paid call of a test fits the budget, else the refusal (and one Telegram notice per window)."""
    b = test_budget()
    if b["spent_usd"] + _price_usd(route, None, body) <= b["limit_usd"]:
        return None
    if not b["notified"]:
        _ledger_add({"kind": "notice"})
        text = (f"⚠️ Essais W.Alter : budget payant atteint ({b['spent_eur']:.2f} € sur {b['limit_eur']:.2f} € en "
                f"{b['window_hours']} h). Les routes payantes sont refusées aux essais tant que tu n'as pas validé "
                f"un montant de plus.")
        threading.Thread(target=_telegram, args=(text,), daemon=True).start()
    return (f"test_budget: paid spend of tests {b['spent_eur']:.2f} EUR / {b['limit_eur']:.2f} EUR over "
            f"{b['window_hours']} h; the owner must approve more (walter-llm test-budget approve EUR)")


def _charge(route: dict, entry: dict, telemetry: dict, body: dict) -> None:
    """Record the paid spend of a test call (provider cost, else estimated from its usage or size)."""
    if entry.get("channel") != "test" or route["provider"] not in PAID:
        return
    cost = telemetry.get("cost_usd")
    usd = float(cost) if cost is not None else _price_usd(route, telemetry.get("usage"), body)
    try:
        _ledger_add({"kind": "spend", "usd": round(usd, 6), "estimated": telemetry.get("cost_status") != "reported",
                     "provider": route["provider"],
                     "model": route["model"], "run_id": entry.get("run_id"), "agent": entry.get("agent")})
    except OSError:
        pass


def _telegram(text: str) -> None:
    """One message to the owner through Hermes' gateway (best effort)."""
    try:
        hermes = Path(_walter("instance", "harness", "hermes")) / "hermes-agent" / "venv" / "bin" / "hermes"
        subprocess.run([str(hermes), "send", "-t", "telegram", text], capture_output=True, timeout=120)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        pass


def approve_tests(eur: float, note: str = "") -> dict:
    """The owner's approval of EUR more paid spend for tests, valid for the window."""
    _ledger_add({"kind": "approval", "eur": eur, "usd": round(eur * float(TEST_BUDGET["usd_per_eur"]), 4),
                 "note": note})
    return test_budget()


# ───────────────────────── routes (Walter Router) ─────────────────────────
_routes: dict[str, tuple[float, dict]] = {}


def _router(*args: str) -> dict | list:
    r = subprocess.run([ROUTER, *args], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(f"walter-router {' '.join(args)}: {(r.stderr or r.stdout)[-300:]}")
    return json.loads(r.stdout)


_refreshing: set[str] = set()


def _refresh(task: str) -> dict:
    """task = a router task, or task/LEVEL for one of the instance's text tiers ("general/L2")."""
    try:
        name, _, level = task.partition("/")
        d = _router("pick", name, *(["--level", level] if level else []))
        _routes[task] = (time.time(), d)
        return d
    finally:
        _refreshing.discard(task)


def decision(task: str) -> dict:
    """The router's routes for a task. A stale entry is served at once and refreshed in the background (a phone call
    must not wait ~5 s for `walter-router pick`); only a task never seen blocks."""
    hit = _routes.get(task)
    if hit and time.time() - hit[0] < ROUTE_TTL:
        return hit[1]
    if hit:
        if task not in _refreshing:
            _refreshing.add(task)
            threading.Thread(target=_refresh, args=(task,), daemon=True).start()
        return hit[1]
    _refreshing.add(task)
    return _refresh(task)


def warm() -> None:
    """Fill the route cache at start-up for every chat task (background)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(t: str) -> None:
        try:
            decision(t)
        except Exception:   # noqa: BLE001 — a task without route answers 400 when asked
            pass
    with ThreadPoolExecutor(4) as pool:   # the phone's poste first
        list(pool.map(one, sorted(chat_tasks(), key=lambda t: t != "voice_assist")))
    for name in ("OPENROUTER_API_KEY", "KIE_API_KEY"):   # Bitwarden reads, before the first call needs them
        try:
            provider_key(name)
        except Exception:   # noqa: BLE001
            pass
    try:   # LiteLLM's first call pays its lazy imports: pay them now
        import litellm
        litellm.get_llm_provider("openrouter/google/gemini-3.8-flash")
    except Exception:   # noqa: BLE001
        pass


def chat_tasks() -> list[str]:
    hit = _routes.get("__tasks__")
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    rows = [t for t in _router("tasks") if t.get("interface") == "chat"]
    tasks = [t["task"] for t in rows]
    _routes["__tasks__"] = (time.time(), tasks)
    _routes["__owner_tasks__"] = (time.time(), [t["task"] for t in rows if not t.get("internal")])
    return tasks


def owner_tasks() -> list[str]:
    """Chat tasks an owner message can ask for: the internal postes (memory extraction, compression, voice…) are
    for the modules that call them by name, never a plan's choice."""
    chat_tasks()
    return _routes["__owner_tasks__"][1]


# Anthropic caches only up to explicit markers. Without them every DSH step re-read its whole prompt (2026-11-07:
# 0 cache reads over the last 200 Claude subscription calls, 2.9 M input tokens). Marker 1 = tools + system (stable
# for a session), marker 2 = the last message (the conversation so far, re-read by the next step and the next turn).
ANTHROPIC_CACHE_POINTS = [{"location": "message", "role": "system"}, {"location": "message", "index": -1}]


def litellm_target(route: dict) -> dict | None:
    """LiteLLM arguments for one router route, or None when this gateway cannot run it (yet)."""
    p, m = route["provider"], route["model"]
    if p == "claude-pro":
        config = _CONF.get("claude_subscription") or {}
        return ({"model": m, "cache_control_injection_points": ANTHROPIC_CACHE_POINTS}
                if config.get("enabled") and m in config.get("verified_models", []) else None)
    if p == "antigravity":                                    # Google AI Pro: the official Antigravity CLI, text only
        from antigravity_subscription import base_id
        config = _CONF.get("antigravity_subscription") or {}
        verified = config.get("verified_models", [])
        return {"model": m} if config.get("enabled") and m in {*verified, *map(base_id, verified)} else None
    if p == "kie" and m.startswith(KIE_GPT):                 # Kie /codex = OpenAI Responses protocol
        key = provider_key("KIE_API_KEY")
        return {"model": f"openai/responses/{m}", "api_base": "https://api.kie.ai/codex/v1", "api_key": key,
                "extra_headers": {"User-Agent": UA}}
    if p == "kie":                                            # Kie /claude = Anthropic Messages protocol
        key = provider_key("KIE_API_KEY")
        return {"model": f"anthropic/{m}", "api_base": "https://api.kie.ai/claude", "api_key": key,
                "extra_headers": {"User-Agent": UA, "Authorization": f"Bearer {key}"},
                "cache_control_injection_points": ANTHROPIC_CACHE_POINTS}
    if p == "openrouter":
        target = {"model": f"openrouter/{m}", "api_key": provider_key("OPENROUTER_API_KEY")}
        if route.get("or_provider"):   # the router's host order: cheapest usable host first, the others as fallbacks
            target["extra_body"] = {"provider": route["or_provider"]}
        return target
    if p == "arnict":
        return {"model": f"openai/{m}", "api_base": "https://api.arnict.com/v1", "api_key": provider_key("ARNICT_API_KEY")}
    if p == "venice":                                         # Venice: OpenAI-compatible chat completions, own key
        return {"model": f"openai/{m}", "api_base": "https://api.venice.ai/api/v1", "api_key": provider_key("VENICE_API_KEY")}
    if p == "codex":                                          # ChatGPT subscription (Codex models), own login
        if not chatgpt_ready():
            return None
        return {"model": f"chatgpt/{m}"}
    return None


async def provider_completion(route: dict, **kwargs):
    """One provider transport; Claude's native client contributes no agent context or tools."""
    if route["provider"] == "antigravity":
        from antigravity_subscription import completion as antigravity
        config = dict(_CONF["antigravity_subscription"])
        for key in ("cli", "home"):
            config[key] = str(_instance_path(config[key]))
        return await antigravity(config, **kwargs)
    if route["provider"] != "claude-pro":
        import litellm
        return await litellm.acompletion(**kwargs)
    import asyncio
    from walter_secrets import grants
    from claude_subscription import completion
    config = dict(_CONF["claude_subscription"])
    for key in ("cli", "state_dir", "usage_log"):
        if config.get(key):
            config[key] = str(_instance_path(config[key]))
    # The Router names the account when the provider has several (route.account = subscription id); which secret
    # serves it is this gateway's own setting (`accounts`), never a grant named by a caller.
    accounts = claude_accounts(config)
    account = route.get("account") or next(iter(accounts))
    if account not in accounts:
        raise ValueError("unknown_claude_account")
    config["account"] = account
    token = await asyncio.to_thread(grants.access, accounts[account])
    return await completion(config, token, **kwargs)


def claude_accounts(config: dict) -> dict[str, str]:
    """subscription id -> Walter Secrets grant, first = the default account (before accounts: one grant)."""
    return dict(config.get("accounts") or {"anthropic-pro": config.get("grant", "claude-subscription")})


def _rate_limited(exc: BaseException) -> bool:
    return type(exc).__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429


async def start_completion(route: dict, kwargs: dict, stream: bool, waits: tuple | None = None):
    """(response, iterator, first chunk): the call, up to its first token when streaming. A subscription's rate-limit
    refusal is waited out (RATE_LIMIT_WAITS) before the caller falls back to a paid route; not when another account
    of the same subscription comes next (waits=())."""
    import asyncio
    for wait in (*(RATE_LIMIT_WAITS if waits is None else waits), None):
        try:
            resp = await provider_completion(route, **kwargs)
            if not stream:
                return resp, None, None
            it = resp.__aiter__()
            return resp, it, await it.__anext__()
        except Exception as exc:
            if wait is None or route.get("access") != "subscription" or not _rate_limited(exc):
                raise
            await asyncio.sleep(wait)


def codex_access_token() -> str:
    """W.Alter's Codex access token, from its grant (renewed through the Codex CLI by walter-secrets)."""
    from walter_secrets import grants
    return grants.access(CODEX_GRANT)


def _codex_account_id() -> str:
    from walter_secrets import grants
    return grants.attribute(CODEX_GRANT, "account_id")


def _install_codex_auth() -> None:
    """LiteLLM's chatgpt provider reads W.Alter's Codex CLI session (read-only) instead of its own device login."""
    from litellm.llms.chatgpt.authenticator import Authenticator
    Authenticator.get_access_token = lambda self: codex_access_token()
    Authenticator.get_account_id = lambda self: _codex_account_id()


def chatgpt_ready() -> bool:
    try:
        from walter_secrets import grants
        return grants.check(CODEX_GRANT)["ok"]
    except Exception:  # noqa: BLE001 — readiness probe: any failure means not ready
        return False


def json_instruction(fmt: dict) -> str:
    schema = (fmt.get("json_schema") or {}).get("schema")
    return ("Réponds uniquement par un objet JSON valide, sans texte autour ni bloc de code."
            + (f" Il doit respecter exactement ce schéma JSON : {json.dumps(schema, ensure_ascii=False)}" if schema else ""))


def as_json(text: str | None) -> str:
    """The JSON object of a Codex answer; ValueError (= next route, which honours response_format) when there is none."""
    t = (text or "").strip()
    t = t[t.find("{"):t.rfind("}") + 1] if "{" in t else t
    json.loads(t)
    return t


async def exact_call(spec: dict) -> dict:
    """Local router transport: one provider, one model, no retries or model fallbacks.

    Keys remain in the gateway. The caller owns provider order, conversation and notices.
    This CLI operation opens no unauthenticated HTTP endpoint.
    """
    import litellm
    import re

    route = spec.get("route") or {}
    provider, model = route.get("provider"), route.get("model")
    if provider not in {"kie", "openrouter", "codex", "arnict", "venice", "claude-pro", "antigravity"} or not isinstance(model, str) or not model.strip():
        return {"ok": False, "error": "invalid_route"}
    try:
        test = os.environ.get("WALTER_RUN_CHANNEL") == "test"
        if test and provider in PAID:
            refused = test_gate(route, spec)
            if refused:
                return {"ok": False, "error": "test_budget", "detail": refused}
        if provider == "codex":
            _install_codex_auth()
        target = litellm_target(route)
        if target is None:
            return {"ok": False, "error": "provider_unavailable"}
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        kwargs = {**target, "messages": spec["messages"], "stream": False, "num_retries": 0,
                  "fallbacks": [], "timeout": max(0.1, float(spec.get("timeout") or 60))}
        if spec.get("tools"):
            kwargs["tools"] = spec["tools"]
        if route.get("reasoning") and route["reasoning"] not in {"none", "non-reasoning"}:
            kwargs["reasoning_effort"] = route["reasoning"]
        response = await provider_completion(route, **kwargs)
        if test:
            _charge(route, {"channel": "test", "agent": "walter-router"}, _telemetry(response), spec)
        message = response.choices[0].message.model_dump(exclude_none=True)
        returned_model = response.model
        # Provider prefixes and punctuation differ; a different model is never accepted as success.
        def identity(value):
            return re.sub(r"[^a-z0-9]", "", value.rsplit("/", 1)[-1].lower())
        if not returned_model or identity(returned_model) != identity(model):
            return {"ok": False, "error": "provider_model_mismatch"}
        if response.choices[0].finish_reason not in {"stop", "tool_calls", "function_call", "end_turn"}:
            return {"ok": False, "error": "provider_incomplete_response"}
        if not message.get("content") and not message.get("tool_calls"):
            return {"ok": False, "error": "empty_provider_response"}
        return {"ok": True, "message": message, "provider": provider, "model": model,
                "response_model": returned_model, "response_id": response.id, **_telemetry(response)}
    except Exception as exc:
        # Provider exception text can contain credentials, payloads and URLs: return only its type.
        status = getattr(exc, "status_code", None)
        return {"ok": False, "error": type(exc).__name__,
                **({"status_code": status} if isinstance(status, int) else {})}


# ───────────────────────── logging ─────────────────────────
def _usage(resp) -> dict | None:
    u = getattr(resp, "usage", None)
    if not u:
        return None
    def get(obj, key):
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    return {"in": get(u, "prompt_tokens"), "out": get(u, "completion_tokens"),
            "cached": get(get(u, "prompt_tokens_details"), "cached_tokens")}


def _number(value) -> float | None:
    """A finite nonnegative measurement, or unknown when missing or malformed."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _telemetry(resp) -> dict:
    """Vendor-reported cost and transport estimate stay distinguishable; absence is never zero."""
    usage = getattr(resp, "usage", None)
    cost = _number(usage.get("cost") if isinstance(usage, dict) else getattr(usage, "cost", None))
    status = "reported" if cost is not None else "unknown"
    if cost is None:
        hidden = getattr(resp, "_hidden_params", None) or {}
        cost = _number(hidden.get("response_cost")) if isinstance(hidden, dict) else None
        # LiteLLM may synthesize zero when pricing/usage is unavailable. Only an explicit
        # provider usage.cost is evidence for zero; a hidden zero has no such provenance.
        if cost is not None and cost > 0:
            status = "estimated"
        else:
            cost = None
    return {"usage": _usage(resp), "cost_usd": cost, "cost_status": status}


def _uuid(value) -> str | None:
    """Validate a local correlation identifier without echoing its supplied value."""
    if value is None or value == "":
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("invalid correlation identifier") from None


def _dsh_session(value) -> str | None:
    """Accept DSH's native session-UUID and bare UUID forms, preserving exact local identity."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid session identifier")
    _uuid(value.removeprefix("session-"))
    if not value:
        raise ValueError("invalid session identifier")
    return value


def _session_run(session: str) -> dict:
    """The public metadata-only lookup; no database import or global most-recent-run guess."""
    try:
        p = subprocess.run(["walter-memory", "runs", "find", "--session", session, "--open-only"],
                           capture_output=True, text=True, timeout=10)
        row = json.loads(p.stdout) if p.returncode == 0 else {}
        return row if isinstance(row, dict) else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}


def _run_metadata(run_id: str) -> dict:
    """Validate explicit request correlation through Memory's metadata-only public CLI."""
    try:
        p = subprocess.run(["walter-memory", "runs", "find", run_id, "--open-only"],
                           capture_output=True, text=True, timeout=10)
        row = json.loads(p.stdout) if p.returncode == 0 else {}
        return row if isinstance(row, dict) else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}


async def _correlation(request, body: dict, agent: str) -> dict:
    """Request-local transport metadata. DSH's public pi-ai cache key carries its native session identity only
    to this local gateway; it is consumed here and never forwarded to a provider as an internal identifier."""
    import asyncio
    from fastapi import HTTPException
    def checked(row, expected=None):
        if not isinstance(row, dict) or row.get("status") != "open" or not row.get("run_id"):
            raise HTTPException(409, "identified run context unavailable or not open")
        resolved = _uuid(row["run_id"])
        if expected and resolved != expected:
            raise HTTPException(409, "identified run context mismatch")
        # This gateway has no pseudonymization stage. Private and unclassified identified
        # contexts cannot use a cloud route. Untracked legacy calls are a separate scope.
        if row.get("privacy_class") != "cloud_allowed":
            raise HTTPException(403, "identified context is not authorized for raw cloud transport")
        return resolved
    try:
        out = {"run_id": _uuid(request.headers.get("X-Walter-Run-Id")),
               "task_id": _uuid(request.headers.get("X-Walter-Task-Id"))}
        if out["run_id"]:
            row = await asyncio.to_thread(_run_metadata, out["run_id"])
            out["run_id"] = checked(row, out["run_id"])
            out["correlation_status"] = "resolved"
            out["channel"] = row.get("channel")
            out["requested"] = row.get("requested")
        if agent == "dsh":
            session_id = _dsh_session(body.pop("prompt_cache_key", None))
            body.pop("prompt_cache_retention", None)
            if session_id:
                session = "dsh/vm/" + session_id
                row = await asyncio.to_thread(_session_run, session)
                found = checked(row)
                if out["run_id"] and out["run_id"] != found:
                    raise HTTPException(400, "conflicting correlation identifiers")
                out.update(run_id=found, session_id=session, correlation_status="resolved", channel=row.get("channel"),
                           requested=row.get("requested"))
        if out["task_id"] and not out["run_id"]:
            raise HTTPException(409, "task correlation requires a resolved run")
        return {k: v for k, v in out.items() if v is not None}
    except ValueError:
        raise HTTPException(400, "invalid correlation identifier") from None


def planned_task(asked: str, requested: dict | None) -> tuple[str, str | None]:
    """(Router task for this call, what the plan set). Lot 2 (2026-11-07): `auto` takes the task and tier the
    preflight asked for this owner message (written on the run); an explicitly chosen task keeps its task and gets
    the plan's tier only. Without a plan nothing changes (auto = DEFAULT_TASK). One plan per owner message, so every
    model call of the turn gets the same answer (and the same model)."""
    task = DEFAULT_TASK if asked in ("auto", "walter") and not requested else asked
    if not requested:
        return task, None
    known = set(owner_tasks())
    level = requested.get("level") if requested.get("level") in ("L1", "L2", "L3") else None
    if asked in ("auto", "walter"):
        task = requested.get("task") if requested.get("task") in known else DEFAULT_TASK
    if level and "/" not in task:
        return f"{task}/{level}", f"{'task+' if asked in ('auto', 'walter') else ''}level"
    return task, "task" if asked in ("auto", "walter") else None


def _text_parts(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    return [p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text"]


def rule_answer(requested: dict | None, body: dict) -> str | None:
    """The preflight's rule answer, only when this request ends on the very owner message it answers (its hash):
    never for a tool step, a title request or another message of the session. The owner message is looked for in
    the trailing block of user rows (no assistant or tool row after it): DSH sends it followed by its own user rows
    (workspace instructions, runtime snapshot), and the hook's context before it."""
    if not requested or not requested.get("answer") or not requested.get("message_sha"):
        return None
    tail = []
    for message in reversed(body.get("messages") or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            break
        tail.append(message)
    for message in tail:
        parts = _text_parts(message.get("content"))
        candidates = [*parts, "".join(parts), *(line for p in parts for line in p.split("\n\n"))]
        if any(hashlib.sha256(c.strip().encode()).hexdigest() == requested["message_sha"] for c in candidates if c.strip()):
            return str(requested["answer"])
    return None


def _rule_completion(text: str) -> dict:
    return {"id": f"walter-rule-{uuid.uuid4().hex[:12]}", "object": "chat.completion", "created": int(time.time()),
            "model": "walter-context-rule", "choices": [{"index": 0, "finish_reason": "stop",
                                                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


async def _rule_stream(text: str):
    head = {"id": f"walter-rule-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()),
            "model": "walter-context-rule"}
    yield "data: " + json.dumps({**head, "choices": [{"index": 0, "delta": {"role": "assistant", "content": text},
                                                      "finish_reason": None}]}) + "\n\n"
    yield "data: " + json.dumps({**head, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}) + "\n\n"
    yield "data: [DONE]\n\n"


def _rule_routing(run_id: str) -> None:
    try:
        subprocess.run(["walter-memory", "runs", "routing", run_id], input=json.dumps(
            {"applied": True, "via": "walter-context rule answer (no model)", "provider": "none"}),
            text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass


def _record_attempt(row: dict, entry: dict) -> None:
    """Persist through public ports. DSH routing becomes applied only after an observed response."""
    try:
        subprocess.run([ROUTER, "log-exec", json.dumps(row)], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass
    if (entry.get("agent") == "dsh" and entry.get("correlation_status") == "resolved"
            and entry.get("run_id") and entry.get("observed_model")):
        routing = {"applied": True, "via": "walter-llm observed response",
                   **{key: entry.get(key) for key in ("model_id", "model", "provider", "observed_model")}}
        try:
            subprocess.run(["walter-memory", "runs", "routing", entry["run_id"]],
                           input=json.dumps(routing), text=True, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass  # Routing is an observation, never a reason to repeat the provider call.


def log(entry: dict) -> None:
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    try:
        with LOG.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if entry.get("provider"):                                 # teach the router (background, best effort)
        row = {"task": entry.get("task"), "model_id": entry.get("model_id"), "provider": entry["provider"],
               "model": entry.get("model"), "ok": entry.get("ok"), "seconds": entry.get("seconds"), "kind": "text",
               "role": f"agent:{entry.get('agent')}",
               **{k: entry.get(k) for k in ("run_id", "task_id", "usage", "cost_usd", "cost_status", "skipped", "account")}}
        threading.Thread(target=_record_attempt, args=(row, entry), daemon=True).start()


# ───────────────────────── HTTP ─────────────────────────
def build_app():
    import asyncio
    import litellm
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import JSONResponse, StreamingResponse

    _install_codex_auth()
    litellm.drop_params = True
    litellm.suppress_debug_info = True
    app = FastAPI(title="walter-llm")
    threading.Thread(target=warm, daemon=True).start()

    def agent_of(authorization: str) -> str:
        tok = authorization.removeprefix("Bearer ").strip()
        agents = json.loads(AGENTS.read_text()) if AGENTS.exists() else {}
        a = agents.get(hashlib.sha256(tok.encode()).hexdigest()) if tok else None
        if not a:
            raise HTTPException(401, "unknown agent token")
        return a["agent"]

    @app.get("/v1/models")
    def models(authorization: str = Header(default="")):
        agent_of(authorization)
        return {"object": "list", "data": [{"id": t, "object": "model", "owned_by": "walter-router"}
                                           for t in ["auto", *chat_tasks()]]}

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/v1/chat/completions")
    async def completions(request: Request, authorization: str = Header(default="")):
        agent = agent_of(authorization)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "request must be a JSON object")
        correlation = await _correlation(request, body, agent)
        requested = correlation.pop("requested", None)
        asked = (body.pop("model", None) or DEFAULT_TASK).removeprefix("walter/")
        task, plan = planned_task(asked, requested if isinstance(requested, dict) else None)
        if plan:
            correlation["plan"] = plan
        stream = bool(body.pop("stream", False))
        ruled = rule_answer(requested if isinstance(requested, dict) else None, body)
        if ruled is not None:   # the preflight settled this message by a rule: no model call (lot 2)
            log({"agent": agent, "task": task, "ok": True, "seconds": 0, "rule": requested.get("fast_path"), **correlation})
            if agent == "dsh" and correlation.get("run_id"):
                threading.Thread(target=_rule_routing, args=(correlation["run_id"],), daemon=True).start()
            if stream:
                return StreamingResponse(_rule_stream(ruled), media_type="text/event-stream",
                                         headers={"X-Walter-Route": "walter-context/rule"})
            return JSONResponse(_rule_completion(ruled), headers={"X-Walter-Route": "walter-context/rule"})
        try:
            d = decision(task)
        except Exception:
            raise HTTPException(400, "no route for requested task") from None
        errors = []
        plan = d.get("execution") or []
        for index, route in enumerate(plan):
            t0 = time.perf_counter()
            following = plan[index + 1] if index + 1 < len(plan) else {}
            other_account = bool(route.get("account") and following.get("provider") == route["provider"]
                                 and following.get("account") not in (None, route["account"]))
            base = {"agent": agent, "task": task, "model_id": d.get("model_id"), "provider": route["provider"],
                    "model": route["model"], **({"account": route["account"]} if route.get("account") else {}),
                    **correlation}
            if correlation.get("channel") == "test" and route["provider"] in PAID:
                refused = test_gate(route, body)
                if refused:
                    errors.append(f"{route['provider']}/{route['model']}: {refused}")
                    log({**base, "ok": False, "seconds": 0, "skipped": "test_budget"})
                    continue
            try:
                target = litellm_target(route)
            except Exception as e:                            # key missing in Bitwarden, vault locked…
                errors.append(f"{route['provider']}/{route['model']}: {type(e).__name__}")
                continue
            if target is None:
                continue
            # Kie's endpoints answer a quick Cloudflare 502 on about half the calls (2026-10-16): one retry there
            # costs ~3 s and spares an OpenRouter fallback (paid, low credit)
            kwargs = {**body, **target, "stream": stream, "num_retries": 2 if route["provider"] == "kie" else 0}
            if route.get("reasoning") and route["reasoning"] not in ("none", "non-reasoning"):
                kwargs.setdefault("reasoning_effort", route["reasoning"])
            want_json = route["provider"] == "codex" and (body.get("response_format") or {}).get("type") in (
                "json_object", "json_schema")
            if want_json:   # the Codex backend ignores response_format: ask in words, check the answer below
                kwargs["messages"] = [{"role": "system", "content": json_instruction(body["response_format"])},
                                      *body.get("messages", [])]
            try:
                resp, it, first = await start_completion(route, kwargs, stream,   # fail over until the first token
                                                         () if other_account else None)
                if want_json and not stream:
                    resp.choices[0].message.content = as_json(resp.choices[0].message.content)
                if not stream:
                    telemetry = _priced(route, _telemetry(resp), body)
                    log({**base, "ok": True, "seconds": round(time.perf_counter() - t0, 2),
                         "observed_model": getattr(resp, "model", None),
                         **telemetry, **({"host": getattr(resp, "provider", None) or
                                            (resp.model_dump().get("provider"))} if route["provider"] == "openrouter" else {})})
                    _charge(route, base, telemetry, body)
                    return JSONResponse(resp.model_dump(), headers={"X-Walter-Route": f"{route['provider']}/{route['model']}"})
            except asyncio.CancelledError:
                log({**base, "ok": False, "seconds": round(time.perf_counter() - t0, 2),
                     "stream": stream, "error": "CancelledError"})
                raise
            except Exception as e:
                errors.append(f"{route['provider']}/{route['model']}: {type(e).__name__}")
                log({**base, "ok": False, "seconds": round(time.perf_counter() - t0, 2), "error": type(e).__name__,
                     "params": sorted(k for k in body if k != "messages"),
                     **({"skipped": "rate_limit"} if route.get("access") == "subscription" and _rate_limited(e) else {})})
                continue

            async def sse(first=first, it=it, base=base, t0=t0, route=route):
                ok, failure = False, None
                telemetry = _telemetry(first)
                observed_model = getattr(first, "model", None)
                try:
                    yield f"data: {first.model_dump_json()}\n\n"
                    async for chunk in it:
                        update = _telemetry(chunk)
                        observed_model = getattr(chunk, "model", None) or observed_model
                        if update["usage"] is not None:
                            telemetry["usage"] = update["usage"]
                        if update["cost_usd"] is not None:
                            telemetry.update(cost_usd=update["cost_usd"], cost_status=update["cost_status"])
                        yield f"data: {chunk.model_dump_json()}\n\n"
                    ok = True  # Only the provider iterator's normal exhaustion establishes success.
                    yield "data: [DONE]\n\n"
                except (asyncio.CancelledError, GeneratorExit) as exc:
                    failure = type(exc).__name__
                    raise
                except Exception as exc:                      # no fallback after a chunk was delivered
                    failure = type(exc).__name__
                    yield f"data: {json.dumps({'error': {'message': failure}})}\n\n"
                finally:
                    try:
                        close = getattr(it, "aclose", None)
                        if close:
                            await asyncio.wait_for(close(), timeout=5)
                    except BaseException as exc:               # cleanup must never suppress the attempt trace
                        ok, failure = False, type(exc).__name__
                        raise
                    finally:
                        _priced(route, telemetry, body)
                        log({**base, "ok": ok, "seconds": round(time.perf_counter() - t0, 2), "stream": True,
                             "observed_model": observed_model, **telemetry, **({"error": failure} if failure else {})})
                        _charge(route, base, telemetry, body)

            return StreamingResponse(sse(), media_type="text/event-stream",
                                     headers={"X-Walter-Route": f"{route['provider']}/{route['model']}"})
        log({"agent": agent, "task": task, "ok": False, "error": "all routes failed", **correlation})
        raise HTTPException(502, {"message": "every route failed", "attempts": errors})

    return app


def add_agent(name: str, cred_file: str, ref: str = "WALTER_LLM_TOKEN") -> None:
    """New token for NAME (one per agent: rotates). cred_file = a DSH credentials YAML, or `env:FILE[:VAR]` = a
    0600 KEY=VALUE file (systemd EnvironmentFile / .env) where only VAR's line is (re)written."""
    token = "wllm_" + secrets.token_urlsafe(32)
    agents = json.loads(AGENTS.read_text()) if AGENTS.exists() else {}
    agents = {h: a for h, a in agents.items() if a["agent"] != name}          # rotate: one token per agent
    agents[hashlib.sha256(token.encode()).hexdigest()] = {"agent": name, "created": datetime.now(timezone.utc).isoformat()}
    AGENTS.write_text(json.dumps(agents, indent=1))
    os.chmod(AGENTS, 0o600)
    if cred_file.startswith("env:"):
        path, _, var = cred_file[4:].partition(":")
        var = var or ref
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [ln for ln in (p.read_text().splitlines() if p.exists() else []) if not ln.startswith(f"{var}=")]
        p.touch(mode=0o600)
        os.chmod(p, 0o600)
        p.write_text("\n".join([*lines, f"{var}={token}"]) + "\n")
        print(f"agent {name}: token written to {p} ({var})")
        return
    p = Path(cred_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Rewrite only refs.<ref>: the same file holds DSH's own records (e.g. the web UI's browser-session secret,
    # whose loss would sign every browser out).
    lines = p.read_text().splitlines() if p.exists() else []
    if "refs:" in lines:
        lines = [ln for ln in lines if not ln.startswith(f"  {ref}:")]
        lines.insert(lines.index("refs:") + 1, f"  {ref}: {token}")
    else:
        lines = ["version: 1", "", "refs:", f"  {ref}: {token}", *[ln for ln in lines if not ln.startswith("version:")]]
    p.touch(mode=0o600)
    os.chmod(p, 0o600)
    p.write_text("\n".join(lines) + "\n")
    print(f"agent {name}: token written to {p} (ref {ref})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "call":
        import asyncio
        from contextlib import redirect_stdout
        with redirect_stdout(sys.stderr):
            try:
                answer = asyncio.run(exact_call(json.load(sys.stdin)))
            except Exception as exc:
                answer = {"ok": False, "error": type(exc).__name__}
        print(json.dumps(answer))
        sys.exit(0 if answer.get("ok") else 1)
    elif cmd == "add-agent":
        add_agent(sys.argv[2], sys.argv[3])
    elif cmd == "test-budget":   # status | approve EUR [note…] (only at the owner's explicit request)
        if len(sys.argv) > 3 and sys.argv[2] == "approve":
            print(json.dumps(approve_tests(float(sys.argv[3]), " ".join(sys.argv[4:])), indent=1))
        else:
            print(json.dumps(test_budget(), indent=1))
    elif cmd == "serve":
        import uvicorn
        uvicorn.run(build_app(), host="127.0.0.1", port=int(os.environ.get("WALTER_LLM_PORT", "8894")), log_level="warning")
    else:
        print("Usage: walter-llm serve | call | add-agent NAME FILE | test-budget [approve EUR [note]]", file=sys.stderr)
        sys.exit(2)
