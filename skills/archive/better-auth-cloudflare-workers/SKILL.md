---
name: better-auth-cloudflare-workers
category: devops
description: Self-hosted auth on Cloudflare Workers + D1 + Resend — replacing Clerk or other hosted auth providers.
created: 2026-04-15
---

# Self-Hosted Auth on Cloudflare Workers + D1 + Resend

## When to use
Replacing Clerk, Auth0, or other hosted auth with a self-hosted solution on Cloudflare Workers + D1.

## ⚠️ CRITICAL: Better Auth does NOT work with D1 (as of April 2026)

Better Auth (v1.6.3) has no working D1 adapter. Three approaches were tried and all failed:

1. **`D1Adapter` from `better-auth/adapters`** — doesn't exist. Import fails at build time.
2. **Kysely + `kysely-d1` D1Dialect** — compiles but Worker runtime errors 1101/1102. D1 doesn't support transactions, and Better Auth expects them.
3. **`database: {db: Kysely, type: "sqlite"}`** — same runtime failure.

**Solution: Custom lightweight auth** using Web Crypto (PBKDF2 + HMAC-SHA256). No external auth deps besides Resend.

## Architecture

Frontend (Pages) calls /api/auth/sign-in/email with credentials: 'include'
-> Worker -> custom auth handler -> D1 (users, verification tables)
-> Set-Cookie: scena_session=<HMAC-signed token> (httpOnly, secure, domain=.example.com)
-> Frontend calls /api/* with cookie (no Bearer token needed)

## Implementation

## 1. D1 Database Setup (Global API Key required for D1)

The mcporter `cfut_` token may lack D1 write permissions. Use the Global API Key from vault:

```bash
CF_GLOBAL=$(vault get cloudflare/global_api_key)
CF_EMAIL="lucas.jouvencon@gmail.com"
CF_ACCOUNT="«secret:vault»"

# Create D1 database via REST API
curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/d1/database" \
  -H "X-Auth-Email: ${CF_EMAIL}" \
  -H "X-Auth-Key: ${CF_GLOBAL}" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-app-db"}'

# Get the UUID from response, then run migration
# See cloudflare-pages-deployment-patterns skill for full D1 REST API patterns
```

### Install dependencies

Only Resend is needed: `npm install resend`

### 3. D1 migration

```sql
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL UNIQUE,
  emailVerified INTEGER NOT NULL DEFAULT 0,
  password TEXT NOT NULL DEFAULT '',
  image TEXT,
  createdAt TEXT NOT NULL DEFAULT (datetime('now')),
  updatedAt TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS verification (
  id TEXT PRIMARY KEY,
  identifier TEXT NOT NULL,
  value TEXT NOT NULL,
  expiresAt TEXT NOT NULL,
  createdAt TEXT NOT NULL DEFAULT (datetime('now')),
  updatedAt TEXT NOT NULL DEFAULT (datetime('now'))
);

ALTER TABLE your_table ADD COLUMN user_id TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_verification_identifier ON verification(identifier);
```

**Note:** `user` is a SQLite reserved word — use `users` (plural).

### 3. Auth module (src/auth.ts)

Password hashing: PBKDF2 with 100k iterations, SHA-256, 16-byte random salt. Format: `saltHex:hashHex`.

Session tokens: HMAC-SHA256 signed payload containing `userId:expiresAt`. Token stored as base64 of `payload.signatureHex`. No DB session table needed — stateless verification.

Core functions:
- `hashPassword(password, secret)` returns `saltHex:hashHex`
- `verifyPassword(password, stored, secret)` returns boolean
- `createSessionToken(userId, secret)` returns base64 token
- `verifySessionToken(token, secret)` returns userId or null
- `generateId()` returns 32-char hex (crypto.getRandomValues)

Auth routes handler `handleAuth(request, env)`:
- POST `/sign-up/email` — hash password, insert user, create verification token, send Resend email, set session cookie, return user
- POST `/sign-in/email` — verify password, set session cookie, return user
- GET `/get-session` — read cookie, verify HMAC, return user from D1
- POST `/sign-out` — clear cookie (Max-Age=0)
- GET `/verify-email?token=&email=` — validate token, update emailVerified, redirect to portal
- POST `/forgot-password` — create reset token, send Resend email

Session helper `getSessionUserId(request, env)` returns userId or null (used by protected routes)

### 4. Worker integration (src/index.ts)

In fetch handler, add BEFORE other routes:
```typescript
if (path.startsWith("/api/auth")) {
  return await handleAuth(request, env);
}
```

For protected routes, replace Clerk JWT verification with:
```typescript
const userId = await getSessionUserId(request, env);
if (!userId) return json({ error: "Unauthorized" }, 401);
// Look up client by user_id instead of clerk_id
```

### 5. CORS for cookie auth (critical)

Must add to ALL CORS responses:
```
"Access-Control-Allow-Credentials": "true"
```

Without this, browser silently drops Set-Cookie headers.

### 6. Frontend (no SDK — just fetch)

All fetch calls must include `credentials: 'include'`. Example pattern:

```javascript
// Sign up
fetch(API_BASE + "/api/auth/sign-up/email", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ name, email, password })
});

// Sign in
fetch(API_BASE + "/api/auth/sign-in/email", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({ email, password })
});

// Check session
fetch(API_BASE + "/api/auth/get-session", { credentials: "include" });

// API calls — cookie sent automatically
fetch(API_BASE + "/api/client/me", { credentials: "include" });
```

### 7. wrangler.toml

```toml
compatibility_flags = ["nodejs_compat"]  # Required if using Resend npm package
```

### Secrets (wrangler)

```bash
wrangler secret put BETTER_AUTH_SECRET  # generate: openssl rand -hex 32
wrangler secret put RESEND_API_KEY      # re_...
```

## Google OAuth

Add two routes to handleAuth:

1. `GET /google` — CSRF state (verification table, 10min), redirect to Google consent
2. `GET /google/callback` — verify state, exchange code for tokens, get user info, create/link user, set cookie, redirect to portal

Secrets: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

Frontend: `<a href="/api/auth/google" class="btn">Continuer avec Google</a>` with Google SVG logo. Full page redirect — no popup/iframe.

## Resend Email Pitfall

Check which subdomain has DKIM/SPF DNS records BEFORE setting `from` address. Example: DNS records were on `mail.walter-ai.cloud`, so `from` must be `auth@mail.walter-ai.cloud`, NOT `auth@walter-ai.cloud`.

## Pitfalls

- **Better Auth doesn't work with D1** — use custom auth instead (see above).
- **`user` is SQLite reserved word** — use `users` table name.
- **credentials: 'include' is MANDATORY** on every fetch call. Clerk used Bearer tokens (no CORS issue), cookie auth requires credentials.
- **CORS `Access-Control-Allow-Credentials: true`** must be on ALL responses, not just auth routes. Without it, browser silently drops Set-Cookie.
- **Cookie domain** must match domain pattern (`.example.com` for api.example.com + app.example.com). Without it, cookies only work on exact origin. When the API is on `*.workers.dev` and Pages on `*.pages.dev`, use the Worker hostname as domain OR omit domain (cookie scoped to exact origin). For cross-origin cookie auth, both must share a parent domain via custom domains.
- **PBKDF2 is CPU-heavy** — 100k iterations takes ~100ms in Workers. Sign-up/sign-in will be slower than Clerk's hosted auth.
- **No automatic Clerk user migration** — users must re-register. Keep `clerk_id` column during transition for legacy lookups.
- **Resend domain verification** — must add DNS records (DKIM, SPF, DMARC) for your domain before emails work.
- **wrangler deploy needs Global API Key** — scoped tokens lack D1 permissions.
- **D1 ALTER TABLE fails if column exists** — run CREATE TABLE and ALTER TABLE as separate commands.
- **Google OAuth callback must redirect to the Pages domain**, not the Worker domain. The callback route on the Worker sets the cookie (with domain matching the Worker) then 302-redirects to `https://your-pages-site.pages.dev/app.html`. The cookie is scoped to the Worker origin; if the Pages site is on a different domain, the session check (`/api/auth/get-session`) must be called with `credentials: 'include'` and CORS must allow credentials.
- **OAuth client reuse** — multiple Workers (e.g., Scena + FakeReach) can share the same Google OAuth client. Just add each Worker's callback URL to "Authorized redirect URIs" in Google Cloud Console. Copy the `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` values to each Worker's secrets.

## Migration from Clerk

1. Run D1 migration (add users/verification tables + user_id column on clients)
2. Deploy Worker with new auth code
3. Deploy Pages with new frontend (forms instead of Clerk SDK)
4. Existing Clerk users must re-register (no automatic password migration)
5. Keep clerk_id column for legacy lookups during transition
6. Update Stripe webhook metadata from clerk_id to user_id
