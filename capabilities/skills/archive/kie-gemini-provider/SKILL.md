---
name: kie-gemini-provider
description: Kie.ai Gemini models provider setup for Hermes — endpoints, naming quirks, config, validation fix, capabilities, pitfalls.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [kie, gemini, provider, hermes, api, llm]
---

# Kie.ai Gemini Provider Setup

Configure Gemini 3.1 Pro and 3.5 Flash as Hermes providers via Kie.ai.

## Key Discovery (2026-06-02)

Each Gemini model on Kie.ai has its **OWN endpoint** with the model name in the URL path. There is NO shared Gemini endpoint. The generic `/openai/v1/chat/completions` does NOT support Gemini models.

**Pattern:** `POST https://api.kie.ai/{model-url-name}/v1/chat/completions`

## Naming Quirks

| Model | URL path (in URL) | `model` field (in body) | Notes |
|-------|-------------------|------------------------|-------|
| Gemini 3.5 Flash | `gemini-3-5-flash-openai` | `gemini-3-5-flash` | `-openai` suffix required in URL |
| Gemini 3.1 Pro | `gemini-3.1-pro` | `gemini-3.1-pro` | **DOTS** — `3-1-pro` returns 422 |
| Gemini 3 Flash | `gemini-3-flash` | `gemini-3-flash` | Hyphens |
| Gemini 2.5 Flash | `gemini-2.5-flash` | `gemini-2.5-flash` | Dots |

**Pitfall:** `gemini-3-1-pro` (hyphens) → 422 "page does not exist". Must use `gemini-3.1-pro` (dots).

## Hermes config.yaml

```yaml
providers:
  kie-gemini-pro:
    api: https://api.kie.ai/gemini-3.1-pro/v1
    api_mode: chat_completions
    default_model: gemini-3.1-pro
    key_env: KIE_API_KEY
    models: [gemini-3.1-pro]
    name: Kie.ai Gemini 3.1 Pro
  kie-gemini-flash:
    api: https://api.kie.ai/gemini-3-5-flash-openai/v1
    api_mode: chat_completions
    default_model: gemini-3-5-flash
    key_env: KIE_API_KEY
    models: [gemini-3-5-flash]
    name: Kie.ai Gemini 3.5 Flash
```

**Pitfall:** The `api` URL MUST end with `/v1`. The OpenAI Python client appends `/chat/completions` to the base_url. Without `/v1`, the final URL is `.../chat/completions` instead of `.../v1/chat/completions` → 404.

## Verified Capabilities (2026-06-02)

| Feature | 3.1 Pro | 3.5 Flash |
|---------|---------|-----------|
| Text chat | OK (0.01cr) | OK (0.01cr) |
| Image input (base64) | OK (0.11cr) | OK (0.11cr) |
| Multi-turn | OK | OK |
| Streaming (SSE) | OK | OK |
| Tools/functions | OK | OK |
| Prompt caching | **NO** | **NO** |
| Thinking/reasoning | OK (0.02cr) | OK (0.02cr) |

## Pitfalls

### `/model` validation warning — fix

Hermes `/model` validates via `GET {base_url}/v1/models`. Kie.ai returns 404.

**Root cause:** `resolve_runtime_provider` returns `provider="custom"` for named custom providers. The validation's config-models check uses `normalized` ("custom") instead of the original provider name, so it never finds the match in config.

**Fix in `hermes_cli/models.py` (line ~3668):** Before the `/v1/models` probe, iterate config providers and match by `base_url`:

```python
providers_cfg = cfg.get("providers") or {}
for _pname, _pcfg in providers_cfg.items():
    if not isinstance(_pcfg, dict):
        continue
    _pcfg_url = str(_pcfg.get("api") or _pcfg.get("base_url") or "").rstrip("/")
    if _pcfg_url and base_url and _pcfg_url == base_url.rstrip("/"):
        _models = _pcfg.get("models") or []
        if isinstance(_models, list) and requested_for_lookup in _models:
            return {"accepted": True, "persist": True, "recognized": True, "message": None}
```

