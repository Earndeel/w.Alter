# Scena P0 hardening session — May 2026

Use this when doing production-readiness work on `/root/projects/scena-cloudflare/`, especially Scena Connect, Sentinel/Ops, or historical job cleanup.

## What changed

Backend hardening added during the session:

- Scena Connect admin key lifecycle:
  - `POST /api/admin/saas/connections/:id/rotate-key`
  - `POST /api/admin/saas/connections/:id/revoke`
- Scena Connect production controls:
  - scopes with `generate` enforcement
  - monthly quota checks
  - per-minute rate limiting
  - usage ledger rows on generation reservation
  - webhook delivery audit records
  - manual retry route `POST /api/admin/saas/webhooks/retry`
  - cron retry via `retryFailedSaasWebhooks(env, 25)` in `scheduled(...)`
- Outbound SaaS callbacks include stronger replay/idempotency metadata:
  - `event_id`
  - `idempotency_key`
  - `X-Scena-Delivery`
  - `X-Scena-Idempotency-Key`
- Scena Sentinel now notifies Lucas by Telegram after daily/manual runs when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_HOME_CHANNEL`/`HOME_CHANNEL` are configured.
- Ops admin has safe historical cleanup route:
  - `POST /api/admin/ops/archive-historical`

## D1 schema additions

`scena-saas-db` gained:

- `saas_connection_limits`
- `saas_usage_ledger`
- `saas_webhook_deliveries`
- `saas_webhook_idempotency`

Apply with the Global Cloudflare key + email:

```bash
cd /root/projects/scena-cloudflare
CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
npx wrangler d1 execute scena-saas-db --remote --file d1/scena-saas-db.sql
```

## Historical cleanup pattern

Use this only for historical noisy rows, not live incidents. It reclassifies stale/failed runtime jobs and archives low/medium open Ops incidents so Sentinel can reflect current risk.

```bash
python3 - <<'PY'
import json, urllib.request
base='https://api.walter-ai.cloud'
ua='Scena-P0-Hardening/1.0'
with urllib.request.urlopen(urllib.request.Request(
    base+'/api/admin/login', method='POST',
    headers={'Content-Type':'application/json','User-Agent':ua},
    data=json.dumps({'password':'«secret:vault»'}).encode()), timeout=30) as r:
    token=json.loads(r.read().decode())['token']
headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':ua}
for path, body in [
    ('/api/admin/ops/archive-historical', {'older_than_days': 7}),
    ('/api/admin/ops/run', {'run_type':'manual_checkup'}),
]:
    req=urllib.request.Request(base+path, method='POST', headers=headers, data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=120) as r:
        print(path, r.status, r.read().decode()[:1000])
PY
```

Expected success shape from the session:

```json
{
  "ok": true,
  "updates": {
    "video_failed": 4,
    "video_stale": 4,
    "image_failed": 35,
    "image_stale": 2,
    "incidents_archived": 2
  }
}
```

Then Sentinel manual run returned:

```json
{
  "status": "completed",
  "risk_level": "low",
  "safe_autofix_count": 0
}
```

## Production drift pitfall

Before writing cleanup SQL, inspect the live D1 schema. In this session, prod `video_jobs` and `image_jobs` did **not** have `updated_at`, even though other tables and local assumptions did. An initial cleanup route failed with:

```txt
D1_ERROR: no such column: updated_at: SQLITE_ERROR
```

Fix was to remove `updated_at = datetime('now')` from `UPDATE video_jobs` / `UPDATE image_jobs` archival SQL and rely on `status` / `error_message` changes only.

Run this before mutating prod:

```bash
CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
npx wrangler d1 execute scena-db --remote --json \
  --command "PRAGMA table_info(video_jobs); PRAGMA table_info(image_jobs);"
```

## Tests and deploy sequence

Recommended sequence:

```bash
cd /root/projects/scena-cloudflare
node --experimental-strip-types --test tests/saas-connect.test.mjs
node --experimental-strip-types --test tests/ops-sentinel.test.mjs
npm test
cd workers/api
CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" \
CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
npx wrangler deploy
```

Session verified:

- `npm test` => `83/83 pass`
- final deployed Worker version: `98f1108f-3fc3-4377-84c3-4ce2737672f9`
- health smoke:
  - `GET /health` => `200`
  - `GET /ping` => `200`
- post-cleanup: `stuck_videos = 0`

## Product status wording

After these hardening steps, Scena backend is closer to beta-private production:

- Scena Chat runtime: Sentinel risk low
- Scena Connect: key lifecycle + quotas + usage + webhook retry/idempotency
- Scena Sentinel: Telegram notification + safe historical archive

Still do not claim full public production readiness until fresh end-to-end real smokes pass:

- Telegram text/image/video generation with delivery marker
- Scena Connect generate → Kie → signed SaaS callback
- Stripe checkout → webhook → credits ledger
- clean commit + release tag tied to the deployed Worker
