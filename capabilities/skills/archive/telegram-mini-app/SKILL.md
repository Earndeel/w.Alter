---
name: telegram-mini-app
category: devops
description: Build Telegram Mini Apps (Web Apps) that open inside Telegram — auth via initData HMAC-SHA256, Bearer token API access, theme integration, auto-provisioning, and bot button setup. Use for dashboards, UIs, forms, or any web experience embedded in Telegram.
---

# Telegram Mini App — Full Stack Integration

Embed a web app (dashboard, form, store, etc.) directly inside Telegram. No login screen, no separate auth — Telegram handles identity via cryptographic `initData`.

## When to Use
- Client dashboards accessible from a Telegram bot
- Any web UI that should feel native inside Telegram
- Replacing browser redirects with in-app experiences
- Stripe checkout flows inside Telegram

## Architecture

```
Bot → Inline button (web_app) → Worker serves HTML → initData auth → API calls with Bearer token
```

Key insight: serve the Mini App HTML **from the same Worker that handles the API**. Same origin = no CORS issues, Bearer token works without cookies.

## Step 1: Create the Mini App HTML

The page must:
1. Load `telegram-web-app.js` SDK
2. Call `tg.ready()` and `tg.expand()` on init
3. Use `tg.initData` for auth (never parse `initDataUnsafe` for security — validate via HMAC)
4. Use Telegram CSS variables for theme matching

```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root{
    --bg:var(--tg-theme-bg-color,#fff);
    --card:var(--tg-theme-secondary-bg-color,#f0f2f5);
    --text:var(--tg-theme-text-color,#000);
    --muted:var(--tg-theme-hint-color,#999);
    --accent:var(--tg-theme-button-color,#3390ec);
    --accent-text:var(--tg-theme-button-text-color,#fff);
  }
</style>
<script>
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();
// Auth
const r = await fetch('/api/auth/telegram', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ initData: tg.initData }),
});
const { token } = await r.json();
// API calls with Bearer token
const data = await fetch('/api/...', {
  headers: { 'Authorization': `Bearer ${token}` },
});
</script>
```

## Step 2: Auth Endpoint (HMAC-SHA256 Validation)

Telegram signs all initData with HMAC-SHA256. You MUST validate this server-side.

### Validation Algorithm (per Telegram docs):
```
1. Parse initData as URL params
2. Extract 'hash' param, remove it from the rest
3. Sort remaining params alphabetically
4. Join as "key=value\nkey=value" (data_check_string)
5. secret_key = HMAC-SHA256("WebAppData", bot_token)
6. computed = HMAC-SHA256(secret_key, data_check_string)
7. computed === hash → valid
```

### Cloudflare Worker Implementation:

```typescript
// POST /api/auth/telegram
async function handleTelegramAuth(request: Request, env: Env): Promise<Response> {
  const { initData } = await request.json();
  const params = new URLSearchParams(initData);
  const hash = params.get("hash");
  params.delete("hash");

  // Sort + join
  const entries = Array.from(params.entries()).sort(([a], [b]) => a.localeCompare(b));
  const dataCheckString = entries.map(([k, v]) => `${k}=${v}`).join("\n");

  // Step 1: secret_key = HMAC-SHA256("WebAppData", bot_token)
  const enc = new TextEncoder();
  const webAppDataKey = await crypto.subtle.importKey(
    "raw", enc.encode("WebAppData"),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const secretKeyRaw = await crypto.subtle.sign("HMAC", webAppDataKey, enc.encode(env.TELEGRAM_BOT_TOKEN));

  // Step 2: HMAC-SHA256(secret_key, data_check_string)
  const secretKey = await crypto.subtle.importKey(
    "raw", secretKeyRaw,
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", secretKey, enc.encode(dataCheckString));
  const computedHex = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, "0")).join("");

  if (computedHex !== hash) {
    return json({ error: "Invalid signature" }, 401);
  }

  // Check auth_date freshness (within 24h)
  const authDate = parseInt(params.get("auth_date") || "0");
  if (Date.now() / 1000 - authDate > 86400) {
    return json({ error: "Expired" }, 401);
  }

  // Parse user info
  const tgUser = JSON.parse(params.get("user")!);
  const tgId = String(tgUser.id);

  // Find or create user by telegram_id
  let user = await env.DB.prepare("SELECT id FROM users WHERE telegram_id = ?")
    .bind(tgId).first<any>();
  if (!user) {
    const id = generateId();
    const name = [tgUser.first_name, tgUser.last_name].filter(Boolean).join(" ");
    await env.DB.prepare(
      "INSERT INTO users (id, name, telegram_id, ...) VALUES (?, ?, ?, ...)"
    ).bind(id, name, tgId).run();
    user = { id };
  }

  // Return session token
  const token = await createSessionToken(user.id, env.SECRET);
  return json({ token });
}
```

