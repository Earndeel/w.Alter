# Xiaomi MiMo Provider

## Configuration

Provider entry in `config.yaml`:

```yaml
providers:
  xiaomi:
    name: "Xiaomi MiMo"
    api: https://token-plan-sgp.xiaomimimo.com/v1
    default_model: mimo-v2.5-pro
    key_env: XIAOMI_API_KEY
    models:
      - mimo-v2.5-pro
      - mimo-v2.5
      - mimo-v2-pro
      - mimo-v2-flash
      - mimo-v2-omni
```

## Key Details

- **Endpoint**: `token-plan-sgp.xiaomimimo.com/v1` (Token Plan, Singapore region)
- **Public API**: `api.xiaomimimo.com/v1/chat/completions` (OpenAI-compatible)
- **Auth**: API key via `XIAOMI_API_KEY` env var (header: `api-key: $KEY` or `Authorization: Bearer $KEY`)
- **Context window**: 1M tokens, no extra multiplier charge
- **Cost**: Very cheap — primary fallback for free-tier exhaustion

## Pricing (as of 2026-06)

| Model | Input/M | Output/M | Cached/M |
|---|---|---|---|
| mimo-v2.5-pro | $0.435 | $0.87 | $0.0036 |
| mimo-v2.5 | $0.14 | $0.28 | — |

- **Cache hit rate**: ~99% cheaper than input (120:1 ratio)
- **Blended price** (7:2:1 cache/input/output): **$0.18/M** via direct API
- **Via OpenRouter**: $0.51-0.64/M blended (OpenRouter margin)

## Prompt Caching — CRITICAL DIFFERENCE FROM ANTHROPIC

### MiMo: Automatic Prefix Caching (NOT manual breakpoints)

MiMo uses **server-side automatic prefix caching**, fundamentally different from Anthropic's manual `cache_control` breakpoint system:

| | Anthropic (Claude) | MiMo (Xiaomi) |
|---|---|---|
| Mechanism | Manual `cache_control` breakpoints (max 4) | Automatic prefix hash matching |
| Control | User places breakpoints | Server decides |
| Headers needed | `cache_control` required | **NONE** (breaks cache if sent) |
| Granularity | Block-level | Full prefix match |
| TTL | 5 minutes (refreshed on hit) | Not documented (load-dependent) |

### How MiMo caching works

1. Server hashes tokens per block on each request
2. Looks for identical prefix already in KV-cache
3. **Routing**: request is sent to a Prefill node that already has the prefix cached
4. **SWA retention**: KV-cache maintained at fixed positions, enabling cross-session reuse (shared system prompts, repeated tool calls, RAG contexts)

### ⚠️ PITFALL: Do NOT send `cache_control` headers to MiMo direct API

Sending Anthropic-style `cache_control` headers to `api.xiaomimimo.com` causes **0% cache hit rate**. This is a known issue (opencode #26460, litellm #19923). The MiMo API ignores or misinterprets these headers.

**Best practice**: Use MiMo's API as pure OpenAI-compatible — no `cache_control`, no special headers. The server handles caching automatically.

**Via OpenRouter**: OpenRouter adapts headers correctly, so caching works. But blended price is higher due to OpenRouter margin.

### Maximizing cache hits

- Keep **system prompt stable** at the start of requests
- Reuse the same prefix across conversation turns
- Agents with repeated tool calls (Claude Code style) easily achieve **90%+ cache hit rate**
- Cross-session cache works for shared system prompts (SWA retention strategy)

## MiMo-V2.5-Pro-UltraSpeed

Limited-access variant (June 9-23, 2026):
- **1T parameters**, up to **1000 tokens/s** inference
- Application-based access: `ultraspeed.xiaomimimo.com`
- Same model quality as V2.5-Pro, optimized inference backend
- Not available on OpenRouter — Xiaomi direct only
- **Stricter rate limits** than standard Pro — free tier can return 429 on first requests

### UltraSpeed Endpoint Config

```yaml
providers:
  xiaomi-ultraspeed:
    name: "Xiaomi MiMo UltraSpeed"
    api: https://api.xiaomimimo.com/v1
    default_model: mimo-v2.5-pro-ultraspeed
    key_env: XIAOMI_ULTRASPEED_API_KEY
    models:
      - mimo-v2.5-pro-ultraspeed
```

### Troubleshooting: "Pondering" with no output

If the TUI shows "pondering" indefinitely after adding UltraSpeed:

1. **Check for 429s** — Verify the API responds with 200 via curl to the `/v1/models` endpoint.
2. **Check for React error #185** — UltraSpeed's >1000 tok/s can trigger `useVirtualHistory` infinite loops in the TUI. Fix documented in `hermes-tui-display` skill, pitfall #27, reference `usevirtualhistory-infinite-loop.md`.
3. **Verify key permissions** — the key must have UltraSpeed access granted (application-based). Standard Xiaomi keys don't auto-unlock UltraSpeed.

## Fallback Chain Example

```yaml
fallback_providers:
  - model: moonshotai/kimi-k2.6:free
    provider: openrouter
  - model: xiaomi/mimo-v2.5-pro
    provider: openrouter
```

When OpenRouter free tier (Kimi) exhausts, falls back to MiMo via OpenRouter, then to direct Xiaomi gateway.
