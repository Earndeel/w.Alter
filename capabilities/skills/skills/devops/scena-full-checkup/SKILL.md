---
name: scena-full-checkup
description: Complete status check of Scena multi-tenant video agent on Cloudflare
category: devops
tags: [scena, cloudflare, checkup, status]
---

# Scena Full Project Checkup

Complete status check of the Scena multi-tenant video agent factory on Cloudflare.

## When to use
- User asks "where are we" / "checkup" / "état du projet"
- Before major changes to verify current state
- After deployments to confirm everything works

## Steps

### 1. Worker Status
```bash
npx wrangler deployments list --name scena-api
```

### 2. Secrets (current production: ~15)
```bash
npx wrangler secret list --name scena-api
```
Expected core: ADMIN_SECRET, BASE_URL, BETTER_AUTH_SECRET, FAL_API_KEY, GEMINI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, NOUS_PROXY_SECRET, NOUS_PROXY_URL, OPENROUTER_API_KEY, PIAPI_API_KEY, RESEND_API_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN

### 3. D1 Databases
Scena now has three production D1 databases; check all three, not just runtime:

```txt
scena-db       = Scena Chat / Telegram / runtime principal
scena-saas-db  = Scena for SaaS / Scena Connect
scena-ops-db   = Scena Sentinel / Ops / incidents / AI watch
```

```bash
npx wrangler d1 info scena-db
npx wrangler d1 info scena-saas-db
npx wrangler d1 info scena-ops-db

npx wrangler d1 execute scena-db --remote --json --command "SELECT status, COUNT(*) FROM video_jobs GROUP BY status; SELECT status, COUNT(*) FROM image_jobs GROUP BY status;"
npx wrangler d1 execute scena-saas-db --remote --json --command "SELECT COUNT(*) AS connections FROM saas_connections; SELECT status, COUNT(*) FROM saas_jobs GROUP BY status; SELECT COUNT(*) AS presets FROM saas_generation_presets WHERE enabled != 0;"
npx wrangler d1 execute scena-ops-db --remote --json --command "SELECT status, risk_level FROM ops_runs ORDER BY started_at DESC LIMIT 1; SELECT status, severity, COUNT(*) FROM ops_incidents GROUP BY status, severity;"
```

Runtime tables: clients, video_jobs, image_jobs, voice_jobs, credit_ledger, agent_log, bot_pool.
SaaS tables: saas_connections, saas_jobs, saas_job_events, saas_preset_packs, saas_generation_presets.
Ops tables: ops_runs, ops_checks, ops_incidents, ops_repair_actions, ops_research_items, ops_recommendations.

### 4. API Endpoints (via api.walter-ai.cloud)
Test each route with requests:
- GET /health → 200
- GET /ping → 200
- POST /api/admin/login → 200 (with {"password": "«secret:vault»"})
- GET /api/admin/stats, /clients, /jobs, /image-jobs → 200 (with Bearer token)
- GET /api/admin/ops/runs → 200 and latest run should be `completed` with `risk_level=low` for production-ready; `medium` means there are still incidents or historical jobs to triage.
- GET /api/saas/presets with a valid `sk_scena_*` key → 200 with enabled presets. Without a SaaS key, 401 is correct.
- POST /webhook/stripe, /piapi, /piapi-image, /fal-image → 400 (missing data = correct)

### 5. Pages
Three Pages projects: `scena-portal` (scena.walter-ai.cloud), `scena-admin` (admin-scena.walter-ai.cloud), `scena-connect`.

Check each is live and serving the correct content (use extensionless URLs — Pages strips `.html`):
```bash
curl -s https://scena.walter-ai.cloud/login | grep -c 'Continuer avec Google'
curl -s https://scena.walter-ai.cloud/demo | grep -c 'Demo Studio'
curl -s https://admin-scena.walter-ai.cloud/operator | grep -c 'Workflow Lab'
```

### 5b. Auth Verification
```bash
# Google OAuth redirect (must return 302 to accounts.google.com)
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}" https://api.walter-ai.cloud/api/auth/google
# Session check (null when unauthenticated = correct)
curl -s https://api.walter-ai.cloud/api/auth/get-session
```
See `scena-deploy-workflow` → `references/auth-flow-debugging.md` for full OAuth flow and failure patterns.

### 6. DNS
Verify api.walter-ai.cloud → scena-api.lucas-jouvencon.workers.dev (Worker), not cfargotunnel.com (Tunnel).

### 7. Stripe Webhook
```python
r = requests.get("https://api.stripe.com/v1/webhook_endpoints", auth=(STRIPE_KEY, ""))
```
Verify URL = api.walter-ai.cloud/webhook/stripe, status = enabled.

### 8. Security Checks
- Admin without auth → 401
- CORS evil origin → blocked (empty Access-Control-Allow-Origin)
- CORS legit (admin-scena.walter-ai.cloud) → allowed

### 9. Production Readiness Gate
Before saying Scena is production-ready, verify:
- `git status --short` is clean or all production changes are intentionally committed/tagged.
- `npm test` passes.
- runtime DB has no active stuck `video_jobs`/`image_jobs` older than the expected provider window.
- Sentinel latest run is `low` risk or remaining warnings are explicitly archived/historical.
- fresh live smokes exist for Telegram generation, Scena Connect signed callback, and Stripe credits.
- Scena Connect has partner-grade key lifecycle for external SaaS onboarding: rotate/revoke, quotas, usage ledger, webhook retry/backoff, idempotency/replay protection.

See `scena-video-factory` reference `references/scena-production-readiness.md` for the full audit pattern.

## Pitfalls
- D1 requires `--remote` flag for production data
- In this non-interactive environment, `wrangler` may refuse to run without `CLOUDFLARE_API_TOKEN` even if you have the Global API Key. If that happens, use direct Cloudflare REST API calls with `X-Auth-Email` + `X-Auth-Key` to inspect D1, routes, Pages, and deployments.
- Stripe: vault `stripe/rk_live` currently returns 401; use `stripe/sk_live_vaf` (or `sk_live_mcp`) for webhook inspection. Webhook should be `https://api.walter-ai.cloud/webhook/stripe` and enabled.
- Column name in `image_jobs` may literally be `***` in the live D1 schema. Do not assume it is only a display artifact; verify with `PRAGMA table_info(image_jobs)` before patching queries.
- `bot_pool` live schema may differ from older code assumptions; verify with `PRAGMA table_info(bot_pool)` before using insert/update queries.
- Admin routes use hyphens: `/api/admin/image-jobs` not `/api/admin/image_jobs`
- Always test via api.walter-ai.cloud (custom domain), not workers.dev
- Public requests without a real `User-Agent` can hit Cloudflare 1010. Add `User-Agent: Scena/1.0` to curl/Python checks.
