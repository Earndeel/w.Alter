---
name: scena-security
description: Security & data-layer audit methodology for Scena — Cloudflare Workers + D1, multi-tenancy, auth, credits, webhooks, CORS, SSRF. Read-only audit, risk classification P0/P1/P2.
category: devops
tags: [scena, security, audit, cloudflare, d1, serverless]
related_skills: [scena-full-checkup]
---

# Scena Security & Data-Layer Audit

Deep read-only audit of Scena's data and security surface on Cloudflare Workers + D1 + Pages.

## When to use
- User asks for "audit sécurité", "security review", "audit couche données", "data-layer audit"
- Before onboarding new SaaS partners — verify Scena Connect security posture
- After adding new webhook endpoints or provider integrations
- Quarterly security checkpoint

## Audit methodology

Read every .ts source file and .sql schema file. Never modify code. Categorize risks P0 (critical, fix now), P1 (high, fix soon), P2 (moderate, improve).

### 10 audit areas

1. **Wrangler bindings** — `workers/api/wrangler.toml`: D1 bindings, cron triggers, compatibility flags, account_id, secrets vs vars
2. **D1 schemas & migrations** — `d1/schema.sql`, `d1/schema-v2.sql`, `d1/scena-saas-db.sql`, `d1/scena-ops-db.sql`, `d1/migrations/*.sql`, `d1/saas-pipeline-runs.sql`
3. **Multi-tenancy** — `index.ts:handleTelegramWebhook`, `handleMediaProxy`, `saas_connect.ts:authenticateSaasConnection`
4. **Authentication** — `auth.ts` (email/Google/Telegram), `index.ts:handleAdminLogin/validateAdminToken`, `saas_connect.ts:requireAdmin`
5. **Secrets** — Env interface in `index.ts`, `saas_connect.ts:encryptJson/decryptJson`, wrangler secret list, hardcoded fallback keys
6. **Credits/billing** — `agent.ts` credit deduction, `index.ts:handleStripeWebhook`, `handleClientPortal` checkout, admin credit endpoint
7. **Rate limits & quotas** — `index.ts:checkRateLimit`, `saas_connect.ts:enforceSaasPolicy`, `getConnectionPolicy`, concurrent_job_limit enforcement
8. **Webhooks/HMAC/idempotence** — ALL inbound webhook handlers (`/webhook/{kie,piapi,piapi-image,fal-image,saas/*,pipeline/*}`), outbound SaaS webhooks, Stripe webhook
9. **CORS** — `index.ts:ALLOWED_ORIGINS`, `getCorsHeaders`, auth.ts CORS headers, `*.pages.dev` wildcard
10. **SSRF & tenant isolation** — Media proxy URL construction, external fetch targets, callback_url validation, pipeline webhook matching scope

### Risk classification
- **P0**: Exploitable without auth (unsigned webhooks), data corruption (race conditions), blocked deploys (phantom schema)
- **P1**: Secret reuse, plaintext tokens, tenant leak vectors, missing enforcement
- **P2**: CORS violations, public-read files, missing rate limiting on auth endpoints

### Key files to audit (read-only, in order)
```
workers/api/wrangler.toml
d1/schema.sql
d1/schema-v2.sql
d1/scena-saas-db.sql
d1/scena-ops-db.sql
d1/saas-pipeline-runs.sql
d1/saas-connect.sql
d1/migrations/*.sql
d1/workflow-artifacts.sql
d1/image-provider-gpt-image-2.sql
workers/api/src/index.ts         (main Worker — auth, routing, webhooks, credits)
workers/api/src/auth.ts          (email/Google/Telegram auth)
workers/api/src/agent.ts         (credit deduction, tool execution)
workers/api/src/saas_connect.ts  (SaaS auth, HMAC, encryption, quotas)
workers/api/src/pipeline_runner.ts (pipeline webhooks)
workers/api/src/agent_context.ts
workers/api/src/orchestration_config.ts
workers/api/src/tools.ts
```

### Verification discipline

#### Static proof first
1. Trace the route from `fetch()` to its handler and every auth/tenant guard.
2. Trace downstream side effects before issuing any live request: D1 writes, credit reservations, provider calls, callbacks, Telegram delivery.
3. Compare implementation with OpenAPI/docs and frontend call sites. A contract requiring admin auth while the handler omits it is stronger evidence than a speculative exploit.
4. Validate clean bootstrap locally with `scripts/verify-schemas.py`; production schema drift is a separate check.

