---
name: scena-portal-authenticated-debugging
description: Debug authenticated Scena portal identity and Telegram state.
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    category: devops
    tags: [scena, portal, auth, telegram, cloudflare, d1, frontend]
    related_skills: [scena-full-checkup, cloudflare-pages-deploy]
---

# Scena Portal Authenticated Debugging Skill

Use this skill to diagnose and verify Scena's authenticated portal surfaces, account-to-client identity mapping, and Telegram bot status. It covers source tracing, live contract checks, tenant-scoped D1 inspection, and production visual verification; it does not expose credentials or silently mutate production.

## When to Use

- The Scena dashboard shows a signed-in user as disconnected from Telegram.
- Telegram tests work but the dashboard says the bot is not connected.
- Login, dashboard, or Studio renders with inconsistent themes, invisible text, or stale CSS.
- A portal API call appears successful in the browser but the UI remains at its default state.
- A production portal change needs a cache-safe deployment and live verification.

## Prerequisites

- Scena checkout, normally `/root/projects/scena-cloudflare`.
- Portal source under `pages/portal/` and Worker source under `workers/api/src/`.
- Cloudflare credentials available through the configured secret source; never print token values.
- For D1 inspection, a token with D1 read permission. Pages-only tokens are insufficient.
- Use `search_files` and `read_file` to trace the actual route and call sites before editing.
- Keep bot tokens, session cookies, API keys, and raw D1 secrets out of tool output and reports.

## How to Run

1. Locate the browser call and the Worker route:
   ```text
   search_files(pattern="api/client/bot|telegram_bot_token|webhook/telegram", path="pages/portal|workers/api/src")
   ```
2. Read the relevant HTML and Worker sections with `read_file`.
3. Verify the live API and Pages domain with `terminal`, using a real `User-Agent` and an authenticated browser session when required.
4. Inspect D1 read-only with a query that returns booleans, usernames, IDs, and matricules only; never select token values.
5. If a code fix is requested, patch the smallest contract surface, run targeted tests, then perform an authenticated E2E check.
6. For production UI changes, obtain explicit deployment approval, cache-bust changed assets, deploy the exact Pages project, and verify both the unique deployment URL and the custom domain.

## Quick Reference

| Concern | Source of truth | Safe observable |
|---|---|---|
| Portal session | `scena_session` cookie and `/api/auth/get-session` | user ID, email, HTTP status |
| Dashboard client | `clients.user_id`, fallback `clients.email` | client ID, matricule, name, status |
| Client Telegram association | `clients.telegram_bot_token` and username | configured boolean, username |
| Telegram webhook routing | `/webhook/telegram/{matricule}` | webhook URL, chat ID, delivery status |
| Worker global bot | `env.TELEGRAM_BOT_TOKEN` | configured boolean only |
| Portal bot UI | `GET /api/client/bot` response | `{configured, bot_name}` or equivalent |

## Procedure

### 1. Trace the portal contract

Read the dashboard's `loadBotStatus`, connect, and disconnect functions. Confirm:

- The HTTP method and path exist in the Worker.
- The request field names match exactly on both sides.
- The response shape matches what the browser reads.
- Errors are not swallowed while the UI silently keeps its initial state.
- Browser responses never contain `telegram_bot_token`.

The known Scena contract is:

- The dashboard status call is `GET /api/client/bot`.
- The connect call is `POST /api/client/bot` with `{bot_token}`.
- The Worker validates the token with Telegram `getMe`, sets the tenant webhook, and stores the token plus username on the client row.

If the UI sends `{telegram_bot_token}` while the Worker reads `body.bot_token`, the save flow returns `400 Token required`. If the Worker only implements POST while the UI calls GET, the status remains “Non connecté” even when the client row is configured.

### 2. Separate global Telegram state from tenant state

Do not infer dashboard association from the fact that a bot answers in Telegram. Scena has two distinct concepts:

- `env.TELEGRAM_BOT_TOKEN`: a Worker-level secret used by global flows such as Telegram Mini App validation or operations.
- `clients.telegram_bot_token`: the bot assigned to one Scena client/matricule and used by the multi-tenant webhook handler.

