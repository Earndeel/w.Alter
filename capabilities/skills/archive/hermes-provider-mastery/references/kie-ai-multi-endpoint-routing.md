# Kie.ai Multi-Endpoint Dynamic Routing — Full Patch Implementation

## Problem

Kie.ai routes different model families through different endpoints:
- Claude: `POST /claude/v1/messages` (Anthropic Messages API)
- Gemini: `POST /gemini-3-5-flash-openai/v1/chat/completions` (OpenAI wire)
- GPT: `POST /chat/gpt-5-5/v1/chat/completions` (OpenAI wire)

Hermes `config.yaml` uses a single `providers.kie.api: https://api.kie.ai` for ALL models.
Without routing, the runtime sends everything to `https://api.kie.ai/chat/completions` → 404 for Claude.

Additionally, Kie.ai's Cloudflare WAF blocks the default `hermes-cli/x.x.x` User-Agent.
And the Anthropic adapter defaults to `x-api-key` header, but Kie.ai needs `Authorization: Bearer`.

## The 6 Patches

### Patch 1: Gateway-Level Routing (`gateway/run.py`)

**Why:** This is the PRIMARY routing point. It runs for every conversation turn AND at startup.
Must be placed where BOTH model name and base_url are known — in `_resolve_gateway_session_model()`,
just before the `return model, runtime_kwargs`.

```python
# Add before _resolve_runtime_agent_kwargs():
def _kie_resolve(base_url: str | None, model: str) -> tuple[str, str]:
    """Rewrite Kie.ai base_url and return (new_url, api_mode)."""
    if not base_url or "kie.ai" not in base_url.lower():
        return base_url, "chat_completions"
    m = (model or "").strip().lower()
    if "claude" in m or "haiku" in m or "sonnet" in m or "opus" in m:
        return "https://api.kie.ai/claude", "anthropic_messages"
    if "gemini-3-5-flash" in m or "gemini-3.5-flash" in m:
        return "https://api.kie.ai/gemini-3-5-flash-openai/v1", "chat_completions"
    if "gemini-3.1-pro" in m or "gemini-3-1-pro" in m:
        return "https://api.kie.ai/gemini-3.1-pro/v1", "chat_completions"
    if "gpt-5-5" in m or "gpt-5.5" in m:
        return "https://api.kie.ai/chat/gpt-5-5/v1", "chat_completions"
    if "gpt-5-4" in m or "gpt-5.4" in m:
        return "https://api.kie.ai/chat/gpt-5-4/v1", "chat_completions"
    return base_url, "chat_completions"

def _kie_route(base_url: str | None, model: str, runtime: dict | None = None) -> str | None:
    """Convenience wrapper — rewrites base_url, optionally patches runtime dict."""
    url, mode = _kie_resolve(base_url, model)
    if runtime is not None and url != base_url:
        runtime["api_mode"] = mode
    return url
```

In `_resolve_gateway_session_model()`, just before `return model, runtime_kwargs`:
```python
        # ── Kie.ai dynamic URL routing (gateway-level) ──
        if runtime_kwargs and "kie.ai" in str(runtime_kwargs.get("base_url", "")).lower():
            new_url, new_mode = _kie_resolve(runtime_kwargs.get("base_url"), model)
            if new_url != runtime_kwargs.get("base_url"):
                runtime_kwargs["base_url"] = new_url
                runtime_kwargs["api_mode"] = new_mode
```

**DO NOT** put this in `_resolve_runtime_agent_kwargs()` — the model isn't known there yet.

### Patch 2: Runtime Switch (`agent/agent_runtime_helpers.py`)

In `switch_model()`, after `determine_api_mode()`:

```python
    # ── Kie.ai dynamic URL routing ──
    if base_url and "kie.ai" in base_url.lower():
        _m = (new_model or "").strip().lower()
        if "claude" in _m or "haiku" in _m or "sonnet" in _m or "opus" in _m:
            base_url = "https://api.kie.ai/claude"
            api_mode = "anthropic_messages"
        elif "gemini-3-5-flash" in _m or "gemini-3.5-flash" in _m:
            base_url = "https://api.kie.ai/gemini-3-5-flash-openai/v1"
        elif "gemini-3.1-pro" in _m or "gemini-3-1-pro" in _m:
            base_url = "https://api.kie.ai/gemini-3.1-pro/v1"
        elif "gpt-5-5" in _m or "gpt-5.5" in _m:
            base_url = "https://api.kie.ai/chat/gpt-5-5/v1"
        elif "gpt-5-4" in _m or "gpt-5.4" in _m:
            base_url = "https://api.kie.ai/chat/gpt-5-4/v1"
```

### Patch 3: Auxiliary Client (`agent/auxiliary_client.py`)

In `resolve_provider_client()`, after base_url is resolved, add routing before client creation.

### Patch 4: Anthropic Auth (`agent/anthropic_adapter.py`)

Two changes:
1. Add `"kie.ai"` to `_requires_bearer_auth()` return set
2. In `build_anthropic_client()`, add `default_headers` with browser-like User-Agent for kie.ai

```python
# In _requires_bearer_auth():
    if any(d in base_url_lower for d in ("aiprimetech.io", "kie.ai")):
        return True

# In build_anthropic_client(), after existing header setup:
    if "kie.ai" in (resolved_base_url or "").lower():
        extra_headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
```

### Patch 5: OpenAI Client User-Agent (`agent/agent_runtime_helpers.py`)

In `create_openai_client()`, for kie.ai base URLs, set browser-like User-Agent:

```python
    if base_url and "kie.ai" in base_url.lower():
        default_headers = default_headers or {}
        default_headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
```

### Patch 6: Validation (`hermes_cli/models.py`)

In `validate_requested_model()`, before the generic `fetch_api_models` probe:
- Detect kie.ai, rewrite URL + api_mode for Claude models
- Route through `anthropic_messages` path (gracefully accepts non-verifiable models)

In `probe_api_models()`:
- Detect kie.ai, use Bearer auth instead of x-api-key
- Use browser-like User-Agent

## Diagnostic: Identifying the Problem

Symptoms:
1. `/model` shows "Error: Your request was blocked by the provider" → Cloudflare WAF (User-Agent)
2. `/model` shows "could not reach API to validate" → `/v1/models` 404
3. Agent "stuck on reasoning" → runtime sends to wrong endpoint (404, retries with backoff)
4. `agent.log` shows `path=/chat/completions` for Claude models → missing routing

```bash
# Check agent.log for the actual endpoint being hit
grep "path=" ~/.hermes/logs/agent.log | tail -10

# Check for 404 retries
grep "HTTP 404" ~/.hermes/logs/errors.log | tail -10

# Verify patch is in place
grep "Kie.ai dynamic" ~/.hermes/hermes-agent/gateway/run.py
grep "Kie.ai dynamic" ~/.hermes/hermes-agent/agent/agent_runtime_helpers.py
```

## Post-Update Re-Application Checklist

After every `hermes update`:
1. Re-apply all 6 patches
2. `find ~/.hermes/hermes-agent -name "*.pyc" -delete`
3. `systemctl --user restart hermes-gateway`
4. Verify with: `grep "Kie.ai dynamic" ~/.hermes/hermes-agent/gateway/run.py`
