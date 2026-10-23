# Model Selection Guide — Hindsight Extraction & Consolidation

Condensed benchmark research (source: artificialanalysis.ai API + empirical benchmark suite). Use when a model is deprecated, a provider changes pricing, or Lucas asks to optimize the memory stack for cost/quality.

## Three-Tier Framework

| Tier | Called by | Frequency | Input size | Key need | Cost sensitivity |
|---|---|---|---|---|---|
| **Compression** | Hermes `auxiliary.compression` | Very high (every context threshold) | Large conversation block | Summarization, long context | **Extreme** |
| **Extraction** | Write worker + dream dedup | High (every ~10 turns) | Conversation batch | Structured JSON output reliably | **High** |
| **Consolidation** | Hindsight API (dream cycle) | Low (1x/day) | Batch of memories | Reasoning, semantic merge quality | **Moderate** |

## Methodology: Benchmark-Driven Selection

Don't rely solely on artificialanalysis.ai scores. **Run empirical tests** for each candidate:

1. Fetch model data from `https://artificialanalysis.ai/api/v2/data/llms/models` (x-api-key header)
2. Filter candidates by: intelligence ≥ threshold, context ≥ requirement, price ≤ budget
3. Build a benchmark script that sends **realistic production prompts** to each candidate
4. Measure: elapsed time, token cost, JSON validity, fact coverage, output quality
5. **Validate on the actual API** (OpenRouter or AI Studio) before integrating

**Critical finding from 2026-05-04 benchmark**: `deepseek/deepseek-v4-flash` scored intel=47 on AA (near top tier) but extracted only **10 facts** vs **26 facts** for `gemini-3.1-flash-lite-preview` on the same prompt. Benchmark scores don't always translate to task-specific quality.

## Current Configuration (post-2026-05-04 swap)

| Tier | Model | Provider | Cost | Intel AA | Why |
|---|---|---|---|---|---|
| Compression | `gemini-3.1-flash-lite-preview` | AI Studio | **$0** | 34 | Fastest (1.63s), 100% coverage, 1M ctx |
| Extraction | `gemini-3.1-flash-lite-preview` | AI Studio | **$0** | 34 | 26 facts, JSON valide, 6x plus rapide que qwen |
| Consolidation | `gemini-3.1-pro-preview` | AI Studio | **$0** | 57 | Granularité parfaite, 6 faits uniques, meilleur reasoning |

All three use **AI Studio free tier** — no OpenRouter cost.

## AI Studio Free Tier vs OpenRouter

| Aspect | AI Studio | OpenRouter |
|---|---|---|
| Cost | **Free** for flash models | Pay per token |
| API format | Gemini native (`generateContent`) | OpenAI-compatible |
| System messages | ❌ Prepend to prompt | ✅ Native support |
| Structured output | `responseMimeType: "application/json"` | `response_format: {type: "json_object"}` |
| Response path | `candidates[0].content.parts[0].text` | `choices[0].message.content` |
| Model slugs | `gemini-3.1-flash-lite-preview` | `google/gemini-3.1-flash-lite-preview` |

**When to use OpenRouter**: For non-Google models (DeepSeek, Mistral, Grok) or when AI Studio rate limits (1500 req/day for flash) are exceeded.

## Benchmarks (artificialanalysis.ai + empirical)

| Model | Intel (AA) | Speed | Input | Output | Context | Empirical facts* |
|---|---|---|---|---|---|---|
| `gemini-3.1-flash-lite-preview` | 34 | **319 t/s** | $0.25 | $1.50 | 1.0M | **26** ✓ |
| `gemini-3-flash-preview` | 35 | 186 t/s | $0.50 | $3.00 | 1.0M | 27 ✓ |
| `deepseek/deepseek-v4-flash` | 47 | 83 t/s | **$0.14** | **$0.28** | 1.0M | 10 ✓ |
| `gemini-3.1-pro-preview` | **57** | 138 t/s | $2.00 | $12.00 | 1.0M | 6 (consolidation) ✓ |
| `gemini-2.5-flash-lite` | 13 | 252 t/s | $0.10 | $0.40 | 1.0M | — |
| `gemini-2.5-flash` | 21 | 207 t/s | $0.30 | $2.50 | 1.0M | — |
| `gemini-2.5-pro` | 35 | 128 t/s | $1.25 | $10.00 | 1.0M | — |
| `gpt-oss-120b` | 33 | 230 t/s | $0.15 | $0.60 | 130k | — |
| `mistral-small-4` | 28 | 170 t/s | $0.15 | $0.60 | 260k | ERREUR 400 |
| `gemma-4-31b` | 39 | 35 t/s | **$0.00** | **$0.00** | 260k | 429 rate limit |
| `qwen3.6-plus` (old) | 50 | 53 t/s | $0.50 | $3.00 | 1.0M | — |
| `gemma-3-27b` (old) | 10 | 27 t/s | $0.11 | $0.25 | 130k | — |