A bot can work through a global or legacy path while the authenticated user's client row is empty. Conversely, a configured client row can exist while the dashboard status endpoint is broken.

### 3. Verify user-to-client resolution

The Worker resolves the authenticated user first by `clients.user_id`. If absent, it falls back to the signed-in user's email and attaches the matching active client row. Check for:

- Duplicate active clients with the same email.
- A row assigned to a different `user_id`.
- Archived rows hiding the intended association.
- A Telegram-created user with no email and a separate Google-authenticated user.
- A bot stored under another matricule.

Use a redacted D1 query such as:

```sql
SELECT
  u.id AS user_id,
  u.email,
  c.id AS client_id,
  c.matricule,
  c.user_id AS client_user_id,
  c.telegram_bot_username,
  CASE WHEN COALESCE(c.telegram_bot_token, '') = '' THEN 0 ELSE 1 END AS telegram_bot_configured,
  c.telegram_chat_id,
  c.status
FROM users u
LEFT JOIN clients c
  ON c.user_id = u.id OR lower(c.email) = lower(u.email)
WHERE lower(u.email) = lower(?);
```

Never include the token column in output. If D1 access fails, say that the row state is unverified; do not replace it with assumptions based on Telegram activity.

### 4. Verify webhook routing

The webhook route is `/webhook/telegram/{matricule}`. It loads the active client by matricule and returns without processing if that client has no `telegram_bot_token`. Once a real update arrives, it writes `telegram_chat_id` for that matricule.

Use `getWebhookInfo` only with the token kept inside a process environment or secret store. Report only the webhook URL, pending update count, last error text if non-sensitive, and bot username.

### 5. Debug authenticated browser behavior

Use Playwright or the browser tools with an actual session when available. Record:

- Final URL and HTTP status.
- Response status for `/api/auth/get-session`, `/api/client/me`, `/api/client/bot`.
- Console/page errors.
- `document.documentElement.scrollWidth` versus `clientWidth` at desktop and mobile widths.
- Computed text/background colors and border radii for affected controls.

Do not use an unauthenticated `{}` mock to claim the real account is configured. API mocks are acceptable only for isolating static rendering from authentication, and must be labeled as such.

### 6. Debug authenticated surface styling

The shared landing stylesheet must not overwrite dark/authenticated tokens accidentally. Scope authenticated overrides to `body.auth-page`, `body.dashboard-page`, and `body.studio-page`; keep the DOM IDs and JavaScript behavior unchanged.

For a production CSS change:

- Add a cache-busting query to changed stylesheet references or change the asset filename.
- Run the targeted contract tests and a responsive Playwright pass.
- Capture desktop and mobile renders for visual review before production.
- Deploy `scena-portal`, not a similarly named Pages project.
- Verify the unique deployment hash URL first, then `https://scena.walter-ai.cloud`.

## Pitfalls

- A dashboard label can be a stale initial DOM value, not live evidence.
- A missing GET route and a mismatched POST field can coexist; fixing only one leaves the flow broken.
- `telegram_chat_id` proves that a webhook update reached a client route; it does not prove that the Google account is the same tenant.
- Do not expose or paste bot tokens into chat, screenshots, logs, D1 output, or browser console.
- Do not query or modify D1 remotely unless the user requested the relevant operation and the scope is explicit.
- Do not deploy frontend changes to production without explicit approval and live verification.
- Cloudflare Pages cache can hide a correct deployment; use a versioned asset URL and verify the hash deployment.

## Verification

A diagnosis is complete only when all applicable checks are grounded:

- Source route and browser call agree on path, method, field names, and response shape.
- The authenticated user-to-client mapping is verified or explicitly marked unverified.
- Telegram global state and client-scoped state are distinguished.
- Targeted tests pass; no raw secret appears in output.
- Live browser checks show the expected status, console state, and responsive geometry.
- After deployment, both the unique Pages hash URL and the custom domain serve the expected markers.

## References

- `references/telegram-client-status.md` — route mismatch pattern, redacted D1 probes, and regression cases for the dashboard Telegram indicator.
