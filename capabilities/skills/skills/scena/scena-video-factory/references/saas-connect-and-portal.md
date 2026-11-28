## Admin UI SaaS Connect (2026-05-25)

Added to `pages/admin/index.html`:
- Nav section: "SaaS Connect" > Connections + Pipelines
- Connections tab: list, detail, create form with BYOK JSON input
- Actions: rotate key, revoke connection
- `loadSaasConnections()` loaded in `loadAll()` alongside other dashboard functions

**Pages deploy**: admin Pages project is `scena-admin` (NOT `admin-scena`). Deploy via:
```bash
npx wrangler pages deploy pages/admin --project-name scena-admin
```
The custom domain is `admin-scena.walter-ai.cloud` but the project name is `scena-admin`.

## Self-Service Portal (2026-05-25)

Portal at `pages/connect/index.html` → deployed to `scena-connect.pages.dev` (Cloudflare Pages project `scena-connect`).

**3-step flow**:
1. Create connection (name, tenant, callback URL, provider, model) — calls `POST /api/saas/connections` (now public, no admin auth)
2. Shows API key + webhook secret (one-time display) + BYOK key config (Kie/Fal)
3. Quickstart code + preset list

**New API endpoints**:
- `POST /api/saas/connections` — now public (portal self-service). Admin auth removed for POST only; GET still requires admin.
- `PATCH /api/saas/connections/:id/keys` — client updates BYOK keys using their API key. Auth: `Authorization: Bearer sk_scena_...`. Validates connection ownership.

**Preset catalog**: 15 presets (expanded from 6). Covers: ugc, cinematic, animation, narrative, docu, image-to-image, social proof, tutorial, before/after, launch, fashion, food, real estate, text-to-video, image-to-video.

**Deploy portal**:
```bash
export CLOUDFLARE_API_TOKEN="$(vault get cloudflare/api_token)"
npx wrangler pages deploy pages/connect --project-name scena-connect
```

**Custom domain**: not yet configured — currently at `scena-connect.pages.dev`. To add custom domain, create DNS CNAME + Pages custom domain mapping.

## Scena Connect / Scena for SaaS (May 2026)

Scena Chat (Telegram multi-tenant flow) must stay intact. Scena for SaaS is an **additive API/connector layer** into the same Scena Engine, not a replacement product.

Current implementation lives in `/root/projects/scena-cloudflare/`:
- `workers/api/src/saas_connect.ts` — SaaS connection auth, preset listing, generate endpoint, Kie callback, outbound signed webhooks.
- `d1/scena-saas-db.sql` — dedicated D1 schema for `scena-saas-db` (`saas_connections`, `saas_jobs`, `saas_job_events`, `saas_preset_packs`, `saas_generation_presets`, `saas_connection_limits`, `saas_usage_ledger`, `saas_webhook_deliveries`, `saas_webhook_idempotency`). `d1/saas-connect.sql` is kept as a backward-compatible schema alias. SaaS tables are intentionally **not** in `d1/schema-v2.sql` anymore.
- `docs/scena-connect.md` — integration guide.
- `docs/scena-connect.openapi.yaml` — OpenAPI spec.
- `examples/scena-connect-client.mjs` — minimal SaaS client.
- `examples/scena-connect-webhook-verifier.mjs` — HMAC verifier.
- `tests/saas-connect.test.mjs` — regression tests.

Production endpoints:
- `POST /api/saas/connections` admin creates a SaaS connection and one-time `sk_scena_...` API key.
- `POST /api/admin/saas/connections/:id/rotate-key` rotates a SaaS API key and returns the new one-time key.
- `POST /api/admin/saas/connections/:id/revoke` revokes/suspends a SaaS connection.
- `GET /api/admin/saas/usage` inspects usage ledger rows by connection.
- `POST /api/admin/saas/webhooks/retry` retries failed outbound SaaS callbacks.
- `GET /api/saas/presets` lists plug-and-play presets.
- `POST /api/saas/generate` submits generation jobs from external SaaS UIs.
- `GET /api/saas/jobs/:id` returns job status.
- `POST /api/saas/webhook-test` sends a signed test callback.
- `POST /webhook/saas/kie` receives Kie async completion for SaaS jobs.

Sandbox credentials are stored in the vault:
```bash
vault get scena_connect/sandbox_api_key
vault get scena_connect/sandbox_webhook_secret
```

Default provider is Kie.ai `bytedance/seedance-2-fast` for video. Default image provider is Kie.ai GPT Image 2 (`gpt-image-2-text-to-image` for text-to-image, `gpt-image-2-image-to-image` when a reference image is present). `z-image` is cheap and useful for manual tests/benchmarks, but should not be selected as the production image provider.

Provider payload contracts are centralized in `workers/api/src/provider_payloads.ts`, with a human reference in `docs/provider-payload-contracts.md`. Active contracts cover Kie Seedance 2/Fast, Kie GPT Image 2 T2I/I2I, Kie Z-Image test payloads, Fal Grok video T2V/I2V, Fal Nano Banana 2/edit, and Flux Dev I2I resize fallback. Always sanitize route/body params through this module before outbound provider calls.

Critical rules:
- Scena for SaaS uses a dedicated D1 database `scena-saas-db` bound as `SAAS_DB` in the Worker (`database_id=8c47d5d8-23b5-4896-b003-059a9fdc3391`). Scena Connect code should read/write `SAAS_DB` via its helper and only fall back to `DB` for old local/dev tests. Do not add SaaS tables back into `schema-v2.sql` / runtime `scena-db`.
- Do not store/copy client SaaS DB records. Store only external IDs, connection config, encrypted credentials, job metadata, event logs, provider metadata.
- Outbound callbacks must be HMAC signed with `X-Scena-Signature = sha256(HMAC(webhook_secret, timestamp.rawBody))`.
- Outbound callbacks should be delivery-tracked and replay-safe: persist a delivery attempt row, include `event_id` + `idempotency_key` in the JSON body, include `X-Scena-Delivery` + `X-Scena-Idempotency-Key` headers, and retry failed callbacks via cron/admin route rather than fire-and-forget.
- Enforce partner controls before provider submission: connection `status`, `generate` scope, monthly credit limit, and per-minute rate limit. Record reserved credits in `saas_usage_ledger` at job creation.
- Keep Telegram tests green after SaaS changes; SaaS layer must remain additive.
- Test command: `node --experimental-strip-types --test tests/saas-connect.test.mjs tests/orchestration-config.test.mjs tests/worker-regressions.test.mjs` and preferably full `npm test` before deploy.
