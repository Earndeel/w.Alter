# X/Twitter Ecosystem for Agents — Complete Overview

Three distinct tool categories for X. They do NOT overlap in capability.

## 1. x_search (Read-Only, via xAI Grok)

**What it does:** Search X posts, profiles, threads. Grok runs the search server-side and returns synthesized results with citations.

**Prerequisites:** Either SuperGrok OAuth (`hermes auth add xai-oauth`) or `XAI_API_KEY` in `~/.hermes/.env`. When both configured, OAuth wins (consumes subscription quota, not API credits).

**Activation:** `hermes tools` → toggle on `🐦 X (Twitter) Search`. Off by default.

**Config (`~/.hermes/config.yaml`):**
```yaml
x_search:
  model: grok-4.20-reasoning
  timeout_seconds: 180
  retries: 2
```

**Parameters:**
- `query` (required) — search string
- `allowed_x_handles` — whitelist up to 10 handles
- `excluded_x_handles` — blacklist up to 10 handles (mutually exclusive with allowed)
- `from_date` / `to_date` — YYYY-MM-DD date range
- `enable_image_understanding` / `enable_video_understanding` — analyze media on matching posts

**Returns:** `answer` (synthesized text), `citations`, `inline_citations` (with URLs), `credential_source`

**Cost:** $0 extra with SuperGrok subscription. Paid xAI API key otherwise.

**When to use:** Any time the agent needs to READ or SEARCH X. Prefer over web_search for X-specific queries.

## 2. xurl / x-cli (Read + Write, via X API)

**What it does:** Full X API access — post, reply, like, repost, DM, follow, search, media upload.

**Prerequisites:** X Developer account + app credentials. xurl uses OAuth 2.0; x-cli uses 5 API keys.

**Cost:** Pay-per-use credits on console.x.com (see pricing below).

**When to use:** Publishing content, engagement actions, DMs — anything x_search can't do.

## 3. Nitter Scraping (Read-Only, Unofficial) — EFFECTIVELY DEFUNCT

**What it does:** Scrapes X profiles via Nitter mirror instances.

**Prerequisites:** None.

**Cost:** $0.

**When to use:** Almost never, as of May 2026. Nitter mirrors are unreliable — most return login walls or 403. X has progressively blocked scraping. Direct scraping of x.com via tools like Scrapling also fails (requires login). **Use x_search instead** — it's the official read path now.

**If desperate:** Try `mcp_scrapling_get` or `mcp_scrapling_stealthy_fetch` on `https://nitter.net/<handle>`, but expect failure. The Hermes v0.14.0 `x_search` tool (Grok-powered) is the reliable replacement.

---

## X API v2 Pricing (Pay-per-Use, as of May 2026)

No subscriptions. Credit-based. Purchase at console.x.com. Min $5.

### Read Operations (per resource)
| Resource | Cost |
|---|---|
| Posts: Read | $0.005 |
| User: Read | $0.010 |
| DM Event: Read | $0.010 |
| Following/Followers: Read | $0.010 |
| Trend: Read | $0.010 |

### Write Operations (per request)
| Action | Cost |
|---|---|
| Content: Create (post) | $0.015 |
| Content: Create (with URL) | $0.200 |
| DM Interaction: Create | $0.015 |
| User Interaction: Create (like/repost) | $0.015 |
| Interaction: Delete | $0.010 |

### Owned Reads (your own data)
$0.001/resource — 5x cheaper for your own posts, mentions, bookmarks, followers, etc.

### Deduplication
Same resource requested twice in 24h UTC window = charged once.

### xAI Credit Bonus
Buying X API credits earns free xAI API credits:
- $0–$199 cumulative: 0% back
- $200–$499: 10% back
- $500–$999: 15% back
- $1000+: 20% back

---

## Optimal Combo for Cost-Conscious Users

| Need | Tool | Cost |
|---|---|---|
| Search/read X | x_search via Grok | $0 (SuperGrok sub) |
| Publish posts | xurl/x-cli | $0.015/post |
| Publish with links | xurl/x-cli | $0.20/post |
| Like/reply/repost | xurl/x-cli | $0.015/action |

**Minimum viable setup:** SuperGrok subscription (search) + $5 X API credits (publishing). $5 buys ~330 posts or ~25 link-posts.

---

## Frontier Model Pricing Reference (OpenRouter, May 2026)

| Model | Input/M | Output/M |
|---|---|---|
| Claude Opus 4.7 | $5.00 | $25.00 |
| Claude Opus 4.7 (Fast) | $30.00 | $150.00 |
| GPT-5.5 | $5.00 | $30.00 |
| GPT-5.5 Pro | $30.00 | $180.00 |
| GPT-5.4 | $2.50 | $15.00 |
| GPT-5.4 Mini | $0.75 | $4.50 |
| GPT-5.4 Nano | $0.20 | $1.25 |

Query live pricing: `curl -s "https://openrouter.ai/api/v1/models" | python3 -c "import json,sys; [print(f'{m[\"id\"]} | \${float(m[\"pricing\"][\"prompt\"])*1e6:.2f}/M in | \${float(m[\"pricing\"][\"completion\"])*1e6:.2f}/M out') for m in json.load(sys.stdin)['data']]" | grep -i 'opus\|gpt-5'`
