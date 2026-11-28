---
name: cloudflare-auth-standard
category: devops
description: Standard auth stack for Cloudflare Workers — custom PBKDF2+HMAC session auth (no external deps), Google OAuth, Resend emails, Stripe payments. Replaces Clerk/Better Auth for full control on D1.
created: 2026-04-15
---

# Standard Auth Stack — Cloudflare Workers

## When to Use
- Building a new Cloudflare Worker that needs authentication (login, signup, sessions)
- Replacing Clerk/Better Auth with a self-contained auth system on D1
- Adding Google OAuth or Stripe checkout to a Worker-based app

## Pitfalls
- PBKDF2 with 100k iterations is slow on Workers CPU limits — consider reducing for signup/login flows
- D1 has a 10MB database size limit — plan session cleanup for high-traffic apps
- Stripe webhook signature verification requires raw body — don't parse JSON before verifying
- Google OAuth redirect URI must exactly match what's configured in Google Cloud Console

## Stack Components
- **Cloudflare Workers** — API server (TypeScript)
- **Cloudflare D1** — SQLite database (users, verification tables)
- **Resend** — transactional emails (verification, password reset)
- **Stripe** — payments (checkout sessions, webhooks)
- **Google OAuth** — social login (optional)

## Auth Implementation

### Password Hashing
PBKDF2 with 100k iterations, SHA-256, random 16-byte salt.
Format in DB: `saltHex:hashHex`

### Session Tokens
HMAC-SHA256 signed tokens stored as `scena_session` cookie.
- HttpOnly, Secure, SameSite=Lax
- Domain: `.project-domain.com` (cross-subdomain)
- Max-Age: 7 days

### D1 Tables Required
- `users` — id, name, email, emailVerified, password, image, createdAt, updatedAt
- `verification` — id, identifier, value, expiresAt, createdAt, updatedAt

### API Routes
- `POST /api/auth/sign-up/email` — register + send verification email + set cookie
- `POST /api/auth/sign-in/email` — login + set cookie
- `GET /api/auth/google` — redirect to Google OAuth
- `GET /api/auth/google/callback` — handle Google callback, set cookie
- `GET /api/auth/get-session` — check cookie, return user or null
- `POST /api/auth/sign-out` — clear cookie
- `GET /api/auth/verify-email` — verify email token
- `POST /api/auth/forgot-password` — send reset email

### Google OAuth Setup
1. Google Cloud Console → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (Web application)
3. Authorized redirect URIs: `https://api.domain.com/api/auth/google/callback`
4. Set secrets: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

### Resend Setup
1. Add domain in Resend dashboard
2. Add DNS records (SPF, DKIM) in Cloudflare
3. From address: Project <auth@mail.domain.com>
4. Set secret: RESEND_API_KEY

### wrangler.toml
Needs `compatibility_flags = ["nodejs_compat"]`

### Secrets
BETTER_AUTH_SECRET, RESEND_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BASE_URL

### CORS
Must include `Access-Control-Allow-Credentials: true` and specific origin (not wildcard).

### Frontend
All fetch calls use `credentials: 'include'` for cookie auth. No Bearer tokens.
Google sign-in is a simple redirect to `/api/auth/google`.

### Why NOT better-auth npm
- `better-auth` uses Kysely internally → Kysely D1 driver doesn't support transactions → runtime crash
- D1 itself doesn't support traditional SQL transactions
- Custom auth (PBKDF2 + HMAC + Web Crypto) is ~15KB vs ~400KB for better-auth
- For simple SaaS (email + Google), custom is sufficient
- If 2FA/magic links/multi-org needed later, write a custom D1 adapter for better-auth

### Reference Implementation
See `/root/projects/scena-cloudflare/workers/api/src/auth.ts` for full working code.
