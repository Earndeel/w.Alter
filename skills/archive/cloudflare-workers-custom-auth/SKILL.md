---
name: cloudflare-workers-custom-auth
description: "Self-hosted auth on Cloudflare Workers + D1 + Resend — PBKDF2+HMAC session auth, Google OAuth, Stripe payments. Replaces Clerk/Better Auth. Includes migration guide from Clerk."
version: 2.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [cloudflare, workers, auth, d1, resend, google-oauth, stripe, pbkdf2, hmac]
---

# Cloudflare Workers Custom Auth (D1 + Resend)

## When to Use

- Replacing Clerk or Better Auth with self-hosted auth on Cloudflare Workers
- Building cookie-based session auth with PBKDF2 password hashing (Web Crypto)
- Setting up D1-backed user management with Resend email verification
- Better Auth fails on Workers+D1 (missing D1Adapter, Kysely dialect errors)

Replace Clerk/Better Auth with a lightweight self-hosted auth system that runs entirely on Cloudflare Workers using Web Crypto APIs and D1.

## Why Not Better Auth?

Better Auth (npm `better-auth`) does NOT work on Cloudflare Workers + D1:
- D1Adapter import does not exist in better-auth/adapters
- kysely-d1 D1Dialect causes runtime errors (1101/1102) — D1 lacks transaction support
- `{db: env.DB, type: "sqlite"}` expects Kysely-compatible interface, D1 API is different

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL UNIQUE,
  emailVerified INTEGER NOT NULL DEFAULT 0, password TEXT NOT NULL DEFAULT '',
  image TEXT, createdAt TEXT NOT NULL DEFAULT (datetime('now')),
  updatedAt TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS verification (
  id TEXT PRIMARY KEY, identifier TEXT NOT NULL, value TEXT NOT NULL,
  expiresAt TEXT NOT NULL, createdAt TEXT NOT NULL DEFAULT (datetime('now')),
  updatedAt TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Password Hashing — PBKDF2 (100k iterations, Web Crypto native)

bcrypt needs native modules unavailable in Workers. PBKDF2 works via crypto.subtle.

Store as `saltHex:hashHex`. Salt = 16 random bytes. Derive 256 bits with SHA-256.

## Session Tokens — HMAC-SHA256 Signed

Store expiry IN the token: `userId:expiresAt`. Sign with HMAC. Encode as base64.

No DB session table needed — just verify signature + expiry on each request.

## Cookie Config

`Set-Cookie: scena_session=TOKEN; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800; Domain=.yourdomain.com`

The leading dot on Domain enables cross-subdomain cookies.

## Frontend — Cookie-Based Auth

Use `credentials: 'include'` on all API calls. No Bearer tokens needed. Session cookie is sent automatically by the browser.

## Resend DNS Pitfall

Resend DNS records are per-subdomain. Check which subdomain has DKIM/SPF records before setting the email `from` address. In our case: DNS was on `mail.walter-ai.cloud`, so `from` must be `auth@mail.walter-ai.cloud`.

## CORS Requirements

`Access-Control-Allow-Credentials: true` is REQUIRED for cross-origin cookies.

## Google OAuth Flow

Add to handleAuth:

- **GET `/google`** — CSRF state in verification table (10min TTL), redirect to Google consent screen (`scope=openid+email+profile`)
- **GET `/google/callback`** — validate state, exchange code via POST to `oauth2.googleapis.com/token`, GET user info from `googleapis.com/oauth2/v2/userinfo`, create/link user in D1, set cookie, redirect to portal
- Env: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (wrangler secret put)
- Google Console: OAuth 2.0 Client ID → redirect URI = `https://api.yourdomain.com/api/auth/google/callback`
- Frontend: `<a href="/api/auth/google">` — full page redirect, no JS SDK
- Auto-links if same email exists as email/password user, marks emailVerified=1

## wrangler.toml

`compatibility_flags = ["nodejs_compat"]` — required for Resend npm SDK.

## Migration from Clerk

1. Run D1 migration (add users/verification tables + user_id column on clients)
2. Deploy Worker with new auth code
3. Deploy Pages with new frontend (forms instead of Clerk SDK)
4. Existing Clerk users must re-register (no automatic password migration)
5. Keep `clerk_id` column for legacy lookups during transition
6. Update Stripe webhook metadata from `clerk_id` to `user_id`

## Google OAuth

Add two routes to `handleAuth`:

1. `GET /google` — CSRF state (verification table, 10min TTL), redirect to Google consent screen (`scope=openid+email+profile`)
2. `GET /google/callback` — verify state, exchange code via POST to `oauth2.googleapis.com/token`, GET user info from `googleapis.com/oauth2/v2/userinfo`, create/link user in D1, set cookie, redirect to portal

Secrets: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

Frontend: `<a href="/api/auth/google">Continuer avec Google</a>` — full page redirect, no JS SDK.

**OAuth client reuse** — multiple Workers can share the same Google OAuth client. Just add each Worker's callback URL to "Authorized redirect URIs" in Google Cloud Console.

## Stripe Integration

### Checkout Sessions

Create dynamic checkout sessions (no pre-created prices):

```typescript
const session = await stripe.checkout.sessions.create({
  mode: 'payment',
  payment_method_types: ['card'],
  line_items: [{ price_data: {
    currency: 'eur',
    product_data: { name: 'Scena Credits', description: `${amount} credits` },
    unit_amount: amount * 100,  // cents
  }, quantity: 1 }],
  success_url: `${BASE_URL}/success?session_id={CHECKOUT_SESSION_ID}`,
  cancel_url: `${BASE_URL}/cancel`,
  metadata: { user_id: userId, credits: amount },
});
```

### Webhook Handler

```typescript
// POST /webhook/stripe
const sig = request.headers.get('stripe-signature');
const body = await request.text();  // MUST be raw text for signature verification
const event = stripe.webhooks.constructEvent(body, sig, STRIPE_WEBHOOK_SECRET);

if (event.type === 'checkout.session.completed') {
  const session = event.data.object;
  const userId = session.metadata.user_id;
  const credits = parseInt(session.metadata.credits);
  // Add credits to D1 user record
}
```

**Pitfall**: Stripe webhook signature verification requires raw body — don't parse JSON before verifying.

## Pitfalls

1. Better Auth + D1 is fundamentally broken — use custom auth
2. Resend DNS domain mismatch — check DKIM/SPF subdomain
3. D1 ALTER TABLE ADD COLUMN fails if column exists — handle idempotently
4. Cookie Domain must have leading dot for cross-subdomain
5. nodejs_compat flag required for npm packages
6. PBKDF2 not bcrypt — bcrypt unavailable in Workers runtime
7. Store token expiry inside the token to avoid DB lookups
8. CORS OPTIONS handler must return Allow-Credentials header