## Step 3: Bearer Token Auth Support

Mini Apps can't set HttpOnly cookies. Update your auth middleware to check both:

```typescript
async function getSessionUserId(request: Request, env: Env): Promise<string | null> {
  // Check Bearer token first (Telegram Mini App)
  const auth = request.headers.get("Authorization") || "";
  if (auth.startsWith("Bearer ")) {
    return verifySessionToken(auth.slice(7), env.SECRET);
  }
  // Fall back to cookie
  const cookie = request.headers.get("Cookie") || "";
  const match = cookie.match(/session=([^;]+)/);
  return match ? verifySessionToken(match[1], env.SECRET) : null;
}
```

## Step 4: Serve from Worker (Same Origin)

Add a route that returns the HTML directly — avoids CORS and cookie issues:

```typescript
if (path === "/tg" || path === "/tg/") {
  return new Response(HTML_CONTENT, {
    headers: { "Content-Type": "text/html; charset=utf-8" },
  });
}
```

## Step 5: Bot Button Setup

In your bot logic, send a message with a `web_app` inline button:

```json
{
  "method": "sendMessage",
  "chat_id": "<CHAT_ID>",
  "text": "📊 Ouvrir ton dashboard",
  "reply_markup": {
    "inline_keyboard": [[{
      "text": "📊 Dashboard",
      "web_app": { "url": "https://api.example.com/tg" }
    }]]
  }
}
```

Or via Telegram Bot API directly:
```bash
curl "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d chat_id=<CHAT_ID> \
  -d text="📊 Dashboard" \
  -d reply_markup='{"inline_keyboard":[[{"text":"📊 Dashboard","web_app":{"url":"https://api.example.com/tg"}}]]}'
```

## Step 6: Database Migration

Add `telegram_id` column to users table:

```sql
ALTER TABLE users ADD COLUMN telegram_id TEXT;
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
```

## Telegram SDK API Reference

### Init & Lifecycle
```javascript
tg.ready()          // Tell Telegram the app is loaded
tg.expand()         // Expand to full height
tg.close()          // Close the Mini App
```

### User Info
```javascript
tg.initDataUnsafe.user.id          // Telegram user ID
tg.initDataUnsafe.user.first_name  // First name
tg.initDataUnsafe.user.last_name   // Last name
tg.initDataUnsafe.user.username    // @username
tg.initDataUnsafe.bot.username     // Bot that opened the app
```

### Theme
```javascript
tg.themeParams.bg_color           // Background color
tg.themeParams.text_color         // Text color
tg.themeParams.hint_color         // Muted/hint color
tg.themeParams.button_color       // Primary button color
tg.themeParams.button_text_color  // Button text color
tg.themeParams.secondary_bg_color // Card/elevated background
```

### UI Components
```javascript
// Main button (bottom of screen)
tg.MainButton.setParams({ text: 'Save', color: '#3390ec' })
tg.MainButton.show()
tg.MainButton.onClick(callback)

// Popup
tg.showPopup({ title: 'OK', message: 'Done!', buttons: [{ type: 'ok' }] })
tg.showAlert('Error message')

// Back button
tg.BackButton.show()
tg.BackButton.onClick(callback)
```

### Links
```javascript
tg.openLink(url, { try_instant_view: false })  // External link
tg.openTelegramLink('https://t.me/username')   // Telegram link
```

## Multi-Tenant Client Linking (Portal + Mini App)

In a multi-tenant SaaS where clients register via a web portal (Clerk) AND use a Telegram Mini App, the challenge is linking the same user across both auth methods without creating duplicate client records.

### The Problem

- Portal auth creates a client with `clerk_id` and real credits/bot config
- Telegram auth creates a user with `telegram_id` — but which client does this user own?
- Naive approach creates a new empty client → user sees 0 credits in Mini App

### The Solution: Link via `telegram_chat_id`

When a user sends a message to their Scena bot, the webhook receives their Telegram user ID as `chat_id` (for DMs, `chat_id` == `telegram_id`). Store this on the client. Then the Mini App auth can find the right client.

**Step 1**: Webhook stores telegram_chat_id (already common):
```typescript
// In telegram webhook handler
await env.DB.prepare(
  "UPDATE clients SET telegram_chat_id = ?, updated_at = datetime('now') WHERE matricule = ?"
).bind(String(chatId), matricule).run();
```

