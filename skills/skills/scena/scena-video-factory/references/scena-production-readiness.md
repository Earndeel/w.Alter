# Scena Production Readiness Pattern

Use when Lucas asks whether Scena is production-ready, what is missing before launch, or how to onboard SaaS partners safely.

## Current production-ready definition
Scena is production-ready only when all of these are true:

1. Git and deployed Worker are aligned: current prod Worker version maps to a committed/tagged release and rollback target is known.
2. Full tests pass locally (`npm test`) before deploy.
3. Sentinel latest run is `risk_level=low` OR remaining warnings are explicitly historical/accepted.
4. No active stuck media jobs remain unresolved (`video_jobs`/`image_jobs` in `processing`/`submitted` older than threshold).
5. Fresh live Telegram smoke exists: text -> agent, image -> image generation -> delivery, image -> video generation -> delivery marker.
6. Fresh live Scena Connect smoke exists: SaaS `/api/saas/generate` -> provider -> `/webhook/saas/kie` -> signed callback to a real endpoint.
7. Fresh live Stripe smoke exists: checkout -> webhook -> credits ledger update.
8. Monitoring/alerts notify Lucas automatically, not just DB rows.
9. A SaaS partner can receive `SCENA_API_KEY`, integrate from docs, and complete first generation without manual code/DB patching.

## Production readiness audit commands

```bash
cd /root/projects/scena-cloudflare
npm test

git status --short

CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
npx wrangler secret list --name scena-api

CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
npx wrangler d1 execute scena-db --remote --json --command \
"SELECT status, COUNT(*) AS count FROM video_jobs GROUP BY status;
 SELECT status, COUNT(*) AS count FROM image_jobs GROUP BY status;
 SELECT COUNT(*) AS stuck_videos FROM video_jobs WHERE status IN ('processing','submitted') AND datetime(created_at) < datetime('now','-20 minutes');
 SELECT COUNT(*) AS completed_undelivered FROM video_jobs WHERE status='completed' AND COALESCE(output_url,'') != '' AND COALESCE(telegram_message_id,0)=0;"

CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
npx wrangler d1 execute scena-saas-db --remote --json --command \
"SELECT COUNT(*) AS connections FROM saas_connections;
 SELECT status, COUNT(*) AS count FROM saas_jobs GROUP BY status;
 SELECT COUNT(*) AS presets FROM saas_generation_presets WHERE enabled != 0;
 SELECT COUNT(*) AS callbacks FROM saas_job_events WHERE event_type LIKE 'callback%';"

CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
npx wrangler d1 execute scena-ops-db --remote --json --command \
"SELECT status, risk_level, safe_autofix_count, guarded_fix_count, failed_fix_count FROM ops_runs ORDER BY started_at DESC LIMIT 1;
 SELECT status, severity, COUNT(*) AS count FROM ops_incidents GROUP BY status, severity;"
```

## P0 blockers before broad production

- Uncommitted/untracked release changes: commit, tag, and map to Worker version.
- Stuck media jobs: resolve, retry, or archive as historical.
- Sentinel medium/high risk: lower to low or mark accepted historical incidents.
- SaaS Connect lacks partner-grade key lifecycle: rotate/revoke, scopes enforcement, quotas, usage ledger.
- Webhook reliability: signed callbacks need retry/backoff, attempt audit, idempotency key/event id, and replay protection.
- Real external SaaS callback smoke: sandbox presets passing is not enough.
- Alerts: Sentinel should notify Lucas by Telegram/email when risk > low.

## Scena Connect partner-ready requirements

A SaaS partner should receive only:

```txt
SCENA_API_KEY=sk_scena_...
SCENA_WEBHOOK_SECRET=whsec_scena_...
SCENA_BASE_URL=https://api.walter-ai.cloud
```

But before scaling partners, add:
- admin UI to create/list/revoke/rotate connections;
- per-connection quota/rate limit/usage ledger;
- webhook test endpoint + delivery retry/backoff;
- signed webhook verification examples;
- clear pricing mode: BYOK, Scena-refacturation, or hybrid.

## Useful docs in repo

- `docs/production-readiness-checklist.md` — live project checklist created from May 2026 audit.
- `docs/scena-connect-backend-integration.md` — partner-facing API-key integration one-pager.
- `docs/scena-connect.md` — full Scena Connect integration guide.
- `docs/scena-ops-agent.md` — Sentinel/Ops architecture.
