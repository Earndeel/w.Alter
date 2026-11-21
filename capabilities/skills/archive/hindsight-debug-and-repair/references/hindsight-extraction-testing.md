# Testing Hindsight Extraction via API

## Method: Use Hindsight's own API (not direct Gemini API)

When testing extraction quality, call the Hindsight retain API instead of trying to use the Gemini API directly (which requires unmasked keys that are hard to extract from running processes).

```bash
# Correct: use Hindsight API (already has the key loaded)
curl -s -X POST "http://127.0.0.1:8888/v1/default/banks/walter/memories" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [{
      "content": "conversation text here",
      "context": "test_label",
      "document_id": "test_1"
    }],
    "async": false
  }'
```

## Checking extraction results

1. Check logs: `tail -50 ~/.hermes/logs/hindsight-api.log | grep 'Extract facts'`
2. Check stats: `curl -s http://127.0.0.1:8888/v1/default/banks/walter/stats`
3. Recall: `curl -s -X POST "http://127.0.0.1:8888/v1/default/banks/walter/memories/recall" -H "Content-Type: application/json" -d '{"query": "search term", "limit": 5}'`

## Key metrics to capture

- `Extract facts: N facts, M chunks from P contents in X.XXXs`
- Token usage: `input_tokens` + `output_tokens` in response
- Cost calculation: `(input * price_input + output * price_output) / 1_000_000`

## Pitfall: API key extraction

The Gemini API key in the Hindsight process environment is masked when read externally. Do NOT try to extract it from `/proc/<pid>/environ` — use the Hindsight API instead.