#### Live production proof — non-mutating by default
Safe probes are `GET /health`, `GET /ping`, authenticated read-only GETs, `OPTIONS`, DNS/TLS checks, and D1 `SELECT`/`PRAGMA` queries. Never assume `{}`, a fake identifier, or a missing field makes a POST harmless: default coercion can turn an "invalid" payload into a real connection, account, job, callback, or provider charge.

Before any production POST/PUT/PATCH/DELETE:
- prove from the current handler that the request exits before every write/external call, **or** use an isolated test environment;
- record the exact cleanup path and verification query first;
- never print returned API keys, webhook secrets, provider tokens, or raw credential rows.

If an audit probe accidentally creates state, stop probing, delete only the exact artifact, verify `COUNT(*) = 0` for that identifier, and document the finding without reproducing credentials.

### Provider webhook remediation gate

For every provider completion/failure callback:

1. Correlate only by the exact provider task ID; an unknown ID must never fall back to the newest pending job.
2. Treat callback fields and output URLs as untrusted until a provider signature is verified or an authenticated provider status/record endpoint confirms them.
3. Return early for already-terminal jobs, then use a conditional D1 terminal transition (`WHERE status NOT IN ('completed', 'failed')`) as the race guard.
4. Require a winning transition (`meta.changes > 0`) before refunds, ledger writes, Telegram delivery, workflow advancement, or outbound customer callbacks.
5. Test forged callback data, terminal replay, unknown IDs, provider-verification failure, and a lost transition race through the real handler path.

See `references/provider-webhook-hardening.md` for the reusable implementation order and behavioral test matrix.

### High-value exploit-chain checks
- Anonymous SaaS connection creation + global provider-key fallback + per-connection quota reset.
- Anonymous registration credits + unsigned Telegram webhook + attacker-controlled chat ID.
- Session signup + body-supplied email + reassignment of an existing client `user_id`.
- Public sequential job lookup returning prompts, media URLs, chat IDs, or provider task IDs.
- Public bot-validation route overwriting another client's Telegram bot binding.
- Stripe HMAC verification without timestamp tolerance or event/payment deduplication.
- Provider webhook completion/failure without signature, replay guard, terminal-state guard, or tenant-scoped lookup.
- Outbound callback URL acceptance that permits arbitrary Worker-side fetches.
- Same-turn parallel tool calls bypassing duplicate/approval checks that only inspect prior messages.
- ReAct loop missing per-tool exception isolation — malformed LLM tool_call crashes entire agent turn, corrupts context, silently fails user. See `references/agent-exception-isolation-audit.md`.

### Agent harness fault-isolation audit (reusable method)

For any LLM-agent codebase with a Reason→Act→Observe loop, audit these five points:

1. **Tool-call parsing** — `toolCall.function.name` and `JSON.parse(arguments)` must each have try/catch (LLM output is non-deterministic).
2. **Tool dispatcher** — the switch/case or handler map must wrap each case in try/catch so one failing tool doesn't kill the batch.
3. **Result collection** — if `toolResults` is pushed *after* the loop, a single exception loses every previously-executed tool's result.
4. **Context save atomicity** — `context.push(user)` and `context.push(assistant)` must both succeed or neither; partial saves corrupt the next turn.
5. **Error surface** — trace the full propagation chain: tool → executeTool → ReAct loop → handleAgentTurn → HTTP handler. A handler that catches nothing + a worker-level `json({error}, 500)` = user sees dead air.

### Pitfalls and false positives
- Do not classify `password === env.ADMIN_SECRET` alone as "plaintext password storage". The durable risks are secret reuse, no rate limit, direct long-lived Bearer compatibility, and credential exposure paths; prove storage separately.
- Secret scanners may redact provider-prefixed identifiers or column names as `***`. Inspect the actual schema/`PRAGMA table_info` before declaring a literal phantom column.
- Missing signatures are only exploitable as claimed when the attacker can reach the route and provide or guess the correlation identifier; distinguish verified exploit chains from hardening gaps.
- A schema that fails from a clean database is a disaster-recovery/deployment blocker, not automatically a remotely exploitable P0.
- CORS must be evaluated with browser preflight, cookie `SameSite`, credential mode, and origin reflection together. `Allow-Credentials` plus a broad origin is a warning, not by itself proof of account compromise.
- Credit operations implemented as `SELECT` then absolute `UPDATE` are non-atomic; check sibling debit, refund, timeout, and ledger paths for the same class.
- Frontend/API drift can hide or expose security controls: inspect method, path, auth transport, field names, callback URLs, and polling/stream endpoints end to end.

See `references/audit-july-2026-baseline.md` for the corrected July 2026 evidence catalog, `references/agent-exception-isolation-audit.md` for the agent harness fault-isolation audit methodology, and `scripts/verify-schemas.py` for deterministic clean-bootstrap checks.
