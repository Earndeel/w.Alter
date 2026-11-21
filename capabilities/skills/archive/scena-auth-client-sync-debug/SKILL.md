---
name: scena-auth-client-sync-debug
description: Debug Scena login/sync issues where credits or Telegram bot state desynchronize after authentication.
---

# Scena Auth / Client Sync Debug

## When to Use

- Scena users can sign in but dashboard shows stale credits or missing bot info
- Client record desynchronizes after authentication
- Login succeeds but sync fails (cookie vs bearer token mismatch)
- Bot connection updates wrong client row

Use this when Scena users can sign in but the dashboard shows stale credits, missing bot info, or the wrong client record after login.

## Goal
Find whether the break is in:
- session auth (cookie vs bearer token)
- client resolution (user_id, email, clerk_id)
- D1 schema / migration mismatch
- frontend sync order
- test coverage / regressions

## Procedure
1. Inspect the request path end-to-end:
   - portal login / auth callback
   - client sync endpoint
   - client me/dashboard endpoint
   - bot connect endpoint
   - credit/bot persistence writes

2. Check auth semantics first:
   - confirm whether the frontend sends `credentials: 'include'`
   - confirm whether the backend expects cookie session, bearer token, or both
   - if the API rejects requests before trying session resolution, move session lookup ahead of token checks

3. Verify client lookup order:
   - prefer `user_id` for authenticated sessions
   - fall back to `email` when migrating older accounts
   - only use `clerk_id` when the request genuinely comes from Clerk auth
   - never assume a client already exists during sync

4. Make `/api/client/sync` idempotent:
   - update existing client when found
   - link `user_id` if missing
   - if an email match exists, attach the session to that record instead of creating a duplicate
   - create a new client only if no match exists

5. Inspect schema compatibility:
   - confirm the schema actually has the columns the code writes (`user_id`, `telegram_bot_token`, `telegram_chat_id`, `clerk_id`, etc.)
   - if migration and canonical schema differ, use the canonical schema as source of truth and backfill carefully

6. When debugging bot sync:
   - ensure bot connect updates only the current client row
   - verify uniqueness constraints for bot token and clerk_id
   - avoid touching any shared `bot_pool` table unless explicitly required

7. Add or update regression tests:
   - session-cookie auth should work without Bearer token for client portal routes
   - `/api/client/sync` should create or relink a client when only a session exists
   - dashboard `/api/client/me` should resolve the same client after sync
   - bot connection should update the current client row only

## Common pitfall
A login can succeed while sync fails because the frontend uses cookie auth, but the backend still demands a Bearer token before resolving the session. That produces stale credits and missing bot state.

Another frequent pitfall on Scena's split subdomains (`scena.walter-ai.cloud` → `api.walter-ai.cloud`) is missing credentialed CORS headers on `/api/client/*`. When the portal fetches with `credentials: 'include'`, the Worker response must include BOTH:
- `Access-Control-Allow-Origin: https://scena.walter-ai.cloud` (or the exact allowed origin)
- `Access-Control-Allow-Credentials: true`

If auth endpoints work but `/api/client/me` / `/api/client/sync` silently fail in the browser, inspect the live response headers first.

## Verification
After changes:
- login works
- `/api/client/sync` succeeds
- `/api/client/me` returns the expected credits and bot fields
- the same client remains selected across refreshes
- regression tests pass for auth + sync paths
