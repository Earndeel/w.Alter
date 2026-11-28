# Chinese API Relay Services — Frontier Model Access

## Categories

### 1. Legitimate Relay/Proxy
Forward requests to official APIs. Charge a **multiplier** on official pricing (1.1x–1.5x).
- **Use case:** Access from China where OpenAI/Anthropic is blocked
- **Not cheaper** than official API — more expensive, but accessible
- **Examples:** CloseAI-Asia (closeai-asia.com)
  - Business tier: 1.5x official price, 5% cashback
  - Dev tier: 1.25x (after ¥5000 cumulative)
  - Enterprise: 1.1x (after ¥10,000 cumulative)
- **Risk:** Low — legitimate businesses with invoicing support

### 2. Account Pooling / Grey Market
Operators buy enterprise accounts in bulk, resell access via OpenAI-compatible API.
- **Use case:** 50–80% cheaper than official API for Claude/GPT
- **How:** Shared enterprise accounts, bulk pricing passed to users
- **Risk:** Medium — rate limits shared across all users, accounts can be revoked, no data privacy guarantee, service can disappear overnight
- **Where to find:** Chinese tech forums (V2EX, 掘金), WeChat groups, Telegram channels

### 3. Stolen/Unauthorized Keys
Access via compromised API keys.
- **Use case:** Extremely cheap but unreliable
- **Risk:** High — keys get revoked, potential legal issues, no recourse

## Legitimate Chinese Providers (Open-Source Models)

These are safe and cost-effective for **open-source** models (DeepSeek, Qwen, Llama, etc.):

| Provider | URL | Notes |
|---|---|---|
| **SiliconFlow** (硅基流动) | siliconflow.cn / siliconflow.com (intl) | Beijing-based, legit, covers LLMs + image + video + speech |
| **01.AI** (零一万物) | lingyiwanwu.com | Yi model family |
| **DeepSeek** | platform.deepseek.com | Direct from the source |
| **Moonshot (Kimi)** | platform.moonshot.cn | Kimi models |

**Important:** These providers typically do NOT resell Claude or GPT. They host open-source models. The "cheap Claude Opus" providers are category 1 or 2.

## Current Frontier Model Pricing (Official, May 2026)

For comparison when evaluating relay offers:

| Model | Input/M | Output/M |
|---|---|---|
| Claude Opus 4.7 | $5.00 | $25.00 |
| GPT-5.5 | $5.00 | $30.00 |
| GPT-5.5 Pro | $30.00 | $180.00 |

If a relay offers Claude Opus at <$2/M input, it's likely category 2 or 3.

## Decision Framework

- **Need reliability + data privacy** → Official API or OpenRouter
- **Need cheap access to open-source models** → SiliconFlow, DeepSeek direct
- **Need cheap Claude/GPT, accept risk** → Grey market pools (category 2)
- **Accessing from China** → Legitimate relays (category 1) at 1.1x–1.5x markup
