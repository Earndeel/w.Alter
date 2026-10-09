# OpenRouter Free Models API

## Endpoint
```
GET https://openrouter.ai/api/v1/models
```
No auth required. No rate-limit for reads.

## Filtering for free models
Filter response `data[]` where `id` contains `:free` AND `pricing.prompt == "0"` AND `pricing.completion == "0"`.

## Response structure (per model)
```json
{
  "id": "deepseek/deepseek-v4-flash:free",
  "name": "DeepSeek: DeepSeek V4 Flash (free)",
  "context_length": 1048576,
  "pricing": {
    "prompt": "0",
    "completion": "0",
    "image": "0",
    "request": "0"
  }
}
```

## ⚠️ Scores AA — privilégier l'API live

Les scores AA listés ci-dessous sont un **snapshot ponctuel** (Mai 2026) et peuvent être périmés. Pour les scores à jour, utiliser l'API live :

```bash
AA_KEY=$(vault get artificial-analysis/api_key)
for page in 1 2 3; do
  curl -s "https://artificialanalysis.ai/api/language/models/free?page=$page&pageSize=200" \
    -H "x-api-key: $AA_KEY" > /tmp/aa_page${page}.json
  python3 -c "import json; data=[json.load(open(f'/tmp/aa_page{p}.json')) for p in range(1,$page+1)]; items=[m for d in data for m in d.get('items',[])]; [print(f'{m[\"slug\"]:40s} AA={m[\"qualityMetrics\"][\"artificialAnalysisIntelligenceIndex\"]:5.1f}  {m[\"creator\"][\"name\"]}') for m in sorted(items, key=lambda x: x['qualityMetrics']['artificialAnalysisIntelligenceIndex'], reverse=True) if m['qualityMetrics']['artificialAnalysisIntelligenceIndex'] >= 35]"
done
```

Voir `references/aa-free-api-integration.md` pour la procédure détaillée.

## Known free models (as of May 2026, ~25 total)

### Tier 1 (AA >= 46) — report these
| Model ID | Name | AA Score | Context | Speed | Rate Limits |
|----------|------|----------|---------|-------|-------------|
| moonshotai/kimi-k2.6:free | Kimi K2.6 | 54 | 262k | ~68 tok/s | 20 req/min, ~50 req/day (no credits), ~1000/day ($10) |
| deepseek/deepseek-v4-flash:free | DeepSeek V4 Flash | 47 | 1M | — | shared pool w/ other :free models |
| qwen/qwen3-coder:free | Qwen3 Coder 480B A35B | ~45 | 262k | — | — |
| openai/gpt-oss-120b:free | GPT-OSS 120B | ~45 | 131k | — | — |

**Kimi K2.6 :free specifics (tested May 2026):**
- Fastest free model on OpenRouter (~68 tok/s free tier, ~48 tok/s paid)
- Rate limits are UPSTREAM from Moonshot, not OpenRouter — multiple API keys won't help
- 429 error: `"temporarily rate-limited upstream"` — retryable with backoff
- Daily quota (~50 req/day) is NOT retryable — needs fallback to paid model
- Paid variant `moonshotai/kimi-k2.6` = $0.73/M input, $3.49/M output (still very cheap)
- Works well as Hermes delegation model with mimo-v2.5-pro as fallback_provider

### Tier 2 (AA 35-45) — borderline, currently excluded at threshold 46
| Model ID | Name | AA Score | Context |
|----------|------|----------|---------|
| google/gemma-4-31b-it:free | Gemma 4 31B | 39 | 262k |
| minimax/minimax-m2.5:free | MiniMax M2.5 | ~38 | 197k |
| qwen/qwen3-next-80b-a3b-instruct:free | Qwen3 Next 80B | ~37 | 262k |
| z-ai/glm-4.5-air:free | GLM 4.5 Air | ~36 | 131k |
| meta-llama/llama-3.3-70b-instruct:free | Llama 3.3 70B | ~36 | 66k |

### Tier 3 (AA < 35) — exclude
Nemotron variants (~15-22), LFM 1.2B (~8-10), Llama 3.2 3B (~10), Poolside Laguna (~15-30), Dolphin Mistral (~20), Hermes 3 405B (~25, old), Ring 2.6 (~28), Baidu CoBuddy (~28), GPT-OSS 20B (~20).

## Provider link format
```
https://openrouter.ai/{model-id-without-:free}
```
Example: `https://openrouter.ai/deepseek/deepseek-v4-flash`
