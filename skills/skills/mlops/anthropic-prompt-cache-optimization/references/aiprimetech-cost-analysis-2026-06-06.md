# aiprimetech Cost Analysis — 2026-06-06 Session

## Account
- Provider: aiprimetech.io (Gamsgo reseller, One-API/New-API backend)
- Email: earndeel@gmail.com, user ID 3401
- Pricing: $3 buys $25 in tokens (12% of Anthropic direct)
- Rate multiplier: 1.10× (10% markup over Anthropic base)

## Session Data (100 API calls, single day)

| Metric | Value |
|---|---|
| Model | claude-opus-4-7-thinking (100%) |
| Total Billed | $15.86 |
| Original Cost | $14.42 |
| Input Tokens | 4,587 (non-cached) |
| Output Tokens | 27,721 |
| Cache Read | 9,483,362 |
| Cache Creation | 279,983 |
| Cache Hit Rate | 97.1% |
| Avg cost/call | $0.159 |
| Avg output/call | 277 tokens |
| Avg cache read/call | 94,834 tokens |
| Avg cache create/call | 2,800 tokens |
| Avg first token | 4.4s |
| Median first token | 3.7s |
| Avg duration | 21.6s |

## Key Findings

1. **72% of payload is conversation history** (~68K tokens), not system prompt components
2. **Cache hit 97.1%** — excellent, but the sheer volume (95K read/call) means $14/session just for cache reads
3. **Compression never triggered** despite reaching 119K tokens — compressor sees `prompt_tokens=46` (non-cached only) vs threshold 100K
4. **All 100 calls used Opus 4.7-thinking** — no model routing, even for trivial tasks (126 tokens output)
5. **Top expensive calls** ($0.26-$0.41) all show 10-23K cache_creation — volatile content invalidation

## Cost Breakdown

- Cache Read: 9.48M tokens × $0.0015/1K = ~$14.22 (90% of bill)
- Cache Write: 280K tokens × $0.01875/1K = ~$5.25
- Output: 27.7K tokens × $0.075/1K = ~$2.08
- Input (non-cached): negligible

## Optimization Opportunities (ordered by impact)

1. **Model routing** ($4-5/day): Route trivial tasks to Sonnet 4 (5× cheaper output)
2. **Payload reduction** ($3-4/day): Reduce 95K avg to 60K by aggressive conversation compression
3. **Fix compressor bug** ($1-2/day): Compressor sees real total tokens, triggers at 100K
4. **Cache stratification** ($1-2/day): Reduce cache_creation from 2.8K/call to <500

## Dashboard Access

- No public REST API for usage data
- API key `sk-...` is LLM-only, not dashboard auth
- Auth stored in Brave LocalStorage (not cookies) as `auth_user` JSON
- CSV export available from dashboard UI (manual download)
- Balance trackable via LocalStorage `auth_user.balance` field snapshots
