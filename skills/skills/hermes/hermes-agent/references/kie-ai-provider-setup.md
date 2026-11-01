# Kie.ai Claude Provider Setup

Kie.ai provides Claude models at a discount. Configure as a **provider** (not a profile).

## Config

In `config.yaml` under `providers`:
```yaml
providers:
  kie-claude:
    api: https://api.kie.ai/claude
    api_mode: anthropic_messages
    key_env: KIE_API_KEY
    default_model: claude-opus-4-6
    models:
      - claude-opus-4-6
      - claude-sonnet-4-6
      - claude-opus-4-5
      - claude-opus-4-7
      - claude-haiku-4-5
    name: Kie.ai Claude
```

## Auth

- `KIE_API_KEY` in `.env` and vault (`kie/api_key`)
- Uses **Bearer token** auth (not x-api-key)
- Hermes anthropic_messages transport handles auth automatically

## Key Gotcha

The auto-detection `_detect_api_mode_for_url()` does NOT recognize `api.kie.ai/claude` as Anthropic. The `api_mode: anthropic_messages` field in the provider config is **required** — without it, Hermes falls back to `chat_completions` which fails with `AssertionError`.

## Usage

```bash
# As fallback in any profile
hermes -p coder chat -m claude-opus-4-7 --provider kie-claude -q "task"

# In smart_model_routing
- name: backend
  provider: kie-claude
  model: claude-opus-4-7
  match:
    any_keywords: [backend, api, database]
```

## Cost Awareness

Full Hermes payload = ~50K tokens (system prompt + 47 tools + memory + skills). At Claude Opus pricing, that's ~$0.50/call. Use Kie Claude as a **worker tool** receiving minimal task capsules (~2K tokens, ~$0.02/call), NOT as the orchestrator model.
