---
name: smm-panel-api
description: "Integrate with SMM panel APIs (SMMFlare and similar) — service listing, order placement, status tracking, balance checks. Standard POST-based API pattern shared across most SMM panels."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [smm, social-media, api, tiktok, instagram, youtube, panel]
---

# SMM Panel API Integration

SMM (Social Media Marketing) panels are platforms that sell social media engagement — followers, likes, views, comments — via a REST API. Most panels share the same API structure (originally from the SMM panel PHP script ecosystem).

## Standard API Pattern

**Endpoint:** `POST https://<panel-domain>/api/v2`
**Auth:** API key passed as `key` parameter in every request
**Format:** `application/x-www-form-urlencoded`
**Response:** JSON

### Core Actions

| Action | Parameters | Response |
|--------|-----------|----------|
| `services` | `key`, `action=services` | Array of service objects |
| `add` | `key`, `action=add`, `service`, `link`, `quantity` (+ type-specific params) | `{"order": 12345}` |
| `status` | `key`, `action=status`, `order` | `{"charge", "start_count", "status", "remains", "currency"}` |
| `balance` | `key`, `action=balance` | `{"balance": "100.00", "currency": "USD"}` |
| `refill` | `key`, `action=refill`, `order` | `{"refill": "1"}` |
| `refill_status` | `key`, `action=refill_status`, `refill` | `{"status": "Completed"}` |
| `cancel` | `key`, `action=cancel`, `orders` (comma-separated) | Array of results |

### Order Types (for `add` action)

| Type | Use case | Extra params |
|------|----------|-------------|
| Default (0) | Followers, likes, views | `quantity` |
| Package (10) | Fixed packages | none (just `link`) |
| Custom Comments (2) | Custom text comments | `comments` (newline-separated) |
| Mentions (9) | Mention users | `quantity`, `usernames` |
| Subscriptions (100) | Auto-like new posts | `username`, `min`, `max`, `delay` |
| SEO (1) | SEO services | `quantity`, `keywords` |
| Web Traffic (102) | Website traffic | `quantity`, `country`, `device`, `type_of_traffic` |

### Service Object Shape

```json
{
    "service": 9556,
    "name": "TikTok Video Views [Instant]",
    "type": "Default",
    "category": "New Services",
    "rate": "0.17",        // price per 1000
    "min": "100",
    "max": "100000",
    "refill": true,
    "cancel": true
}
```

### Order Status Values

- `Pending` — order queued
- `In progress` — delivery started
- `Completed` — fully delivered
- `Partial` — partially delivered (check `remains`)
- `Processing` — being processed
- `Canceled` — cancelled
- `Refunded` — money returned

## Known Panels

### SMMFlare
- **URL:** `https://smmflare.com/api/v2`
- **Account page:** `https://smmflare.com/account`
- **API docs:** `https://smmflare.com/api`
- **Credentials:** vault `smmflare/api_key`
- **Pricing:** Views $0.01-0.17/1K, Likes $0.29-0.59/1K, Followers $2.40-3.99/1K
- **User:** Earndeel (lucas.jouvencon@gmail.com), account ID 61340

## MCP Wrapper Integration

When user wants persistent integration, create an MCP server that wraps the panel API:
- Endpoint discovery via `services` action
- Order placement with validation (min/max from service listing)
- Status polling with configurable intervals
- Balance checking before order placement

## Pitfalls

- **Low quality engagement** — SMM panel followers/views are typically bots. Good for social proof, bad for real engagement. Be honest with user about this.
- **No credits = no orders.** Check `balance` before attempting `add`. Most panels require pre-funded accounts (crypto, card, PayPal).
- **Bulk status:** `status` action accepts `orders` (comma-separated, up to 100 IDs) for batch queries.
- **Service IDs change.** Always call `services` to get current IDs; never hardcode service IDs from old sessions.
- **Rate is per 1000.** To calculate cost: `quantity * rate / 1000`.
- **Drip-feed:** Use `runs` and `interval` params on `add` to spread delivery over time (e.g., 10 runs × 1000 views every 30 minutes).
- **Session cookies for account page.** The API key is generated on the account page. If you need to generate one programmatically, you need valid session cookies — see `references/brave-cookie-extraction.md` and `references/mac-browser-pitfalls.md`.

## Workflow: Boost a Video

```bash
# 1. Check balance
curl -s -X POST "https://smmflare.com/api/v2" -d "key=API_KEY&action=balance"

# 2. List TikTok services
curl -s -X POST "https://smmflare.com/api/v2" -d "key=API_KEY&action=services" | \
  python3 -c "import json,sys; [print(f'{s[\"service\"]}: {s[\"name\"]} - \${s[\"rate\"]}/1K') for s in json.load(sys.stdin) if 'tiktok' in s.get('category','').lower()]"

# 3. Place order
curl -s -X POST "https://smmflare.com/api/v2" -d "key=API_KEY&action=add&service=9556&link=https://www.tiktok.com/@user/video/123&quantity=10000"

# 4. Check status
curl -s -X POST "https://smmflare.com/api/v2" -d "key=API_KEY&action=status&order=ORDER_ID"
```
