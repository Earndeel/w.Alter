# Custom Anthropic-Compatible Providers

When using third-party Claude endpoints (Kie.ai, DashScope, Azure, proxies), the provider must be configured with `api_mode: anthropic_messages` in `config.yaml`.

## Auto-detection rules (from `runtime_provider.py`)

These URLs auto-detect as `anthropic_messages`:
- URL ending with `/anthropic` (e.g., `https://api.minimax.io/anthropic`)
- `api.kimi.com` with `/coding` in path
- `api.openai.com` → `codex_responses` (not anthropic)
- `api.x.ai` → `codex_responses`

**Everything else falls back to `chat_completions`** — which fails for Anthropic-native APIs.

## Required config pattern

```yaml
# ~/.hermes/config.yaml
providers:
  kie-claude:
    api: https://api.kie.ai/claude
    api_mode: anthropic_messages    # ← CRITICAL
    key_env: KIE_API_KEY            # ← reads from .env
    default_model: claude-opus-4-6
    models:
      - claude-opus-4-6
      - claude-sonnet-4-6
      - claude-opus-4-7
      - claude-haiku-4-5
    name: Kie.ai Claude
```

## Auth

- Kie.ai uses **Bearer token** auth (not x-api-key)
- The Anthropic SDK handles this automatically when `api_mode: anthropic_messages`
- Key must be in `~/.hermes/.env` as `KIE_API_KEY=<key>` AND in vault

## Verification

```bash
# Direct API test (should return 200)
curl -s -w '\n%{http_code}' "https://api.kie.ai/claude/v1/messages" \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4-6","max_tokens":50,"messages":[{"role":"user","content":"test"}]}'

# Via Hermes (should show provider=custom, transport=anthropic_messages)
hermes chat -v -m claude-opus-4-6 --provider kie-claude -q "test" 2>&1 | grep 'provider\|transport\|api_mode'
```

## Pitfalls

- **Timeout**: Full Hermes system prompt (47 tools + skills + memory) is heavy. Kie.ai latency ~15s vs ~3-5s for native providers. Set appropriate timeouts.
- **URL pattern**: `api.kie.ai/claude` does NOT end with `/anthropic` so auto-detection fails. The explicit `api_mode` field is mandatory.
- **Profile-local providers**: If a profile needs the provider too, add the same `providers.kie-claude` block to that profile's `config.yaml`.
- **Fallback config**: Add as fallback provider in profiles: `fallback_providers: [{model: claude-opus-4-6, provider: kie-claude}]`
