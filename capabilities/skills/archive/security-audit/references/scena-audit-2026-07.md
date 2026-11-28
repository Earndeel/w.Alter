# Scena Security Audit — Findings Reference

Completed 2026-07-22. Full read-only audit of `/root/projects/scena-cloudflare`.

## Architecture Summary

- **3 D1 databases**: `scena-db` (runtime), `scena-saas-db` (SaaS Connect), `scena-ops-db` (Sentinel)
- **Single Worker**: `scena-api` (3555 lines in index.ts)
- **Auth**: Custom Better Auth (PBKDF2 + HMAC sessions + Google OAuth + Telegram Mini App)
- **Billing**: Stripe Checkout → webhook → credit ledger → consumption → refund on failure
- **Webhooks**: 9 inbound endpoints (Telegram, PiAPI, Fal, Kie, Stripe, SaaS providers, pipeline)

## Critical Findings (for pattern recognition)

### Pattern: Plaintext secrets in D1 columns
`telegram_bot_token` and `bot_pool.token` stored in plaintext.
→ Always check every TEXT column for secret-sounding names during Phase 2.

### Pattern: Admin auth bypass via raw secret comparison
`token === env.ADMIN_SECRET` allows secret-as-Bearer, bypassing expirable HMAC tokens.
→ Always check admin auth for `=== env.SECRET` comparisons.

### Pattern: Inbound webhooks without signature verification
`/webhook/saas/kie` and `/webhook/saas/fal` accept any POST with no HMAC/IP check.
→ Map ALL webhook endpoints in Phase 4. Check each for auth.

### Pattern: Hardcoded encryption fallback key
`'scena-connect-dev-secret'` as default when env vars missing.
→ During Phase 6, grep for string literals near `encrypt`/`decrypt` calls.

### Pattern: SSRF via user-controlled callback URLs
`fetch(callbackUrl)` with no URL validation, protocol check, or IP restriction.
→ During Phase 4, trace every `fetch()` call that uses user-provided URLs.

### Pattern: Double-refund on webhook replay
`UPDATE credits = credits + X WHERE id = Y` without status guard.
→ During Phase 5, check every credit mutation for idempotency guards.

### Pattern: Cross-tenant job matching via loose fallback
Fal image webhook fallback selects `LIMIT 1` across ALL clients.
→ During Phase 4, check every webhook-to-job lookup for tenant isolation.

### Pattern: Admin API exposes token prefixes
`env.STRIPE_SECRET_KEY.substring(0, 12)` returned in settings endpoint.
→ During Phase 6, check admin/debug endpoints for substring exposure of secrets.

### Pattern: Unprotected admin-level route creation
`POST /api/saas/connections` missing `requireAdmin()` while GET has it.
→ During Phase 3, check every HTTP method on privileged routes individually.

## Table of all audited files

| File | Lines | Role |
|------|-------|------|
| `workers/api/src/index.ts` | 3555 | Router, webhooks, Stripe, client portal, admin API |
| `workers/api/src/saas_connect.ts` | 1734 | SaaS Connect (auth, generation, webhooks, encryption) |
| `workers/api/src/agent.ts` | 2839 | Agent brain, credit checks, video/image generation |
| `workers/api/src/auth.ts` | 402 | Better Auth (email, Google, Telegram Mini App) |
| `d1/schema.sql` | 350 | Canonical runtime schema |
| `d1/schema-v2.sql` | 306 | Schema v2 with workflow_artifacts |
| `d1/scena-saas-db.sql` | 212 | SaaS DB schema + seed data |
| `d1/scena-ops-db.sql` | 215 | Ops DB schema + seed data |
| `d1/saas-connect.sql` | 212 | Duplicate of scena-saas-db.sql |
| `d1/migrations/001_better_auth.sql` | 32 | Users, verification tables |
| `d1/migrations/002_client_brain_base_user_md.sql` | 1 | Single column add |
| `d1/migrations/003_client_memory_md.sql` | 2 | Memory columns |
| `workers/api/wrangler.toml` | 30 | Worker config, D1 bindings |
