# Kie.ai Cache Verification Recipe (Opus 4.7 / `/claude` route)

Live verification confirming Anthropic-native prompt caching on Kie.ai's `/claude` endpoint. Done 2026-06-06.

## Recipe — 3 calls to derive exact pricing

Replace `<TOKEN>` with the Kie API key (look it up via the vault skill, never hard-code).

```bash
# TEST 1 — Tiny no-cache baseline
curl -sS -A 'Mozilla/5.0 (compatible; HermesAgent/1.0)' \
  'https://api.kie.ai/claude/v1/messages' \
  -H 'Authorization: Bearer <TOKEN>' -H 'Content-Type: application/json' \
  -d '{"model":"claude-opus-4-7","max_tokens":50,
       "messages":[{"role":"user","content":"Say hi in 5 words"}]}'
# → input_tokens=14, output_tokens=27, credits_consumed=0.04

# TEST 2 — 5k system prompt with cache_control (write)
FILLER=$(python3 -c "print('The quick brown fox jumps over the lazy dog. '*500)")
curl -sS -A 'Mozilla/5.0 (compatible; HermesAgent/1.0)' \
  'https://api.kie.ai/claude/v1/messages' \
  -H 'Authorization: Bearer <TOKEN>' -H 'Content-Type: application/json' \
  -d "{\"model\":\"claude-opus-4-7\",\"max_tokens\":50,
       \"system\":[{\"type\":\"text\",\"text\":\"$FILLER\",
                   \"cache_control\":{\"type\":\"ephemeral\"}}],
       \"messages\":[{\"role\":\"user\",\"content\":\"Say hi\"}]}"
# → ephemeral_5m_input_tokens=5269, credits_consumed=1.92

# TEST 3 — Same prompt within 5min (read)
# Same payload, different user message → cache_read_input_tokens=4353, credits_consumed=0.15
```

## Equations & solved pricing

With standard Anthropic ratios (write=1.25×input, read=0.10×input):

- E1: `14·pi + 27·po = 0.04`
- E2: `10·pi + 5269·1.25·pi + 27·po = 1.92` → `6596.25·pi + 27·po = 1.92`

Resolve: **pi = 285.62 cr/Mtok**, **po = 1333.38 cr/Mtok**.
Verify E3: predicted 0.153 vs observed 0.15 ✓.

At documented $1.425/Mtok input → **1 credit ≈ $0.005**.

## Hermes wiring confirmed

- `agent/agent_runtime_helpers.py:1218-1220` — `anthropic_prompt_cache_policy` returns `(True, True)` for Kie/Claude (third-party Anthropic-compatible gateway branch).
- `run_agent.py:4399-4405` — injects `cache_control: {type: ephemeral}` on last block of system message (single breakpoint — see optimization notes below).
- `agent/transports/anthropic.py:160-169` — extracts `cache_read_input_tokens` + `cache_creation_input_tokens` from response.
- `agent/anthropic_adapter.py:2056-2066` — preserves `cache_control` markers when system content is a list of blocks.

## Observed live (session 20260605_190329_f1f48c)

23 calls on Opus 4.7 via `provider=kie`. From call #3 onward: `cache=N/N (100%)` on every turn. Total session cost 40.12 credits ≈ $0.20 vs $1.07 without cache → **81.3% reduction**.

## Credit balance endpoint

`GET https://api.kie.ai/api/v1/chat/credit` with Bearer auth → `{"code":200,"msg":"success","data":<balance>}`.

No public usage-history endpoint exists — all `/api/v1/chat/usage*`, `/billing/*`, `/records`, `/logs` return 404. Track per-call cost via the `credits_consumed` field in each response.

## Pitfalls

1. **OpenAI-wire routes reject `cache_control`** — Gemini 3.5 Flash, Gemini 3.1 Pro, GPT-5.5 all return 422 if you send Anthropic-style markers. Caching is `/claude` route only.
2. **TTL 1h is real** — response shows `ephemeral_1h_input_tokens` separately from `ephemeral_5m_input_tokens`. Set `{"type":"ephemeral","ttl":"1h"}` for blocks that should survive multi-minute pauses. Costs 2× write but pays off after 2+ reads within the hour.
3. **Volatile blocks invalidate prefix cache** — if Hindsight/timestamp/dynamic content sits inside the cache_control prefix, every change kills the cache. Stratify with multiple breakpoints (up to 4 allowed by Anthropic) ordered stable→volatile.

## Stratified cache optimization (4 breakpoints)

Hermes' `build_system_prompt_parts()` already returns `{stable, context, volatile}` — three natural tiers. The current single-breakpoint injection at `run_agent.py:4404` puts everything into one cache prefix, so any volatile change (Hindsight memory update, timestamp drift, USER.md edit) invalidates the whole chain.

Optimization pattern: split the system content into 3 blocks at the stable/context/volatile boundaries and place a `cache_control` marker on each. Anthropic caches each prefix independently — if volatile changes, stable+context preserves a cache hit. Place TTL `1h` on stable+context (rarely change), default `5m` on volatile.

Expected gain on multi-hour sessions: an additional 15–25% on input cost beyond the existing 81% from single-breakpoint caching.
