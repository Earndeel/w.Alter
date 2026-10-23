# Measurement Recipe — Anthropic Prompt Cache

Derive exact per-token pricing and verify cache behaviour on any Anthropic-compatible endpoint with a 3-call sequence. Replace `<TOKEN>` with the provider API key (look it up via the vault skill, never hard-code).

## The 3-call probe

```bash
ENDPOINT='https://api.kie.ai/claude/v1/messages'   # or api.anthropic.com/v1/messages, etc.
MODEL='claude-opus-4-7'

# CALL 1 — Tiny no-cache baseline. Establishes per-token input+output rate.
curl -sS -A 'Mozilla/5.0 (compatible; HermesAgent/1.0)' "$ENDPOINT" \
  -H 'Authorization: Bearer ***' -H 'Content-Type: application/json' \
  -d '{"model":"'"$MODEL"'","max_tokens":50,
       "messages":[{"role":"user","content":"Say hi in 5 words"}]}'
# Expect: usage.input_tokens small, output_tokens small, cache_* = 0

# CALL 2 — 5k system prompt with cache_control (forces a WRITE)
FILLER=$(python3 -c "print('The quick brown fox jumps over the lazy dog. '*500)")
curl -sS -A 'Mozilla/5.0 (compatible; HermesAgent/1.0)' "$ENDPOINT" \
  -H 'Authorization: Bearer ***' -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"max_tokens\":50,
       \"system\":[{\"type\":\"text\",\"text\":\"$FILLER\",
                   \"cache_control\":{\"type\":\"ephemeral\"}}],
       \"messages\":[{\"role\":\"user\",\"content\":\"Say hi\"}]}"
# Expect: ephemeral_5m_input_tokens > 0, cache_read_input_tokens = 0

# CALL 3 — Same system within 5 min, different user message (forces a READ)
# Re-run CALL 2 with a different user message ('Say bye' etc.).
# Expect: cache_read_input_tokens > 0, ephemeral_5m_input_tokens = 0
```

## Pricing extraction (provider-credit math)

Observed data (Kie.ai Opus 4.7, 2026-06-06):

| Call | input | cache_write | cache_read | output | credits |
|---|---|---|---|---|---|
| 1 | 14 | 0 | 0 | 27 | 0.04 |
| 2 | 10 | 5269 | 0 | 27 | 1.92 |
| 3 | 10 | 0 | 4353 | 19 | 0.15 |

Assuming standard Anthropic ratios (write = 1.25× input, read = 0.10× input), the system is solvable:

- E1: `14·pi + 27·po = 0.04`
- E2: `10·pi + 5269·1.25·pi + 27·po = 1.92`  →  `6596.25·pi + 27·po = 1.92`
- Subtract: `6582.25·pi = 1.88`  →  **pi = 285.62 cr/Mtok**
- Back-substitute: **po = 1333.38 cr/Mtok**
- Verify E3: predicted `10·pi + 4353·0.1·pi + 19·po = 0.153` vs observed 0.15 ✓

If the providers' real ratios deviate from standard, the verify step will mismatch — that's the signal to re-derive without the ratio assumption (need a 4th call varying only output to separate `po`).

## TTL 1h verification

Repeat CALL 2 with `{"type":"ephemeral","ttl":"1h"}`. Expected:

- `usage.cache_creation.ephemeral_1h_input_tokens > 0`
- `usage.cache_creation.ephemeral_5m_input_tokens == 0`
- `credits_consumed` ≈ 2× the 5m write cost

If the provider doesn't honour `ttl`, the field silently routes to `ephemeral_5m_input_tokens` instead. That's the signal that the provider's claim of 1h support is broken.

## In-Hermes verification (no external probe)

```bash
grep -E 'API call #.*cache=' ~/.hermes/logs/agent.log | tail -20
```

Healthy multi-turn session on Claude:

```
API call #1: ... cache=0/N           # write (no prior cache)
API call #2: ... cache=N/N (100%)    # full hit
API call #3: ... cache=N/N (100%)    # still hit
```

Unhealthy patterns:

- `cache=0/N` on every call → caching disabled or markers stripped. Check `anthropic_prompt_cache_policy` returns `(True, ...)` for this provider.
- `cache=K/N (50%)` fluctuating → volatile content inside the cached prefix is invalidating part of it. Stratify with multiple breakpoints.
- `cache=N/N (100%)` then drops to `0/N` after a quiet period → TTL expired. Switch to TTL 1h if pauses are common.

## Quick cost ceiling estimate

For a session with `T` turns averaging `S` input tokens, with 100% cache hit from turn 2 onward:

- Cost ≈ `S · pi · 1.25  +  (T-1) · S · pi · 0.10  +  total_output · po`
- Compared to no-cache: `T · S · pi  +  total_output · po`
- Savings on input: `1 - (1.25 + 0.10·(T-1)) / T`
  - T=10: 78.75% saved
  - T=20: 84.4% saved
  - T=50: 87.5% saved (asymptote ≈ 90%)

Observed on real session of 23 turns: 81.3% — matches expectations.
