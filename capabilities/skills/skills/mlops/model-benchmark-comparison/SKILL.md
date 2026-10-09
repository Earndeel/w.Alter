---
name: model-benchmark-comparison
description: Compare LLMs via artificialanalysis.ai benchmarks to find the best model for a specific use case (compression, extraction, reasoning, etc.). Load when the user wants to replace a model, optimize routing, or find cheaper/faster/better alternatives.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [mlops, benchmarks, model-selection, openrouter, cost-optimization]
    related_skills: [hermes-agent, openrouter-video-input]
---

# Model Benchmark Comparison

Compare LLMs via [artificialanalysis.ai](https://artificialanalysis.ai) to find the best replacement for a given workload. This skill covers the full workflow: scrape benchmark data, filter by usage quadrant, check OpenRouter availability, and recommend.

## Trigger

Load this skill when the user asks to:
- Replace a model (e.g. "why am I getting 404 on qwen3.6-plus:free?")
- Optimize model routing for cost or speed
- Find the best model for compression, extraction, reasoning, etc.
- Compare models by intelligence / speed / price / context window

## Workflow

### 1. Fetch benchmark data via API (preferred)

artificialanalysis.ai exposes a **free v2 API** that returns structured benchmark data for **all 523+ models** (May 2026).

```bash
AA_KEY=$(vault get artificial-analysis/api_key)
curl -sL "https://artificialanalysis.ai/api/v2/data/llms/models" \
  -H "x-api-key: $AA_KEY" | python3 -m json.tool
```

**Authentication:** Header `x-api-key` (NOT `Authorization: Bearer`). Returns ~523 models (as of May 2026). API key is free but requires creating an account at artificialanalysis.ai. If you get 401/404, the endpoint may have moved — check `https://artificialanalysis.ai/api-reference` for the latest.

**Vault CLI format:** `vault get <service>/<field>` (slash-separated, NOT space-separated). Example: `vault get artificial-analysis/api_key`. Using `vault get artificial-analysis api_key` silently fails with the usage help text.

Response fields (per model in `data` array):
- `evaluations.artificial_analysis_intelligence_index` — intelligence score (0-100, higher is better)
- `median_output_tokens_per_second` — speed (0 if not measured)
- `pricing.price_1m_input_tokens` / `price_1m_output_tokens` — pricing
- `model_creator.name` — provider (OpenAI, Google, Anthropic, etc.)
- **Context window is NOT in the v2 API** — scrape the leaderboard table instead (see step 1b).

Store the user's key in vault:
```bash
vault add artificial-analysis api_key "aa_..."
```

### 1b. Scrape leaderboard for context windows (API doesn't have them)

The v2 API lacks context window data. The leaderboard table at `/leaderboards/models` has it. Use Scrapling MCP fetcher — it renders the Next.js SPA and extracts the full HTML table as markdown:

```
mcp_scrapling_fetch(url="https://artificialanalysis.ai/leaderboards/models", extraction_type="markdown", css_selector="table", wait=6000)
```

This returns a markdown table with columns: Model | Context Window | Creator | Intelligence Index | Blended Price | Speed | Latency | End-to-End Response Time. Parse it to get context windows per model.

The main leaderboard page also lists all individual evaluations with links (TAU2, IFBench, GDPval-AA, HLE, etc.). For agentic analysis, also scrape `/evaluations/gdpval-aa` (see step 3b). Full evaluation catalog in `references/aa-evaluations.md`.

### 2. Scrape missing fields via Playwright (fallback)

If the API is unavailable, scrape the Next.js SPA. The `/models` page only lists ~25 models, but many more exist at `/models/<slug>`. **Do NOT stop at the first obvious models.** The user expects exhaustive exploration of all variants (lite, preview, reasoning, flash) — missing a `gemini-3.1-flash-lite` because only `gemini-2.5-flash` was checked is a failure mode.

**Scrape the full catalog via Playwright:**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://artificialanalysis.ai/models', wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(5000)
    html = page.content()
    browser.close()

import re
slugs = re.findall(r'href="/models/([^"]+)"', html)
print(sorted(set(slugs)))
```

**Then brute-force probe common variant patterns:**
- `gemini-3-1-flash-lite-preview` (often missing from the list)
- `gemini-2-5-flash-lite`
- `gemini-3-flash`
- `gemini-3-pro`
- `qwen3-6-plus`, `qwen3-6-max`, `qwen3-6-flash`
- `deepseek-v4-flash`, `deepseek-v4-pro`, `deepseek-v3-2`
- `gemma-4-31b`, `gemma-3-27b`, `gemma-3-12b`, `gemma-3-4b`
- `mistral-small-4`, `ministral-3-3b`, `ministral-3-8b`
- `gpt-oss-120b`, `gpt-oss-20b`
- `llama-4-maverick`, `llama-4-scout`
- `nova-2-0-lite`, `mercury-2`

Probe each candidate:
```python
page.goto(f'https://artificialanalysis.ai/models/{slug}', ...)
if '404' not in page.inner_text('body')[:100]:
    # Model page exists — extract data
```

### 2. Extract per-model data

For each valid slug, extract these fields from the model page:

| Field | Regex pattern in page text |
|-------|---------------------------|
| Intelligence Index | `scores (\d+) on the Artificial Analysis Intelligence Index` |
| Input price | `is (\$[\d.]+) per 1M input tokens` |
| Output price | `and (\$[\d.]+) per 1M output tokens` |
| Speed | `At (\d+) tokens per second` |
| Context window | `context window of ([\d.]+)[kK]? tokens` |

### 3b. For agentic use cases, scrape GDPval-AA Elo rankings

**CRITICAL: The main leaderboard's tool-calling benchmarks (TAU2, IFBench, Terminal-Bench) do NOT predict real-world agentic performance.** The dedicated agentic evaluation **GDPval-AA** ("Agentic real-world work tasks") uses Elo ratings on actual work tasks. Claude scores poorly on TAU2 (88.6%) but dominates GDPval-AA (Elo 1753, #3). Grok 4.3 leads TAU2 (97.7%) but ranks #22 on GDPval-AA (Elo 1495).

For agentic model selection, ALWAYS scrape the GDPval-AA leaderboard:

```
mcp_scrapling_fetch(
  url="https://artificialanalysis.ai/evaluations/gdpval-aa",
  extraction_type="markdown",
  css_selector="table",
  wait=6000
)
```

This returns an Elo-ranked table of 374+ models tested on real agentic tasks. Top 5 (May 2026):
1. GPT-5.5 (xhigh) — Elo 1769, $11.25/M
2. GPT-5.5 (high) — Elo 1753, $11.25/M
3. Claude Opus 4.7 (max) — Elo 1753, $10.94/M
4. Claude Opus 4.7 (NR) — Elo 1683, $10.94/M
5. Claude Sonnet 4.6 (max) — Elo 1676, $6.56/M

**Key agentic insight — Claude excels at real-world agentic tasks** despite poor tool-calling benchmark scores, because GDPval-AA measures planning, error recovery, and multi-step orchestration — not just correct tool invocation.

**Best agentic Elo/$ ratio:**
- MiniMax-M2.7: Elo 1505, $0.22/M → 6841 Elo/$
- MiMo-V2.5: Elo 1553, $0.79/M → 1966 Elo/$
- MiMo-V2.5-Pro: Elo 1571, $1.50/M → 1047 Elo/$
- Gemini 3.5 Flash (high): Elo 1656, $3.38/M → 490 Elo/$

Other agentic evaluations available at `/evaluations/<slug>`:
- **apex-agents-aa** — Long-horizon agentic tasks
- **gdpval-aa** — Agentic real-world work tasks (Elo, THE agentic benchmark)
- **ifbench** — Instruction following (percentage)
- **terminalbench-hard** — Agentic coding in terminal (percentage)
- **tau2** — Tool calling accuracy (percentage)

### 4. Map to usage quadrant

Filter candidates by the 3 dimensions of the user's workload:

| Usage | Min Intel | Context | Priority |
|-------|-----------|---------|----------|
| **Context compression** | 20-40 | 1M+ | Cost first, speed second |
| **Structured extraction (JSON)** | 25-40 | 128k+ | Structured-output reliability, speed |
| **Reasoning / consolidation** | 35-55 | 128k+ | Intel first, cost acceptable |
| **Agent default** | 45-60 | 128k+ | GDPval-AA Elo first, intel + tool-calling secondary |

### 4. Check provider availability

#### OpenRouter
```bash
curl -sL "https://openrouter.ai/api/v1/models" | python3 -c "
import sys, json
d = json.load(sys.stdin)
mids = [m['id'] for m in d['data']]
for target in ['google/gemini-3.1-flash-lite-preview', 'deepseek/deepseek-v4-flash']:
    print('FOUND' if target in mids else 'MISSING', target)
"
```

#### Google AI Studio (free tier)
For Gemini flash/lite models, **prefer AI Studio free tier over OpenRouter** when:
- The model is a Gemini flash/lite variant (3.1 flash lite, 3 flash, etc.)
- The workload is high-volume (compression, extraction)
- Cost is the primary concern

**AI Studio model names differ from OpenRouter slugs:**
| OpenRouter slug | AI Studio model name |
|-----------------|---------------------|
| `google/gemini-3.1-flash-lite-preview` | `gemini-3.1-flash-lite-preview` |
| `google/gemini-3-flash-preview` | `gemini-3-flash-preview` |
| `google/gemini-3.1-pro-preview` | `gemini-3.1-pro-preview` |
| `google/gemini-2.5-pro-preview-05-06` | `gemini-2.5-pro` |
| `google/gemini-3-pro-preview` | `gemini-3-pro-preview` |

Test availability:
```python
import requests
key = "AIzaSy..."
for model in ["gemini-3.1-flash-lite-preview", "gemini-3.1-pro-preview"]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    resp = requests.post(url, json={"contents": [{"role": "user", "parts": [{"text": "hi"}]}]})
    print(model, resp.status_code)
```

**Pitfall:** AI Studio free tier has rate limits (~60 RPM). For production loads, use OpenRouter or a paid Gemini tier.

### 5. Validate with live tests (CRITICAL)

**Benchmarks are not enough.** A model can score well on AA but fail in practice (JSON malformé, rate-limit, hallucination on facts, poor extraction recall).

Run a small live test battery for each candidate before recommending:

| Test | Prompt focus | Success criteria |
|------|-------------|------------------|
| **Compression** | Long conversation (1k+ tokens), ask for summary | Coverage ≥ 90% of key facts, concise |
| **Extraction** | Paragraph in French/English, ask for JSON `{"extracted_facts": [...]}` | JSON parses, fact count ≥ 15 |
| **Consolidation** | 10 redundant facts, ask to deduplicate | Unique fact count 4-6, no duplicates |

Use the script in `scripts/model_benchmark.py`:
```bash
OPENROUTER_API_KEY=$(vault get openrouter/api_key) \
GEMINI_API_KEY=$(vault get gemini/api_key) \
  python3 /root/.hermes/skills/mlops/model-benchmark-comparison/scripts/model_benchmark.py
```

Or run the AA-only analysis script (no live tests, just API rankings):
```bash
AA_KEY=$(vault get artificial-analysis/api_key) \
  python3 /root/.hermes/skills/mlops/model-benchmark-comparison/scripts/aa_analysis.py
```

**Always test extraction JSON on DeepSeek-family models before recommending them for structured-output pipelines.** DeepSeek V4 Flash scored intel=46.5 but extracted only 10 facts vs 23-26 for Gemini 3.1 Flash Lite — a 60% drop in recall. The second run improved to 25 facts, but latency was 6x slower (14s vs 2.3s).

**Always prefer AI Studio free tier for Gemini flash/lite models when cost matters.** In live tests:
- `gemini-3.1-flash-lite-preview` (AI Studio): 1.63s compression, 2.34s extraction, **$0.00**
- `deepseek-v4-flash` (OpenRouter): 4.39s compression, 14.33s extraction, $0.0002-0.0003

For consolidation, higher intelligence matters. `gemini-3.1-pro-preview` (intel=57) produced 6 clean atomic facts vs 4 fused facts from `gemini-3-flash` (intel=35). Both free on AI Studio.

## Key Benchmarks (session snapshot — May 2026)

> See `references/aa-model-slugs.md` for the full slug catalog discovered in working sessions.
> See `references/aa-evaluations.md` for the full evaluation catalog and what each one measures.

**Top intelligence (AA Index v4.0):**
- GPT-5.5 (xhigh): intel=60.2, $12.50/M, 65 t/s — highest but extremely expensive
- Claude Opus 4.7 (max): intel=57.3, $11.88/M, 49 t/s
- Gemini 3.1 Pro Preview: intel=57.2, $5.00/M, 142 t/s — **best Q/P in top 5**
- Qwen3.7 Max: intel=56.6, $4.00/M — new Alibaba flagship
- Gemini 3.5 Flash (high): intel=55.3, $3.75/M, 219 t/s — **best daily driver**

**Best intel/price ratio (intel ≥ 30):**
- DeepSeek V4 Flash (Max): intel=46.5, **$0.18/M**, 111 t/s — 130x cheaper than Claude Sonnet non-reasoning
- MiMo-V2-Flash: intel=41.5, $0.16/M, 132 t/s — Xiaomi sleeper
- Step 3.5 Flash: intel=37.8, $0.16/M, 190 t/s
- Kimi K2.6 (Moonshot): $0.73/$3.49/M, 262K ctx, ~48-68 tok/s real-world — fast long-context, free tier available (`:free`) but rate-limited

**Speed demons:**
- Mercury 2: **790 t/s**, intel=32.8, $0.40/M — fastest model by 2x
- Gemini 3.1 Flash-Lite Preview: 342 t/s, intel=33.5, $0.62/M, 1M ctx
- gpt-oss-120b: 310 t/s, intel=33.3, $0.28/M — open weights

**Free models worth using:**
- MiMo-V2-Omni (Xiaomi): intel=43.4, 108 t/s — best free model
- Kimi K2.6 (Moonshot): ~68 tok/s real-world, 262K ctx — fast but rate-limited (see pitfall #8)
- Step 3.5 Flash 2603: intel=38.5, 197 t/s — blazing fast and free
- Command A+ (Cohere): intel=37.2, 203 t/s — free, extremely low latency (0.27s)
- Gemma 4 31B (Google): intel=39.2, free, 256k ctx — best open weights free

**Key insight — Chinese models dominate price/perf:**
Xiaomi (MiMo), Alibaba (Qwen), DeepSeek, Tencent (Hy3), and StepFun occupy 80% of the "attractive quadrant" (high intel, low price). The entire MiMo-V2 family is remarkable: V2.5 at intel=49 for $0.79/M competes with GPT-5.4 non-reasoning at $6.25/M.

**Top agentic (GDPval-AA Elo, May 2026):**
> For agentic model selection, use GDPval-AA Elo — NOT TAU2/IFBench. See step 3b and `references/aa-evaluations.md`.
- GPT-5.5 (xhigh): Elo 1769, $11.25/M — #1 agentic but expensive
- Claude Opus 4.7 (max): Elo 1753, $10.94/M — #3, Claude excels at real-world agentic despite poor TAU2
- Gemini 3.5 Flash (high): Elo 1656, $3.38/M — **#7, best agentic Q/P in top 10**
- MiMo-V2.5-Pro: Elo 1571, $1.50/M — #12, best budget agentic
- MiniMax-M2.7: Elo 1505, $0.22/M — #18, highest Elo/$ ratio (6841)
- Qwen3.6 Plus: Elo 1351, $1.12/M — #43, despite 97.7% TAU2 (tool calling ≠ agentic)

## Pitfalls

1. **TAU2 tool-calling scores do NOT predict real-world agentic performance.** Claude Opus 4.7 scores 88.6% on TAU2 (poor) but ranks #3 on GDPval-AA (Elo 1753). Grok 4.3 scores 97.7% on TAU2 (#1) but only Elo 1495 on GDPval-AA (#22). For agentic use cases, ALWAYS check GDPval-AA Elo rankings, not TAU2/IFBench percentages. The `/evaluations/gdpval-aa` page has the Elo leaderboard.
2. **Individual evaluation leaderboards have richer data than the main leaderboard.** Scrape `/evaluations/<slug>` for Elo rankings (GDPval-AA, APEX-Agents-AA), percentage rankings (TAU2, IFBench, Terminal-Bench), and more models than the main leaderboard shows. The main leaderboard only shows the composite Intelligence Index — individual evaluations reveal category-specific strengths.
3. **Vault CLI format is `vault get <service>/<field>` (slash), NOT `vault get <service> <field>` (space).** Using the space form silently prints the usage help and returns exit code 1, which looks like "key not found". Always use: `vault get artificial-analysis/api_key`. Same for all vault operations: `vault add`, `vault remove` also use slash format.

1. **The `/models` page only shows ~25 models.** Always brute-force probe common variant slugs — the "lite", "preview", "reasoning", "flash" variants are often better than the flagship. Missing a `gemini-3.1-flash-lite` because only `gemini-2.5-flash` was checked is a failure mode the user will call out.
2. **artificialanalysis.ai HAS a v2 JSON API.** Use `GET /api/v2/data/llms/models` with `x-api-key` header before scraping. It returns all 523+ models (as of May 2026) with intel, speed, and pricing. Authentication is `x-api-key`, NOT `Authorization: Bearer`.
3. **Context window is NOT in the v2 API.** You still need Playwright to scrape context-window text from each model page.
4. **Context window parsing is tricky.** Some pages say "1.0M tokens" (regex `([\d.]+)[kK]?`), others "260k tokens". Normalize to a common unit.
5. **Price extraction can fail** if the page uses cache-hit pricing blends. Always look for the full sentence: "Pricing for <Model> is $X per 1M input tokens ... and $Y per 1M output tokens".
6. **Model availability on OpenRouter != benchmark availability.** A model may score well on AA but not be available on OpenRouter (or only as `:free`). Always verify.
7. **DeepSeek models can fail structured-output extraction despite high intelligence scores.** DeepSeek V4 Flash (intel=46.5) extracted only 10 facts in the first run vs 23-26 for Gemini 3.1 Flash Lite — a 60% drop in recall. Latency was also 6x slower (14s vs 2.3s).
8. **Free models on OpenRouter (`:free` suffix) are unreliable for consecutive requests.** `gemma-4-31b-it:free` returned 429 rate-limit during live testing. `moonshotai/kimi-k2.6:free` and `deepseek/deepseek-v4-flash:free` also hit 429 on second consecutive call. The `:free` tier shares a global rate-limit pool — expect ~50 req/day without credits, up to ~1000 with $10 added. For any workload requiring >1 sequential call, use the paid variant (e.g. `moonshotai/kimi-k2.6` at $0.73/$3.49 per M tok — still very cheap). Always have a paid fallback ready.
9. **Some OpenRouter slugs differ from AA slugs.** Example: `google/gemini-3-flash-preview` on OpenRouter vs `gemini-3-flash` on AA. Always query the OpenRouter model list to confirm.
10. **AI Studio free tier is better than OpenRouter for Gemini flash/lite models.** Same model, zero cost. But model names differ: OpenRouter uses `google/gemini-3.1-flash-lite-preview`, AI Studio uses `gemini-3.1-flash-lite-preview`. Rate limits apply (~60 RPM).
11. **AI Studio Pro models may hit MAX_TOKENS with default settings.** `gemini-3.1-pro-preview` and `gemini-3-pro-preview` produced truncated output with `maxOutputTokens=1024`. Increase to 2048+ for consolidation tasks.

## Credentials

If the user has an artificialanalysis.ai API key, store it in the vault:
```bash
vault add artificial-analysis api_key "aa_..."
```
The key can be used for authenticated requests if a stable API endpoint is discovered.
