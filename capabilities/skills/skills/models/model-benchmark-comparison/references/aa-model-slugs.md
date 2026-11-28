# artificialanalysis.ai Valid Model Slugs

> Discovered via brute-force probing + API v2 dump. 523+ models in the API (May 2026).

## Data sources

1. **API v2** (`GET /api/v2/data/llms/models` + `x-api-key`): all 523+ models with intel, speed, pricing. NO context window.
2. **Leaderboard scrape** (`/leaderboards/models`): full table with context windows. Use Scrapling MCP: `mcp_scrapling_fetch(url="https://artificialanalysis.ai/leaderboards/models", css_selector="table", wait=6000)`.
3. **Individual pages** (`/models/<slug>`): detailed per-model data.

## Key new entrants (May 2026)

| Slug | Name | Intel | Speed | In $/1M | Out $/1M | Notes |
|------|------|-------|-------|---------|----------|-------|
| gemini-3-5-flash | Gemini 3.5 Flash (high) | 55.3 | 219 | $1.50 | $9.00 | Best daily driver, 1M ctx |
| gemini-3-5-flash-minimal | Gemini 3.5 Flash (minimal) | 43.3 | 236 | $1.50 | $9.00 | Cheap mode |
| qwen3-7-max | Qwen3.7 Max | 56.6 | - | $2.50 | $7.50 | Alibaba flagship |
| mimo-v2-5 | MiMo-V2.5 | 49.0 | 91 | $0.36 | $1.80 | Xiaomi mid-range beast |
| mimo-v2-flash | MiMo-V2-Flash | 41.5 | 132 | $0.10 | $0.30 | Best ultra-budget |
| mimo-v2-omni | MiMo-V2-Omni | 43.4 | 108 | $0.00 | $0.00 | Best free model |
| step-3-5-flash | Step 3.5 Flash | 37.8 | 190 | $0.10 | $0.30 | StepFun, very fast |
| hy3 | Hy3-preview (Reasoning) | 41.9 | 100 | $0.12 | $0.43 | Tencent newcomer |
| kimi-k2-6 | Kimi K2.6 | 53.9 | 57 | $0.95 | $4.00 | Strong reasoning |
| glm-5-1 | GLM-5.1 (Reasoning) | 51.4 | 53 | $1.40 | $4.40 | Z AI |
| minimax-m2-7 | MiniMax-M2.7 | 49.6 | 51 | $0.30 | $1.20 | MiniMax flagship |
| command-a-plus | Command A+ | 37.2 | 203 | $0.00 | $0.00 | Cohere, 0.27s latency |
| gpt-5-4-nano | GPT-5.4 nano (xhigh) | 44.0 | 156 | $0.20 | $1.25 | OpenAI cheap reasoning |
| grok-4-3 | Grok 4.3 (high) | 53.2 | 110 | $1.25 | $2.50 | xAI 1M ctx |

## Previously confirmed (still valid)

| Slug | Intel | Speed | In $/1M | Out $/1M | Context |
|------|-------|-------|---------|----------|---------|
| gemini-3.1-pro-preview | 57 | 142 | $2.00 | $12.00 | 1.0M |
| gemini-3.1-flash-lite-preview | 34 | 342 | $0.25 | $1.50 | 1.0M |
| gemini-3-flash | 35 | 185 | $0.50 | $3.00 | 1.0M |
| deepseek-v4-pro | 52 | 30 | $1.74 | $3.48 | 1.0M |
| deepseek-v4-flash | 47 | 111 | $0.14 | $0.28 | 1.0M |
| qwen3.6-plus | 50 | 52 | $0.50 | $3.00 | 1.0M |
| gemma-4-31b | 39 | 35 | $0.00 | $0.00 | 260k |
| gpt-oss-120b | 33 | 310 | $0.15 | $0.60 | 130k |
| mercury-2 | 33 | 790 | $0.25 | $0.75 | 130k |
| mimo-v2-5-pro | 54 | 55 | $1.00 | $3.00 | 1.0M |
| claude-opus-4-7 | 57 | 49 | $6.25 | $25.00 | 1.0M |
| llama-4-scout | 14 | 117 | $0.17 | $0.66 | 10M |
