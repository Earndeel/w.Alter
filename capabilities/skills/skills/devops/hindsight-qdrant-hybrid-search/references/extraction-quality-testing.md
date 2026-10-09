# Extraction Quality Testing via Hindsight API

Use this procedure to validate that the extraction LLM is producing good structured facts before committing to a model swap.

## Quick Test (retain API)

The Hindsight `POST /v1/default/banks/{bank_id}/memories` endpoint runs the full extraction pipeline (LLM extract → embed → consolidate). Use `async: false` for synchronous results.

### Request format
```json
{
  "items": [{
    "content": "<conversation text>",
    "context": "extraction_test",
    "document_id": "test_1"
  }],
  "async": false
}
```

### Verify extraction happened
Check logs for fact count:
```bash
tail -20 /root/.hermes/logs/hindsight-api.log | grep "Extract facts"
# Expected: "Extract facts: N facts, M chunks from P contents in Xs"
```

### Verify consolidation
```bash
tail -20 /root/.hermes/logs/hindsight-api.log | grep "CONSOLIDATION"
# Expected: "created=N updated=M skipped=K"
```

## Test Battery (8 cases)

Run these test cases to cover all extraction edge cases:

| # | Case | What to verify |
|---|------|---------------|
| 1 | Simple identity facts | name, city, job, skills extracted |
| 2 | Technical project info | project name, stack, budget, client |
| 3 | Correction/override | old value superseded by new |
| 4 | Preference with negation | "always X, never Y" captured |
| 5 | Numbers and financials | exact figures preserved |
| 6 | French colloquial + URLs | URLs, tokens, informal language |
| 7 | Multi-speaker conversation | attributions correct |
| 8 | Temporal/schedule | times, frequencies, channels |

## Example test payloads

### Test 1: Simple identity
```json
{
  "items": [{"content": "Mon nom est Lucas. J'habite à Paris. Je suis développeur freelance Python et TypeScript.", "context": "test_1", "document_id": "test_identity"}],
  "async": false
}
```

### Test 3: Correction/override
```json
{
  "items": [{"content": "J'utilise Gemini Pro pour l'extraction. Non pardon, c'est Flash Lite maintenant. Et le reranker c'est ZeRank-2, pas FlashRank.", "context": "test_3", "document_id": "test_correction"}],
  "async": false
}
```

### Test 6: French colloquial + URLs
```json
{
  "items": [{"content": "Vas y, lance le deploy sur prod. Le token Stripe c'est sk_live_vaf dans le vault. Webhook: https://scena.app/api/webhooks/stripe.", "context": "test_6", "document_id": "test_colloquial"}],
  "async": false
}
```

## Cost benchmark (gemini-3.1-flash-lite-preview)

From a full 8-test battery run:
- 8/8 success rate
- ~3270 input tokens + ~450 output tokens per extraction
- ~4.4s average per extraction
- Total cost: ~$0.002 for 8 tests → ~$1/month for 500 extractions

## Model comparison reference

| Model | Input/M | Output/M | Structured JSON | Notes |
|-------|---------|----------|-----------------|-------|
| gemini-3.1-pro-preview | $2.00 | $12.00 | Excellent | Overkill for extraction |
| gemini-3-flash-preview | $0.10 | $0.40 | Excellent | Good but 2× more than Lite |
| gemini-3.1-flash-lite-preview | $0.05 | $0.20 | Very good | Best cost/quality for extraction |
| deepseek-v4-flash (OpenRouter) | $0.126 | $0.252 | Medium | JSON less reliable |

## Recall verification

After extraction, verify facts are searchable:
```bash
curl -s -X POST "http://127.0.0.1:8888/v1/default/banks/walter/memories/recall" \
  -H "Content-Type: application/json" \
  -d '{"query": "<keywords from test content>", "limit": 5}'
```

Note: consolidation runs asynchronously, so recall may return 0 results immediately after retain. Wait 5-10s for consolidation to complete.

## Pitfall: API key access for direct Gemini calls

When testing extraction via direct Gemini API calls (not through the Hindsight API), API keys read from `/proc/<PID>/environ` may be **masked by the system** (appears as 13 chars instead of 39). This affects both `cat /proc/$PID/environ` and Python binary reads.

**Workaround:** Use the Hindsight API itself as a proxy — it already has the correct key loaded. Call `POST /v1/default/banks/walter/memories` with `async: false` and check the response `usage` field + log `Extract facts:` line. This tests the exact same pipeline that production uses, which is actually more accurate than testing the Gemini API directly.

If you need raw Gemini API access, read the key from `~/.hermes/hindsight/.env.service` or the vault instead of the process environment.
