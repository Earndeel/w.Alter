# AWS Bedrock Claude Pricing vs Kie.ai (2026-06-10)

## Bedrock Pricing (per million tokens)

| Model | Input | Output | Context | Notes |
|---|---|---|---|---|
| **Claude Fable 5** | $10.00 | $50.00 | 1M | Most expensive Anthropic model |
| **Claude Opus 4.8** | $5.00 | $25.00 | 1M | Latest Opus |
| **Claude Opus 4.7** | $5.00 | $25.00 | 1M | |
| **Claude Opus 4.6** | $5.00 | $25.00 | 1M | US-only inference: +10% |
| **Claude Sonnet 4.6** | $3.00 | $15.00 | 1M | US-only inference: +10% |
| **Claude Haiku 4.5** | $1.00 | $5.00 | 200K | |

## Kie.ai Pricing (per million tokens)

| Model | Input | Output | Ratio vs Bedrock |
|---|---|---|---|
| **Claude Opus 4.8** | $2.00 | $10.00 | **2.5x cheaper** |
| **Claude Opus 4.7** | $1.425 | $7.15 | **3.5x cheaper** |
| **Claude Opus 4.6** | $1.425 | $7.15 | **3.5x cheaper** |

## Bedrock-Exclusive Models (not on Kie/OpenRouter)

- **Claude Fable 5** — $10/$50, creative/specialized
- **Claude Mythos 5** — pricing unknown, biology research
- **Claude Mythos Preview** — pricing unknown

## Routing Decision Matrix

| Scenario | Best Provider | Why |
|---|---|---|
| Daily Opus 4.6/4.7 usage | Kie | 3.5x cheaper |
| Need Opus 4.8 | Kie | 2.5x cheaper |
| Need Fable 5 / Mythos 5 | **Bedrock** | Exclusive access |
| Free credits available ($100) | Bedrock | Free until exhausted |
| Prompt caching (Anthropic native) | Both support | Kie verified: 81% cost reduction |
| Rate limits / availability | Bedrock fallback | AWS scale |

## Bedrock Cache Pricing (if available)

Not confirmed yet. Anthropic's native pricing shows:
- Cache read: 10% of input price
- Cache write (5min): 125% of input price
- Cache write (1h): 200% of input price

Need to verify if Bedrock supports `cache_control` markers.

## Bedrock Credentials

Stored in vault:
- `vault get aws/access_key_id` — AKIA...OVXT
- `vault get aws/secret_access_key` — secret key
- `vault get aws/account_id` — {{bw:W.Alter · aws:field:account_id}}
- `vault get aws/region` — «secret:vault»

CLI usage:
```bash
export AWS_ACCESS_KEY_ID=$(vault get aws/access_key_id)
export AWS_SECRET_ACCESS_KEY=$(vault get aws/secret_access_key)
export AWS_DEFAULT_REGION=«secret:vault»
```

## Pitfalls

- **Bedrock model IDs differ from Anthropic API** — Use `anthropic.claude-opus-4-8-v1:0` format, not `claude-opus-4-8`
- **US-only inference surcharge** — Opus 4.6+, Sonnet 4.6+ have 1.1x multiplier for US-only inference
- **Long context surcharge** — >200K tokens = 2x pricing on applicable models
- **Region availability** — Not all models available in all regions. «secret:vault» has the broadest catalog.
- **No Fable 5 on Kie** — Must use Bedrock for Fable 5
