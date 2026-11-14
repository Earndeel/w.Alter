# Grok 4.6 cache investigation in Hermes — 2026-08-15

## Verified runtime path

Hermes Desktop routed Grok 4.6 through:

- provider: `custom` (configured presentation provider `kie`)
- base URL: `https://api.kie.ai/grok/v1`
- wire mode: `codex_responses`
- HTTP path: `POST https://api.kie.ai/grok/v1/responses`
- session evidence: `state.db`, session `20260815_123801_f9819a`

A stale route to `/grok/responses` produced HTTP 404 (`No message available`). The OpenAI SDK appends `/responses`; the base URL must include `/v1`.

## Cache evidence

The session log reported these six Kie calls:

| Call | Input | Cached read | Hit ratio |
|---:|---:|---:|---:|
| 1 | 33,435 | 128 | 0.38% |
| 2 | 34,793 | 33,408 | 96.02% |
| 3 | 53,522 | 34,688 | 64.81% |
| 4 | 59,794 | 128 | 0.21% |
| 5 | 68,636 | 128 | 0.19% |
| 6 | 77,259 | 68,608 | 88.80% |
| **aggregate** | **327,439** | **137,088** | **41.87%** |

The persisted session row summed the same session at `input_tokens=190351`, `cache_read_tokens=137088`, giving a session-level read ratio of 72.02% (the log aggregation includes the six request-level input totals; the DB aggregate reflects the completed/persisted accounting path and should be reported separately).

## Interpretation

The cache is not globally broken. It warms when the static prefix remains stable and drops when the prefix changes. In the observed turn, dynamic tool/skill discovery changed the tool schema and/or instructions, producing new content-addressed cache keys. The transport computes the key from `scope_id + instructions + sorted tool schemas` and sends it to Kie Grok as `extra_body.prompt_cache_key`; it also sends `x-grok-conv-id` for backend stickiness.

The request dump from the early failed attempt showed the intended cache fields:

```json
{
  "extra_headers": {"x-grok-conv-id": "20260815_123135_44945e"},
  "extra_body": {"prompt_cache_key": "pck_6d7bf087a882c7a98f162a46"}
}
```

The successful Hermes session had cached reads of 96%, 65%, 89% on warm calls, and 0% on calls after static-prefix/tool changes. This is expected behavior for prefix caching, not proof of a broken cache.

## Important limits

- Kie-side internal cache logs were not available from the local Hermes host; evidence is Hermes request dumps, `agent.log`, and `state.db`.
- `cache_write_tokens=0` does not prove no cache write occurred. The Kie Responses usage shape exposes `input_tokens_details.cached_tokens` on responses, while write accounting is absent/opaque.
- The direct Kie protocol fixture independently showed `cached_tokens=128` on the first request and `192` on the second, confirming Kie returns cache-read metadata on the verified Responses route.
- The Kie tool probe used a tiny stable prompt, not the full Desktop tool payload; do not compare its absolute cache counts directly with Desktop.

## Diagnostic recipe

1. Confirm request URL ends in `/grok/v1/responses`.
2. Confirm the request body uses Responses fields (`input`, `instructions`, not `messages`).
3. Confirm `extra_body.prompt_cache_key` is stable across two calls with an unchanged static prefix.
4. Confirm `extra_headers.x-grok-conv-id` is stable for the logical conversation.
5. Compare per-call `cache_read_tokens / input_tokens` rather than only the session total.
6. Correlate every cache drop with tool discovery, skill loading, context compaction, or another static-prefix change.
7. Treat missing `cache_write_tokens` as unknown, not zero.

## Known unrelated cost issue

The same Desktop session logged an auxiliary title-generation call via OpenRouter. This is separate from Kie Grok cache behavior and should not be attributed to Kie.
