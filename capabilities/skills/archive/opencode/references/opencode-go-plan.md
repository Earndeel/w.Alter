# OpenCode Go Plan — Model Reference

$5 first month, then $10/month. Hosted in US, EU, Singapore.
Base URL: `https://opencode.ai/zen/go/v1`
Auth: OpenCode API key via `x-api-key` header.

## Models (15 as of May 2026)

### OpenAI-compatible (`/v1/chat/completions`)

| Model ID | Name | Notes |
|----------|------|-------|
| `glm-5` | GLM-5 | Zhipu |
| `glm-5.1` | GLM-5.1 | Zhipu |
| `kimi-k2.5` | Kimi K2.5 | Moonshot |
| `kimi-k2.6` | Kimi K2.6 | Moonshot, AA 54 |
| `deepseek-v4-pro` | DeepSeek V4 Pro | |
| `deepseek-v4-flash` | DeepSeek V4 Flash | AA 47 |
| `mimo-v2.5` | MiMo V2.5 | Xiaomi |
| `mimo-v2.5-pro` | MiMo V2.5 Pro | Xiaomi, AA 54 |
| `mimo-v2-pro` | MiMo V2 Pro | |
| `mimo-v2-omni` | MiMo V2 Omni | |

### Anthropic-compatible (`/v1/messages`)

| Model ID | Name | Notes |
|----------|------|-------|
| `qwen3.7-max` | Qwen3.7 Max | Alibaba Cloud backend |
| `qwen3.6-plus` | Qwen3.6 Plus | |
| `qwen3.5-plus` | Qwen3.5 Plus | |
| `minimax-m2.7` | MiniMax M2.7 | |
| `minimax-m2.5` | MiniMax M2.5 | |

## Hermes model format

```
opencode-go/<model-id>
```

Examples:
```
/model opencode-go/qwen3.7-max
/model opencode-go/kimi-k2.6
/model opencode-go/deepseek-v4-flash
```

## Rate limits (Go plan)

- 5-hour limit: $12 of usage
- Weekly limit: $30 of usage
- Monthly limit: $60 of usage
- Free models still work when limits reached

## Key difference from Zen

- Go: subscription ($10/mo), open models only (Qwen, GLM, Kimi, DeepSeek, MiMo, MiniMax)
- Zen: pay-as-you-go, frontier models (GPT-5, Claude, Gemini) + open models
- Go key: `OPENCODE_GO_API_KEY` env var
- Zen key: `OPENCODE_ZEN_API_KEY` env var