*Empirical facts = number of structured facts extracted from a realistic Scena Factory conversation prompt in the benchmark suite. See `scripts/model_benchmark.py`.

## Recommendations by Tier

### 1. Compression (Hermes auxiliary.compression.model)
**Best**: `gemini-3.1-flash-lite-preview` via AI Studio
- 1.63s, 100% coverage, 1.0M context, **gratuit**
- Config: `provider: gemini`, `model: gemini-3.1-flash-lite-preview`

**Alternative if AI Studio rate-limited**: `deepseek/deepseek-v4-flash` via OpenRouter
- Intel 47, $0.14/$0.28, 1.0M context, 83 t/s

### 2. Extraction (Write Worker + Dream Dedup)
**Best**: `gemini-3.1-flash-lite-preview` via AI Studio
- 26 facts en 2.34s, JSON valide à 100%, **gratuit**, 1.0M context
- Fixes Qwen alternate-schema bugs (`type/subject/context/attribute/value` instead of `fact`)
- Native structured output via `responseMimeType: "application/json"`

**Alternative if AI Studio rate-limited**: `gemini-3-flash-preview` via AI Studio
- 27 facts, légèrement plus cher mais toujours sur free tier

### 3. Consolidation (Hindsight API / Dream Cycle)
**Best**: `gemini-3.1-pro-preview` via AI Studio
- Intel 57, granularité parfaite (6 faits bien séparés), **gratuit**, 1.0M context
- Meilleur que gemma-4-31b (39) et gemini-3-flash (35) pour le reasoning

**Alternative free**: `gemini-3-flash-preview` via AI Studio
- Intel 35, fusionne trop (billing + backend ensemble), mais gratuit

## Files to Update When Swapping Models

| Tier | File | Key line |
|---|---|---|
| Compression | `~/.hermes/config.yaml` | `auxiliary.compression.model:` + `provider:` |
| Extraction | `~/.hermes/services/write_worker.py` | `EXTRACT_MODEL = os.getenv(...)` + `call_gemini_api()` |
| Extraction | `~/.hermes/services/dream_cycle.py` | `EXTRACT_MODEL = os.getenv(...)` + `call_gemini_api()` |
| Extraction | `/etc/systemd/system/write-worker.service` | `Environment=EXTRACT_MODEL=...` |
| Consolidation | `/etc/systemd/system/hindsight-api.service` | `HINDSIGHT_API_LLM_MODEL=` + `HINDSIGHT_API_LLM_PROVIDER=` |
| Secrets | `~/.hermes/hindsight/.env.service` | `HINDSIGHT_API_LLM_API_KEY=` (Gemini key) |

## How to Verify a Swap

1. Check AI Studio availability: `curl -s "https://generativelanguage.googleapis.com/v1beta/models/{MODEL}?key={KEY}"`
2. Run the benchmark suite: `python3 /root/.hermes/scripts/model_benchmark.py`
3. For extraction: POST to write-worker with a realistic conversation batch and verify `extracted_facts` has valid JSON shape + expected fact count
4. For consolidation: trigger `systemctl start dream-cycle` and check `/root/.hermes/logs/dream_status.log`
5. Monitor `~/.hermes/logs/errors.log` for 404/400/429 from the new model for 24h

## Known Bugs & Workarounds

### hindsight-api.env double-assignment
File `~/.hermes/hindsight/hindsight-api.env` had `HINDSIGHT_API_DATABASE_URL=HINDSIGHT_API_DATABASE_URL=...` which caused SQLAlchemy `ArgumentError: Could not parse SQLAlchemy URL`. Fix: single assignment.

### Hindsight API provider naming
The hindsight-api package expects `gemini` as provider, NOT `google`. `HINDSIGHT_API_LLM_PROVIDER=google` throws `ValueError: Invalid LLM provider: google`. Always use `gemini`.

### Gemma 4 31B free tier rate limiting
`google/gemma-4-31b-it:free` on OpenRouter returns HTTP 429 consistently. Unusable for production consolidation despite being free.

### Compression provider must match model family
Setting `auxiliary.compression.provider: groq` with `model: gemini-3.1-flash-lite` **silently fails** — Groq does NOT host any Gemini models (only Llama, Qwen, Whisper, GPT-OSS as of May 2026). Symptom: `No auxiliary LLM provider for compression — summaries will be unavailable` in agent.log — middle turns are dropped without summary.

**Fix**: `provider: gemini` (AI Studio) for all Gemini-family models.

**Verification**: `curl -s https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY" | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data']]"`

**General rule**: always verify a provider actually hosts the target model before configuring it. The `provider:` in config.yaml must match the API endpoint, not the model family name.