**Step 2**: Auth handler links client by telegram_chat_id:
```typescript
// POST /api/auth/telegram — after finding/creating user...
let client = await env.DB.prepare(
  "SELECT id FROM clients WHERE user_id = ? AND status != 'archived' ORDER BY credits DESC, id DESC LIMIT 1"
).bind(user.id).first();

if (!client) {
  // Find existing client by telegram_chat_id (set when user messaged their bot)
  const existing = await env.DB.prepare(
    "SELECT id FROM clients WHERE telegram_chat_id = ? AND status != 'archived' ORDER BY credits DESC, id DESC LIMIT 1"
  ).bind(tgId).first();

  if (existing) {
    // Link existing client to this Telegram user
    await env.DB.prepare(
      "UPDATE clients SET user_id = ?, updated_at = datetime('now') WHERE id = ?"
    ).bind(user.id, existing.id).run();
    client = existing;
  }
}

if (!client) {
  // No existing client — create a new one (first-time user)
  // ... create logic ...
}
```

### Critical: ORDER BY credits DESC

When multiple clients might match (e.g., duplicates from testing), always prefer the one with existing credits:

```sql
SELECT * FROM clients WHERE user_id = ? AND status != 'archived'
ORDER BY credits DESC, id DESC LIMIT 1
```

### Linking Flow (for new clients)

1. Client creates account on portal (Clerk) → buys credits
2. Client connects their Telegram bot via portal → webhook configured
3. Client sends first message to their bot → webhook stores `telegram_chat_id`
4. Client opens Mini App → auth finds client by `telegram_chat_id` → links `user_id` → correct credits shown

No duplicate clients possible. The link is made at the natural interaction point (first bot message).

### Pitfall: Forgetting to wire the auth handler

The `handleAuth` function can exist in auth.ts but never be called if you forget to import and route it:

```typescript
// In index.ts
import { handleAuth, getSessionUserId } from "./auth";

// In the router
if (path.startsWith("/api/auth/")) {
  return await handleAuth(request, env as any);
}
```

### Pitfall: Existing API routes reject Mini App tokens

If your `/api/client/me` endpoint uses `verifyClerkToken()`, Mini App Bearer tokens (custom HMAC session tokens) will be rejected. Fix by checking session tokens first, then falling back to Clerk:

```typescript
async function handleClientPortal(request, env, path, method) {
  const token = (request.headers.get("Authorization") || "").replace("Bearer ", "");
  if (!token) return json({ error: "Unauthorized" }, 401);

  let client = null;
  let clerkId = null;

  // Try custom session token first (Telegram Mini App)
  const sessionUserId = await getSessionUserId(request, env);
  if (sessionUserId) {
    client = await env.DB.prepare(
      "SELECT * FROM clients WHERE user_id = ? AND status != 'archived' ORDER BY credits DESC, id DESC LIMIT 1"
    ).bind(sessionUserId).first();
  }

  // Fallback: Clerk JWT
  if (!client) {
    const user = await verifyClerkToken(token);
    if (user?.clerk_id) {
      clerkId = user.clerk_id;
      client = await getPrimaryClientByClerkId(env, clerkId);
    }
  }

  if (!client) return json({ error: "Unauthorized" }, 401);

  // Routes use `client` directly — remove per-route getPrimaryClientByClerkId calls
}
```

**Important**: Remove per-route `getPrimaryClientByClerkId(env, user.clerk_id)` calls and use the already-resolved `client`. Replace `user.clerk_id` references with `clerkId || ""`.

## Chat Menu Button (vs Inline Button)

In addition to inline `web_app` buttons in messages, you can set a persistent menu button in the bottom-left of the chat:

```python
import urllib.request, json

def set_menu_button(bot_token, url, text="Dashboard"):
    payload = json.dumps({
        "menu_button": {
            "type": "web_app",
            "text": text,
            "web_app": {"url": url}
        }
    })
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/setChatMenuButton",
        data=payload.encode(),
        headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req).read())
```

Or via curl:
```bash
curl -X POST "https://api.telegram.org/bot<TOKEN>/setChatMenuButton" \
  -H "Content-Type: application/json" \
  -d '{"menu_button":{"type":"web_app","text":"Dashboard","web_app":{"url":"https://api.example.com/tg"}}}'
```

The menu button is persistent across all chats with the bot — no need to embed it in every message.

## Integrating Mini App into Existing Worker with Clerk Auth

When adding Telegram Mini App support to a Worker that already uses Clerk for auth (e.g., a web portal), you must modify the existing auth flow to accept both token types.

### Pitfall: Auth handler not wired in router

The `handleAuth` function can exist in auth.ts but never be called if you forget to import it and add a route in index.ts:

```typescript
// In index.ts — ADD THIS IMPORT
import { handleAuth, getSessionUserId } from "./auth";

// In the router — ADD THIS ROUTE
if (path.startsWith("/api/auth/")) {
  return await handleAuth(request, env as any);
}
```

### Pitfall: Existing API routes reject Mini App tokens

