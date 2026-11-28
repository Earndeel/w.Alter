---
name: smm-panel-integration
description: "SMM panel API integration — order followers/views/likes, track status, manage balance. Covers SMMFlare and standard SMM panel v2 API pattern."
triggers:
  - "smm panel"
  - "buy followers"
  - "buy views"
  - "boost video"
  - "smmflare"
  - "social media panel"
  - "reseller panel"
---

# SMM Panel Integration

SMM (Social Media Marketing) panels are platforms that sell social engagement services — followers, likes, views, comments — across multiple platforms (TikTok, Instagram, YouTube, etc.). They expose REST APIs (typically v2) for programmatic ordering.

## When to Use

- User wants to boost a video/post with views, likes, or followers
- User mentions an SMM panel by name (SMMFlare, SMM Heaven, JustAnotherPanel, etc.)
- User wants to automate social media promotion campaigns

## Standard SMM Panel v2 API Pattern

Most SMM panels (hosted on platforms like PerfectPanel/SmartPanel) share an identical API shape:

| Endpoint | Action | Description |
|----------|--------|-------------|
| POST /api/v2 | `services` | List available services with IDs, prices, min/max |
| POST /api/v2 | `add` | Place an order |
| POST /api/v2 | `status` | Check order status (single or batch up to 100) |
| POST /api/v2 | `balance` | Check account balance |
| POST /api/v2 | `refill` | Request a refill on dropped engagement |
| POST /api/v2 | `refill_status` | Check refill status |
| POST /api/v2 | `cancel` | Cancel orders |

Auth: API key passed as `key` parameter in POST body.

## Workflow: Boosting Content

1. **Get API key** — user retrieves from their panel account settings
2. **List services** — filter for target platform (TikTok, IG, etc.) and service type (views, likes, followers)
3. **Check balance** — ensure sufficient credits before ordering
4. **Place order** — `action=add`, `service=<ID>`, `link=<URL>`, `quantity=<N>`
5. **Track status** — poll with `action=status&order=<ID>` until completed

## Service Types

| Type | Name | Extra Params |
|------|------|-------------|
| 0 | Default | `link`, `quantity` |
| 1 | SEO | `link`, `quantity`, `keywords` |
| 2 | Custom Comments | `link`, `comments` (newline-separated) |
| 9 | Mentions | `link`, `quantity`, `usernames` |
| 10 | Package | `link` only (fixed quantity) |
| 100 | Subscription | `username`, `min`, `max`, `delay`, `posts` |
| 102 | Web Traffic | `link`, `quantity`, `country`, `device`, `type_of_traffic` |

## Pitfalls

- **Low quality engagement** — SMM panel followers/views are typically bots. Good for social proof, bad for real engagement. Be honest with user about this.
- **No credits = no API** — user must top up balance via the panel's website before API calls work.
- **Service IDs vary by panel** — always call `services` first to get current IDs; never hardcode.
- **Rate/delivery time varies** — some services deliver instantly, others take hours/days. Check `status` periodically.
- **Refill guarantees** — not all services support refill. Check `refill: true` in service listing before promising.

## Creating an MCP Wrapper

When user wants persistent integration, create an MCP server that wraps the panel API:
- Endpoint discovery via `services` action
- Order placement with validation (min/max from service listing)
- Status polling with configurable intervals
- Balance checking before order placement

See `references/smmflare-api.md` for the complete SMMFlare v2 API reference.

## Known Panels

| Panel | URL | API Endpoint |
|-------|-----|-------------|
| SMMFlare | smmflare.com | /api/v2 |
| (add more as discovered) | | |