**Pitfall:** Import is `from hermes_cli.config import load_config`, NOT `load_cli_config`. Wrong name silently fails in `try/except` — the patch appears to do nothing.

**Pitfall:** Must restart gateway after patching. Old `.pyc` cache and running processes keep stale code.

### "Your request was blocked" (HTTP 403) — Cloudflare WAF blocking OpenAI Python client

HTTP 403 with "Your request was blocked" — this is **Cloudflare's WAF** (Kie.ai's front-end), NOT Gemini's safety filter.

**Root cause (confirmed 2026-06-03):** Kie.ai's Cloudflare WAF blocks requests with `User-Agent: OpenAI/Python X.Y.Z`. The OpenAI Python client (used by Hermes) sends this UA by default. `requests`, `httpx` direct, and `curl` work fine because they use different UAs.

**Symptoms in Hermes logs:**
```
PermissionDeniedError ... HTTP 403: Your request was blocked.
Non-retryable client error: Your request was blocked.
Streaming failed before delivery: Your request was blocked.
```

**Diagnosis:**
1. `tail -100 ~/.hermes/logs/errors.log | grep -i "blocked\|403\|PermissionDenied"` — confirm the error.
2. Test with curl (should work): `curl -s ... -d '{"model":"gemini-3-5-flash","messages":[{"role":"user","content":"say OK"}],"max_tokens":5}'`
3. Test with OpenAI Python client (should fail): `OpenAI(api_key=key, base_url=".../v1").chat.completions.create(...)`

**Fix:** Add a kie.ai host check in `create_openai_client()` in `agent/agent_runtime_helpers.py` (~line 1255, right after `client_kwargs = dict(client_kwargs)` and the validation calls):

```python
    client_kwargs = dict(client_kwargs)
    _validate_proxy_env_urls()
    _validate_base_url(client_kwargs.get("base_url"))
    # Kie.ai Cloudflare WAF blocks OpenAI Python User-Agent
    _cbu = str(client_kwargs.get("base_url") or "")
    if "api.kie.ai" in _cbu and "default_headers" not in client_kwargs:
        client_kwargs["default_headers"] = {
            "User-Agent": "Mozilla/5.0 (compatible; HermesAgent/1.0)",
        }
```

**Pitfall:** Do NOT patch `agent/agent_init.py` alone — it only covers the initial client creation. When the user switches model via `/model` in the TUI, `switch_model()` in `agent/agent_runtime_helpers.py` builds `_client_kwargs` directly (line ~1471) and calls `_create_openai_client()` without going through `agent_init.py`. The fix MUST be in `create_openai_client()` to cover all code paths (init, switch, fallback, credential rotation).

**Pitfall:** Must clear `.pyc` cache after patching: `find ~/.hermes/hermes-agent -name "*.pyc" -path "*agent_runtime*" -delete` (and `*agent_init*` if that was also patched).

**Do NOT confuse with Gemini's actual safety filter**, which returns different errors and is content-triggered.

### No prompt caching

Kie.ai does NOT expose Gemini's context caching (`CachedContent`). Every call bills full prompt tokens. Verified: same prompt 3x → identical `prompt_tokens` each time, no `cached_tokens` field.

### Google native format (alternative)

Gemini 3.5 Flash also works via `POST /gemini/v1/models/gemini-3-5-flash:generateContent` with Google's native `contents/parts` payload. NOT compatible with Hermes's OpenAI transport — use for direct API calls only.

## Usage

```bash
hermes -m gemini-3.1-pro --provider kie-gemini-pro -q "task"
hermes -m gemini-3-5-flash --provider kie-gemini-flash -q "task"
```

## Related Skills

- `kie-video-generation` — parent Kie.ai skill (video, image, Claude, pricing)
- `hermes-agent` — Hermes provider configuration reference
