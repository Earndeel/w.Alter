# GPT-5.6 reasoning field format (2026-07-10, updated 2026-07-12)

## TL;DR

The Kie GPT-5.6 `/codex/v1/responses` endpoint uses the OpenAI **Responses API** format, which requires a **nested** `reasoning` object — NOT the flat `reasoning_effort` field from Chat Completions.

## Working format (nested)

```json
{
  "model": "gpt-5-6-luna",
  "reasoning": {
    "effort": "max"
  },
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "..."}]}]
}
```

✅ HTTP 200, `status=completed`, `reasoning_tokens > 0` (nested under `usage.output_tokens_details`)

Response echoes back:
```json
{
  "reasoning": {
    "mode": "standard",
    "context": "all_turns",
    "effort": "max"
  }
}
```

Accepted effort values (from Kie playground): `low`, `medium`, `high`, `xhigh`, `max`, `ultra`.

## Broken format (flat)

```json
{
  "model": "gpt-5-6-luna",
  "reasoning_effort": "max",
  "input": [{"role": "user", "content": [{"type": "input_text", "text": "..."}]}]
}
```

❌ HTTP 200 but body: `{"code": 500, "msg": "Server exception, please try again later"}`

**Do not use flat `reasoning_effort` with the Responses endpoint.** This format is Chat Completions-native and Kie's Responses endpoint rejects it silently (HTTP 200, error in body).

## Hermes config → payload gap

When `config.yaml` has:
```yaml
model:
  reasoning_effort: max
```

Hermes v0.18.2 does NOT propagate this to the Responses payload. The actual request shows:
```json
"reasoning": {"effort": "medium", "summary": "auto"}
```

The mapping from `reasoning_effort` config key to `reasoning.effort` payload field is broken for `codex_responses` mode.

## User-Agent requirement (Kie Cloudfront)

All requests to `https://api.kie.ai/codex/v1/responses` must include a browser-like `User-Agent` header:

```
User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36
```

Without it, Cloudflare returns `HTTP 403: Your request was blocked`. Hermes v0.18.2 does not inject this header for custom `codex_responses` providers.

## SSE transport (always streaming)

**The `/codex/v1/responses` endpoint always responds with `Content-Type: text/event-stream`**, even when `stream: true` is NOT set in the request. There is no non-streaming JSON response mode.

This means:
- **Never call `response.json()`** — it will fail. The body is SSE, not JSON.
- **Always consume the SSE stream** via `response.iter_lines(decode_unicode=True)`.
- **The final response lives inside the `response.completed` event**, nested under `data.response`. Earlier events are streaming intermediates.

SSE event types observed (full set for a completed call):
`response.created`, `response.in_progress`, `response.output_item.added`, `response.content_part.added`, `response.output_text.delta`, `response.output_text.done`, `response.content_part.done`, `response.output_item.done`, `response.completed`.

### SSE parsing pattern

```python
r = requests.post(BASE, headers=HEADERS, json=payload, timeout=180, stream=True)
completed = None
for line in r.iter_lines(decode_unicode=True):
    if not line or not line.startswith("data: "):
        continue
    data_str = line[6:]
    if data_str in ("[DONE]", "[done]"):
        break
    obj = json.loads(data_str)
    if obj.get("type") == "response.completed":
        completed = obj.get("response", obj)

# Extract: completed["id"], completed["model"], completed["status"],
#          completed["usage"], completed["reasoning"], completed["output"]
```

## Response usage structure

`reasoning_tokens` is **not at `usage.reasoning_tokens`**. It lives under `output_tokens_details`:

```json
"usage": {
    "input_tokens": 0,
    "output_tokens": 4715,
    "total_tokens": 4715,
    "output_tokens_details": {
        "reasoning_tokens": 4134
    }
}
```

- `input_tokens` is reported as `0` (input count not surfaced).
- `total_tokens` equals `output_tokens`.
- Read `usage.output_tokens_details.reasoning_tokens`, never `usage.reasoning_tokens`.

## Response observations (2026-07-12)

- **`credits_consumed` is always `null`** — the endpoint does not return credit info.
- **`reasoning.mode` is always `"standard"`** regardless of effort level.
- **Effort propagates and scales**: `effort=low` → 294 reasoning tokens, `effort=max` → 4134 tokens (14.1×) on the same Fermi problem. Both echo their requested effort correctly.
- **Reasoning is visible in `output[]`**: `low` gives 1 reasoning + 1 message; `max` gives 8 reasoning items interleaved with 2 messages.
