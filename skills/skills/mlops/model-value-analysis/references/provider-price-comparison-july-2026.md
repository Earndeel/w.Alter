# Provider Price Comparison — July 2026

Cross-provider pricing for key LLMs. OpenAI API/Codex, OpenRouter, and Kie.ai.
Prices per 1M tokens (input / output). All data live as of July 26, 2026.

## GPT-5.6 Family

| Model | OpenAI API/Codex | OpenRouter | Kie.ai |
|---|---|---|---|
| GPT-5.6 Sol | $5.00 / $30.00 | $5.00 / $30.00 | **$1.40 / $8.40** (−72%) |
| GPT-5.6 Terra | $2.50 / $15.00 | $2.50 / $15.00 | — |
| GPT-5.6 Luna | $1.00 / $6.00 | $1.00 / $6.00 | **$0.28 / $1.68** (−72%) |
| GPT-5.5 | — | $5.00 / $30.00 | $1.40 / $8.40 |

Kie.ai applies a uniform **72% discount** off OpenAI official pricing. OpenRouter = official pricing, no markup.

## Claude Family

| Model | OpenRouter | Kie.ai | Kie.ai discount |
|---|---|---|---|
| Claude Opus 5 | $5.00 / $25.00 | — | — |
| Claude Opus 4.8 | $5.00 / $25.00 | **$2.00 / $10.00** | −60% |
| Claude Opus 4.7 | $5.00 / $25.00 | **$1.43 / $7.15** | −71% |
| Claude Sonnet 5 | $2.00 / $10.00 | ~$0.85 / $4.28 | −57% |
| Claude Fable 5 | $10.00 / $50.00 | — | — |
| Claude Haiku 4.5 | $1.00 / $5.00 | — | — |

Key: Kie.ai is **always cheaper for Claude** (60-71% less than OpenRouter).
However, Kie.ai does not support streaming (Cloudflare drops SSE chunks) and
is slower (~72 tok/s vs 1626 tok/s for DeepSeek).

## Other Models (OpenRouter only)

| Model | Input/M | Output/M | Notes |
|---|---|---|---|
| DeepSeek V4 Pro | $0.44 | $0.87 | Cheapest frontier model |
| DeepSeek V4 Flash | $0.14 | $0.28 | Cheapest absolute |
| Grok 4.5 | $2.00 | $6.00 | |
| MiniMax-M3 | $0.30 | $1.20 | |
| GLM-5.2 | $0.67 | $2.12 | |
| Kimi K3 | $3.00 | $15.00 | |
| Gemini 3.6 Flash | $1.50 | $7.50 | |
| Gemini 3.1 Pro | $2.00 | $12.00 | |
| Muse Spark 1.1 | $1.25 | $4.25 | |

## Codex Plus Subscription Economics

Codex Plus ($20/mo) uses a **credit system** (1 credit = $0.04):

| Model | Credits/1M input | Credits/1M cached | Credits/1M output |
|---|---|---|---|
| GPT-5.6 Sol | 125 | 12.5 | 750 |
| GPT-5.6 Terra | 62.5 | 6.25 | 375 |
| GPT-5.6 Luna | 25 | 2.5 | 150 |

Quota: 15-90 Sol msgs per 5h rolling window, 20-110 Terra, 50-280 Luna.
Plus a separate weekly cap. Credit top-ups available when exhausted.

**Breakeven Codex Plus vs Kie.ai:**
- Codex Plus wins above ~60 sessions/month (2/day)
- Kie.ai wins below ~35 sessions/month
- Between 35-60: depends on model mix (Sol-heavy favors Codex, Luna-heavy favors Kie.ai)

**Optimal mix:** Codex Plus for daily use within quota, Kie.ai for Claude models
and when quota exhausted.