If your `/api/client/me` endpoint uses `verifyClerkToken()`, Mini App Bearer tokens (custom HMAC session tokens) will be rejected as "invalid Clerk token". Fix by checking session tokens first:

```typescript
async function handleClientPortal(request, env, path, method) {
  const token = (request.headers.get("Authorization") || "").replace("Bearer ", "");
  if (!token) return json({ error: "Unauthorized" }, 401);

  let client = null;
  let clerkId = null;

  // Try custom session token first (Telegram Mini App)
  const sessionUserId = await getSessionUserId(request, env);
  if (sessionUserId) {
    client = await env.DB.prepare(
      "SELECT * FROM clients WHERE user_id = ? AND status != 'archived' ORDER BY id DESC LIMIT 1"
    ).bind(sessionUserId).first();
  }

  // Fallback: Clerk JWT
  if (!client) {
    const user = await verifyClerkToken(token);
    if (user?.clerk_id) {
      clerkId = user.clerk_id;
      client = await getPrimaryClientByClerkId(env, clerkId);
    }
  }

  if (!client) return json({ error: "Unauthorized" }, 401);

  // Routes can now use `client` directly — no more per-route getPrimaryClientByClerkId
}
```

**Important**: Remove the per-route `getPrimaryClientByClerkId(env, user.clerk_id)` calls and use the already-resolved `client` from the top of the function. Also replace `user.clerk_id` references with `clerkId || ""`.

### Pitfall: NOT NULL constraint for Telegram users

Telegram provides no email. When creating a client record for a Telegram user, the INSERT must include `email=''` (empty string) to satisfy `NOT NULL` constraints:

```sql
-- This FAILS if email is NOT NULL:
INSERT INTO clients (user_id, matricule, name, credits, status, created_at, updated_at)
VALUES (?, ?, ?, 0, 'active', datetime('now'), datetime('now'))

-- This works:
INSERT INTO clients (user_id, matricule, name, email, credits, status, created_at, updated_at)
VALUES (?, ?, ?, '', 0, 'active', datetime('now'), datetime('now'))
```

## Custom credit checkout pattern (Scena)

For Mini Apps that expose Stripe credit purchases, a robust pattern is:
- keep only the business-approved preset cards
- in Scena's current setup: exactly 3 slots → `custom`, `$19`, `$49`
- map presets to fixed credits server-side (current Scena mapping: `$19 -> 100 credits`, `$49 -> 250 credits`)
- add a `custom` card with a numeric input (`custom-credits-input`)
- compute the preview price client-side from the same rule used by the backend
- send `POST /api/client/checkout` with either:
  - `{ plan: 'usd19' | 'usd49' }`
  - or `{ plan: 'custom', custom_credits: 250 }`
- in Telegram, open the returned Stripe URL with `tg.openLink(data.url, { try_instant_view: false })`

Current Scena pricing rule is pack-aligned, not flat-per-credit:
- `100 credits = $19`
- `250 credits = $49`
- custom price currently follows `price_cents = credits * 20 - 100` with a minimum of 100 credits, so the custom preview/backend stay aligned with those two public anchors.

Important backend rule: never trust the client price. Recompute `price_cents` server-side from the submitted `custom_credits`, persist `metadata[plan]=custom` + `metadata[credits]=<amount>` into Stripe Checkout, and use `currency=usd` when the public UI is shown in dollars.

## Pitfalls

- **Never trust `initDataUnsafe` for auth** — always validate `initData` via HMAC. `initDataUnsafe` can be spoofed by the client.
- **`auth_date` expiry** — Telegram recommends validating freshness (within 24h). Rejected stale initData forces users to reopen.
- **Same-origin serving** — serve from the same domain as your API to avoid CORS. Embed HTML in Worker or use Pages with `_routes.json`.
- **No HttpOnly cookies** — Mini App webview can't set them. Use Bearer tokens.
- **`/` escape in template literals** — TypeScript Workers need `<\\/script>` instead of `</script>` in embedded HTML strings.
- **HMAC is two-step** — `HMAC("WebAppData", bot_token)` produces the key, then `HMAC(key, data_check_string)` produces the signature. Not a single HMAC call.
- **Bot must be linked** — the bot that sends the `web_app` button must be connected to the client's account (multi-tenant scenario).
- **`getMe` API to verify bot tokens** — use `https://api.telegram.org/bot<TOKEN>/getMe` before accepting a bot token from a user.
- **Menu button vs inline button** — menu button is global (all chats), inline buttons are per-message. Use both: menu button for quick access, inline buttons for contextual CTAs.
- **CF Worker HTML escaping** — when embedding HTML in Worker TypeScript template literals, special chars like `$`, backticks, and `\` need escaping. Prefer a separate static file served via Pages if the HTML is complex.
