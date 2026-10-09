# Third-Party Anthropic-Compatible Provider Integration

Hermes can talk to non-Anthropic endpoints that speak the Anthropic Messages API (e.g., Kie.ai Claude, Azure Anthropic, DashScope, MiniMax). This requires setting `api_mode: anthropic_messages` in the **provider entry**, not the top-level `model` block.

## Config Shape

```yaml
model:
  base_url: https://api.kie.ai/claude
  default: claude-opus-4-6
  provider: kie-claude
  # Do NOT put api_mode here for custom providers

providers:
  kie-claude:
    api: https://api.kie.ai/claude
    api_mode: anthropic_messages      # <-- drives transport selection
    default_model: claude-opus-4-6
    models:
      - claude-opus-4-6
      - claude-sonnet-4-6
    name: Kie Claude
```

**Critical:** The `api_mode` field lives inside the `providers.<name>` dict. Hermes resolves it via `_get_named_custom_provider()` → `_parse_api_mode(entry.get("api_mode") or entry.get("transport"))`. Setting it under `model.api_mode` does **not** work for custom providers.

## API Key Resolution

The provider entry is checked in this order:
1. `key_env` → reads from env var (e.g., `KIE_API_KEY`)
2. `api_key` → inline key in config.yaml
3. Fallback to `OPENAI_API_KEY`, then `OPENROUTER_API_KEY`

Recommended: store the key in `.env` as `KIE_API_KEY=...` and reference it via `key_env: KIE_API_KEY` in the provider entry.

## Kie.ai Direct Mode: Common Misconfiguration

Kie.ai Claude works directly through Hermes' `anthropic_messages` transport when the provider entry resolves the **real Kie key** and the Anthropic adapter treats Kie as a Bearer-auth endpoint.

**Required patches/config:**
- `agent/anthropic_adapter.py` `_requires_bearer_auth(...)` includes `https://api.kie.ai/claude` so the SDK sends `Authorization: Bearer ...` instead of Anthropic's native `x-api-key`.
- `providers.kie-claude.key_env: KIE_API_KEY` is present. Without it, the named custom provider can fall back to `OPENAI_API_KEY` / `OPENROUTER_API_KEY`, producing misleading `AssertionError` or `Empty/malformed response` failures.
- Optional but useful: normalize Claude-Code-style tool aliases (`Bash` → `terminal`, `Read` → `read_file`, etc.) before tool validation, because Kie-hosted Claude can emit Claude Code tool names even when Hermes advertised canonical Hermes names.

**Symptoms when `key_env` is missing or wrong:**
```
API call failed: AssertionError
Provider: custom  Model: claude-opus-4-6
Endpoint: https://api.kie.ai/claude
```

or after forcing non-streaming:
```
Empty/malformed response — switching to fallback
API Response received - Model: None, Usage: None
```

**Fix:** add `key_env: KIE_API_KEY` to the provider entry and ensure the profile `.env` contains `KIE_API_KEY=...`. Do not route through OpenRouter for this endpoint.

## Fallback Workaround: LiteLLM Bridge

Only use this if direct `anthropic_messages` mode still fails after verifying credits and `key_env`.

```bash
pip install litellm
litellm --model anthropic/claude-opus-4-6 \
        --api_base https://api.kie.ai/claude \
        --api_key "$KIE_API_KEY" \
        --port 4000
```

Then point a separate Hermes provider at `http://localhost:4000/v1`. This bypasses Hermes' native Anthropic transport and uses the OpenAI-compatible path.

## Diagnostics & Credit Check

When a third-party Anthropic-compatible endpoint returns cryptic errors (e.g., `AssertionError` from the Anthropic SDK during streaming), **check the account balance first** before assuming a transport bug.

```bash
# Check remaining credits on Kie.ai
curl -s -H "Authorization: Bearer $KIE_API_KEY" \
  https://api.kie.ai/api/v1/chat/credit
```

**Negative balance** (`{"data": -319.75}`) causes all Claude requests to fail with HTTP 402 — but the Anthropic SDK may surface this as an `AssertionError` during SSE stream parsing rather than a clean HTTP error. This looks identical to a transport bug but is simply an exhausted account.

**Symptom vs Root Cause:**
| Observed Error | Likely Root Cause | Fix |
|----------------|-------------------|-----|
| `AssertionError` during stream | Insufficient credits (402) | Top up account |
| `AssertionError` during stream | Non-standard SSE format | Use LiteLLM bridge |
| `404 Not Found` on `/v1/messages` | Wrong base_url path | Verify endpoint docs |

**Quick diagnostic flow:**
1. Check credits (`/api/v1/chat/credit`)
2. If positive, test non-streaming: `curl ... -d '{"stream": false}'`
3. If non-streaming works but streaming fails → use LiteLLM bridge (see above)
4. If both fail → check model name, API key, or base_url

## Verified Endpoints

| Provider | Base URL | api_mode | Streaming Works |
|----------|----------|----------|-----------------|
| Anthropic official | `https://api.anthropic.com` | `anthropic_messages` | Yes |
| Kie.ai Claude | `https://api.kie.ai/claude` | `anthropic_messages` | Yes, with `key_env: KIE_API_KEY` + Bearer-auth patch |
| Azure Anthropic | `https://*.azure.com/anthropic` | `anthropic_messages` | Yes |
