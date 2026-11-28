# Scena Security Audit — Corrected July 2026 Baseline

Evidence snapshot from the July 22, 2026 audit of `/root/projects/scena-cloudflare`.
Treat line numbers as historical anchors and retrace symbols on the current branch.
No secrets are recorded here.

## Scope and verification

- Current worktree: 22 TypeScript files, 17 HTML files, 12 SQL files; repository was materially dirty, so distinguish `HEAD`, worktree, and deployed Worker.
- Production read-only health checks returned 200 for API, Portal, and Admin custom domains.
- `npm test`: 112 passed / 20 failed out of 132. Many failures were source/HTML contract snapshots, but at least one exposed a real missing auth guard.
- Clean-bootstrap check with in-memory SQLite:
  - `d1/schema.sql`: failed on an index referencing missing `clerk_id`.
  - `d1/scena-saas-db.sql`: passed.
  - `d1/scena-ops-db.sql`: passed.
- A supposedly invalid production probe, `POST /api/saas/connections` with `{}`, created a real connection because the handler supplies defaults. The exact audit artifact was deleted and `COUNT(*) = 0` was verified. Never repeat this probe in production.

## Verified critical exploit chains

### Anonymous SaaS provisioning can consume global provider credentials

**Evidence:** `workers/api/src/saas_connect.ts` routes `POST /api/saas/connections` before `requireAdmin`; `createConnection()` supplies a default name and returns API/webhook credentials. Provider resolution falls back from per-connection BYOK credentials to Worker-global provider keys.

**Impact:** an unauthenticated caller can mint connections repeatedly, bypass per-connection quotas, and invoke paid providers using platform credentials.

**Required fix:** choose one explicit commercial mode:
- admin/verified onboarding only; or
- self-service BYOK with a valid provider key required and no platform-key fallback.
Add global abuse limits independent of connection ID and rotate/revoke unknown keys after deployment.

### Session user can claim an existing client by body-supplied email

**Evidence:** `index.ts:3394-3414` lets `/api/client/sync` prefer request `body.email`, looks up an existing client by that email, then assigns the caller's `user_id`. `auth.ts:113-145` establishes a session immediately after signup.

**Impact:** a new account can claim another client's record if the victim email is known.

**Required fix:** derive identity only from the verified session. Ignore body email for ownership linking; require a signed migration/invite token for legacy records.

### Public Telegram and legacy onboarding routes compose into free provider abuse

**Evidence:**
- `/api/register` creates a client with initial credits without authenticated ownership or robust anti-abuse.
- `/webhook/telegram/:matricule` has no Telegram `secret_token` verification and updates `telegram_chat_id` from the inbound body.
- `/api/bot/validate` can overwrite a client's bot binding using only a matricule and a valid bot token.

**Impact:** repeated free accounts, forged Telegram updates, chat takeover, provider-credit consumption, or bot-delivery hijack.

**Required fix:** remove/lock legacy routes, configure Telegram webhook `secret_token`, verify `X-Telegram-Bot-Api-Secret-Token`, and bind every mutation to an authenticated owner.

### Public sequential job lookup is an IDOR

**Evidence:** `index.ts:352-355` exposes `GET /api/jobs/{id}`; `handleGetJob()` at `index.ts:2426-2429` returns `SELECT * FROM video_jobs WHERE id = ?` without owner/session checks.

**Impact:** enumeration can disclose prompts, media URLs, chat IDs, client IDs, and provider correlation IDs.

**Required fix:** remove the public route or require a tenant/session plus `WHERE id = ? AND client_id = ?`; return a minimal response DTO rather than `SELECT *`.

### Credit accounting is non-atomic and ledger data can be corrupt

**Evidence:** debit paths in `agent.ts` perform `SELECT credits`, calculate in application code, then write an absolute balance in separate queries. A timeout refund path binds `clientId` into `balance_after` rather than the resulting balance.

**Impact:** concurrent generations can spend the same balance; audit ledger and user balance can disagree.

**Required fix:** conditional atomic debit:

```sql
UPDATE clients
SET credits = credits - ?
WHERE id = ? AND credits >= ?;
```

Check affected-row count, then insert ledger data from the authoritative post-update balance. Add a unique operation/idempotency key shared by debit and refund paths.

### Signed Stripe webhook still permits replay

**Evidence:** `index.ts:3201-3261` verifies Stripe HMAC but does not enforce timestamp tolerance or deduplicate `event.id` / payment/session identity before crediting.

**Impact:** replay of a previously valid webhook can credit the same purchase again.

**Required fix:** validate signature timestamp, persist unique Stripe event and payment identifiers, and perform credit update + dedup insert atomically/idempotently.

## High-risk hardening gaps

- Provider and pipeline webhooks lack provider-specific signature verification, replay protection, and terminal-state idempotency. Scope correlation lookups by tenant/connection when possible.
- Arbitrary `callback_url` values trigger Worker-side outbound fetches. Restrict scheme/host, resolve and reject private/link-local destinations where the runtime permits, and defend against redirects/rebinding.
- Agent "explicit approval" exists mainly in prompt text; executor paths should enforce approval and duplicate-generation limits. Same-response parallel tool calls must share a reservation guard.
- `concurrent_job_limit` exists in schema/policy but was not enforced on every create path.
- Provider keys are AES-GCM encrypted, which is good, but encryption key fallback/reuse and absent rotation/versioning increase blast radius.
- Telegram bot tokens remain plaintext in D1 and should be encrypted at rest with versioned keys.
- Admin/auth endpoints need rate limiting and stronger session/secret lifecycle controls.
- Broad Pages CORS patterns should be narrowed, but browser exploitability must be evaluated with preflight, `SameSite`, and credential transport rather than declared from headers alone.

## Disaster recovery and contract integrity

- `d1/schema.sql` did not bootstrap cleanly because `clerk_id` was indexed but not declared. This is a release/restore blocker, not proof of a remote exploit.
- OpenAPI required admin authentication for connection creation while implementation omitted it.
- Portal called methods/fields absent from the Worker (`GET`/`DELETE /api/client/bot`, `GET /api/client/sync`, mismatched job and bot fields).
- Portal interface called authenticated SaaS pipeline endpoints without the Bearer key and referenced nonexistent callback/SSE routes.
- Connect wizard used same-origin `API = ''` while examples referenced the API custom domain; its client-side BYOK requirement was not enforced server-side.

Security controls must be tested end to end across route, method, auth transport, request/response fields, and frontend usage—not file by file in isolation.

## False positives removed from the original baseline

- Direct comparison against `env.ADMIN_SECRET` is not by itself plaintext password storage. The real issues are secret reuse, brute-force resistance, token lifetime, and exposure paths.
- A redacted provider-prefixed identifier shown as `***` is not automatically a literal malformed schema column. Confirm with raw schema or `PRAGMA table_info`.
- A missing-column bootstrap failure is not automatically P0 security severity; classify it under restore/deployment reliability unless it creates an exploitable state.
