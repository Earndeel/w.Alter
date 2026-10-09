# Cost Tracking

MiroShark shares the same OpenRouter key as Hermes. Costs are mixed.

## Estimate per simulation phase
| Phase | Model | Calls | Est. cost |
|-------|-------|-------|-----------|
| suggest-scenarios | grok-4.3 | 1 | $0.001 |
| ask (briefing) | grok-4.3 | 1 | $0.001 |
| ontology/generate | grok-4.3 | 1 | $0.002 |
| graph/build | (Neo4j only) | 0 LLM | $0 |
| prepare (profiles) | mimo-v2-flash | 4 | $0.002 |
| prepare (embeddings) | text-embedding-3-large | 4 | $0.001 |
| simulation/run (72 rounds) | mimo-v2-flash | ~200-400 | $0.50-1.00 |
| **Total** | | | **~$0.50-1.00** |

## Check remaining balance
Get the OpenRouter key from vault (`vault get openrouter/api_key`) and check credits at `https://openrouter.ai/api/v1/credits`.

## Count MiroShark LLM calls from logs
```bash
grep "Calling LLM" /root/MiroShark/backend/logs/*.log | wc -l
```

## Pitfall
Do NOT report total OpenRouter usage as "MiroShark cost" — the key is shared with Hermes. Always check MiroShark-specific logs or estimate from call count × model pricing.

## Model deprecation notes
Smart/NER models (e.g. `x-ai/grok-4.1-fast`) get deprecated without notice on OpenRouter. Update `SMART_MODEL_NAME`, `NER_MODEL_NAME`, `WEB_SEARCH_MODEL` in `/root/MiroShark/.env` and restart backend. As of May 2026: `x-ai/grok-4.1-fast` → `x-ai/grok-4.3`.
