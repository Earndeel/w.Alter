# Kimi K2.6 :free — Real-World Performance (May 2026)

## Model ID
`moonshotai/kimi-k2.6:free` on OpenRouter. Paid variant: `moonshotai/kimi-k2.6`.

## Speed
- Free tier: 41–68 tok/s (variable, depends on upstream congestion)
- Paid tier: 26–84 tok/s (similar range, less 429 jitter)
- Context: 262K tokens
- Pricing: $0/free, $0.73/$3.49 per M tok (paid)

## Rate Limits (Critical)
- **Concurrent**: ~20 requests/min shared across all free users
- **Daily quota**: ~50 requests/day without credits on account
- **With $10 credit**: ~1000 requests/day
- **Upstream provider**: Moonshot (not OpenRouter) — rate limits are provider-side, not aggregator-side
- **Multiple OpenRouter keys do NOT help** — same upstream throttle regardless of key
- **Error**: HTTP 429 with `"temporarily rate-limited upstream"`

## Retry Behavior
- Hermes `api_max_retries: 7` + `jittered_backoff` (base 5s, max 120s) handles transient 429s
- After retries exhaust, Hermes falls back to `fallback_providers` chain
- Recommended fallback chain: mimo-v2.5-pro (GitLawb) → kimi-k2.6:free → mimo (OpenRouter)

## Tested Capabilities
- **Spatial reasoning (cube painting)**: ✅ Correct (8+12+6+1=27), well-structured with LaTeX
- **Grid logic puzzles**: ✅ Correct but tends to over-reason, may hit token limits
- **Code generation**: ✅ Clean Python (asyncio rate limiter with dataclass+deque)
- **Complex multi-constraint reasoning**: ⚠️ Gets lost in analysis, may not produce final answer

## vs Gemini 3.1 Flash Lite (Comparison)
| Metric | Kimi K2.6 :free | Gemini 3.1 Flash Lite |
|--------|----------------|----------------------|
| Speed | 41-68 tok/s | ~instant (2.3s for full response) |
| Rate limits | 429 after 1-2 requests | None observed |
| Spatial reasoning | ✅ Detailed, LaTeX | ✅ Concise, correct |
| Daily quota | ~50 req/day free | Unlimited free |
| Best for | Delegation fallback | Compression, vision, STT, reasoning |

## Recommendation
- **Do NOT use as primary model** — rate limits make it unreliable for production
- **Use as fallback** when primary (mimo/GitLawb) is down
- **Reserve for short tasks** — long reasoning sessions will exhaust daily quota
- **Gemini Flash Lite beats it** for reasoning, speed, and availability at $0 cost
- User preference: **free tier only** — never suggest paid variant
