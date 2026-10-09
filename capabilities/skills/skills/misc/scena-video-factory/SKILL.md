---
name: scena-video-factory
description: Multi-tenant AI video agent factory V3 — Scena. Cloudflare Workers + D1, PiAPI webhook flow, multi-tenant Telegram routing, Better Auth, Stripe billing. Kimi 2.6 orchestrator via OpenRouter. FREE TIER architecture.
category: devops
---

# Scena Video Agent Factory V2

**Reference files:** `references/gemini-veo-integration.md` — Veo 3.1 Lite via Gemini API (SDK, polling, pricing, Scena integration plan)
`references/pipeline-api-contracts.md` — Full API contracts for POST /api/saas/pipeline, status polling, webhook events, step definitions, BYOK.
`references/workflow-lab-client-demo-may-2026.md` — Client demo + Workflow Lab pattern: demo page, per-step admin controls, Seedance payload preview endpoint, tests, HTML-writing verification.

## Architecture

```
/root/projects/video-agents-factory/
├── factory.py                      ← CLI (create/list/credits/start/stop/health/stats)
├── shared/pricing.json             ← Model costs × margin multiplier
│
├── admin/
│   ├── admin_db.py                 ← Central DB (clients, ledger, model_config, fal_endpoints, errors)
│   ├── supervisor.py               ← Process manager (auto-restart, health check)
│   ├── stripe_billing.py           ← Stripe (customers, checkout, webhooks)
│   ├── telegram_provisioning.py    ← Bot token validation
│   ├── bot_pool.py                 ← Pre-created Telegram bots pool
│   ├── tunnel_manager.py           ← Cloudflare tunnels
│   ├── dns_manager.py              ← DNS record management
│   ├── webhook_server.py           ← Stripe + Clerk signup webhooks (port 5051)
│   ├── auth.py                     ← Admin dashboard auth (session cookie, NO Basic Auth)
│   └── dashboard/                  ← Admin web UI (port 5050)
│       ├── run.py
│       └── templates/
│           ├── index.html          ← 8 tabs: Overview, Clients, Integrations, Models, Bots, LLM Config, Settings, Errors
│           └── login.html          ← Admin login page (dark theme)
│
├── landing/
│   ├── index.html                  ← Landing page (Cloudflare Pages)
│   └── login.html                  ← Client auth (Clerk SDK)
│
└── client_template/                ← Copied per client on signup
    ├── agent.py                    ← 🧠 Scena tool-calling agent
    ├── persona.md                  ← Personality (concise, sarcastic, pro)
    ├── memory.py                   ← Persistent client memory (JSON)
    ├── pipeline/
    │   ├── analyzer.py             ← Need analysis (reads model from DB)
    │   ├── planner.py              ← Action plan (reads model from DB)
    │   ├── generator.py            ← Payload gen (reads Fal endpoints from DB)
    │   ├── extender.py             ← Video extension (>15s via I2V last-frame)
    │   └── orchestrator.py         ← 4-stage orchestrator
    ├── tools/
    │   ├── scena_tools.py          ← Tool registry (LLM sees these)
    │   ├── media.py                ← Video/image analysis, frame extraction
    │   ├── generator.py            ← Video generation via Fal.ai
    │   ├── image_gen.py            ← Image generation
    │   ├── characters.py           ← Character sheet CRUD
    │   ├── asset_preprocessor.py   ← Upload to Fal.ai, frame extraction, model-specific formatting
    │   └── postprocess/
    │       └── postprocessor.py    ← ffmpeg (subtitles, filters), TTS, lipsync, concat
    ├── dashboard/                  ← Per-client Flask dashboard (unique port)
    ├── models/                     ← Per-client model configs
    ├── assets/                     ← Client uploads
    ├── characters/                 ← Character sheets
    ├── db/pipeline.db              ← Per-client SQLite
    └── memory.json                 ← Persistent memory
```

## Current State (May 2026) — V3 Cloudflare Worker

**Active deployment:** `/root/projects/scena-cloudflare/` — Cloudflare Workers + D1 + Pages.

### Recent Migrations
- **Clerk → Better Auth** (May 2, 2026): All Clerk code removed. Better Auth via cookie sessions. No `clerk_id` column in D1. `handleClientPortal()` uses only Better Auth.
- **Gemini → Kimi 2.6 via OpenRouter** (May 2, 2026): All Gemini API converters deleted. SCENA_TOOLS are already OpenRouter-compatible format. `callKimi()` orchestrator function targets `moonshotai/kimi-k2.6` via `https://openrouter.ai/api/v1/chat/completions`. Vision analysis uses `analyzeWithVision()` via OpenRouter. CompactContext and batch expansion also migrated to OpenRouter.

**LLM stack (current):**
```
💬 Agent conversation → moonshotai/kimi-k2.6 (OpenRouter)
🔍 Vision analysis    → moonshotai/kimi-k2.6 (OpenRouter, native vision)
📋 Planning/analysis  → moonshotai/kimi-k2.6 (OpenRouter)
```
No Gemini API key needed. No format converters. Tools pass through natively.

## Pipeline runner (2026-05-25)

Autonomous video generation pipeline: `workers/api/src/pipeline_runner.ts` (42KB).

**Architecture**: State machine pattern for Cloudflare Workers. Sync steps (analysis, sheets, storyboard) execute immediately. Async steps (Kie Seedance video) submit and return `waiting_async`, resume via webhook.

**Endpoints**:
- `POST /api/saas/pipeline` — launch full pipeline (source_video_url + brief + params)
- `GET /api/saas/pipeline/:id/status` — poll status
- `POST /webhook/pipeline/kie-video` — resume after async video gen

**Pipeline steps**: ingest_inputs → validate_source → source_analysis → modification_plan → generate_sheets → generate_storyboard → compile_clips → submit_generation → qa_validation → export_package

**BYOK**: Already wired in `saas_connect.ts` — `encrypted_provider_keys_json` is stored per connection, decrypted by `getProviderKeys()`, used in `submitKieVideoJob` with fallback to global env keys.

**Provider integration**:
- Gemini analysis → OpenRouter `google/gemini-2.5-flash` with `video_url` content type
- Kie image gen (sheets/storyboard) → synchronous poll (30 attempts × 2s)
- Kie video gen → async submit, webhook resume at `/webhook/pipeline/kie-video`

**Progression webhooks**: Sent to `callback_url` at each step boundary. Events: `pipeline.started`, `step.started`, `step.completed`, `step.failed`, `pipeline.completed`, `pipeline.failed`. HMAC-SHA256 signed.

**D1 table**: `saas_pipeline_runs` — see `d1/saas-pipeline-runs.sql`.

**Tests**: `tests/pipeline-runner.test.mjs` — 8/8 pass. Covers validation, status 404, webhook rejection, full sync flow, graceful failure, progression webhooks.

**Smoke test 2026-05-25**: Full end-to-end pipeline completed successfully.
- Source: MDN flower.mp4 → Parfum Noir product reveal
- Gemini source_analysis ✅, modification_plan ✅
- Sheets: failed (subrequest limit) — non-fatal, continued
- Storyboard: skipped (non-fatal) — continued
- 1 clip compiled, submitted to Kie Seedance 2 Fast
- Kie webhook callback received → pipeline resumed → QA → export → completed
- 165 Kie credits consumed, 123s processing time
- Total pipeline duration: ~4 minutes
- Video URL extracted from `resultJson.resultUrls[0]`

**Provider stack (2026-05-25)**: Fal.ai + Kie.ai are both supported. OpenRouter is used for LLM analysis/planning. Client-facing UI should keep provider/model choice simple, but the backend may route to Fal or Kie for tests/legacy workflows. See `references/fal-kie-pipeline-repair.md` for the repaired dual-provider contract.
- Fal image gen: `fal-ai/nano-banana-2` (T2I), `fal-ai/nano-banana-2/edit` (I2I, `image_urls` ARRAY)
- Fal video gen: `fal-ai/veo3` (T2V), `fal-ai/minimax-video/video-01-live` (I2V with `image_url`)
- Kie video test/legacy gen: `bytedance/seedance-2-fast`
- Kie image test/legacy gen: GPT Image 2 adapters via `provider_payloads.ts`
- Auth: Fal uses `Authorization: Key <FAL_API_KEY>`; Kie uses Bearer.
- Pipeline webhooks: `/webhook/pipeline/fal-video` and `/webhook/pipeline/kie-video`
- SaaS provider webhooks: `/webhook/saas/fal` and `/webhook/saas/kie`
- BYOK: decrypt `encrypted_provider_keys_json` using AES-GCM envelope `v1.<iv>.<ciphertext>` and prefer client `fal`/`kie` keys over env keys.

**Known pitfall**: Cloudflare Workers subrequest limit (1000/invocation). Fal polling (15 attempts × 3s) + OpenRouter calls + validation = ~30-50 subrequests per step. Sheets/storyboard are non-fatal to avoid hitting the limit.

**Node.js TypeScript pitfall**: `Record<string, string>` and generic types with angle brackets break `node --experimental-strip-types`. Use `{ [key: string]: string }` instead. Same for `Record<string, Handler>` → `{ [key: string]: Handler }`. This affects all `.ts` files imported from `.mjs` test files.

**Kie→Fal/Fal+Kie migration (2026-05-25)**: Do not remove Kie blindly. Scena can run dual-provider: Fal for the main pipeline and Kie for tests/legacy generation. Keep the provider adapters explicit and route by connection/workflow:

- `/api/saas/generate`: support `submitKieVideoJob`, `submitKieImageJob`, `submitFalVideoJob`, `submitFalImageJob`.
- Pipeline async callbacks: register both `/webhook/pipeline/fal-video` and `/webhook/pipeline/kie-video` in `index.ts`.
- SaaS provider callbacks: register both `/webhook/saas/fal` and `/webhook/saas/kie`.
- `createConnection`: default provider should derive from supplied provider keys (`fal` if Fal key present, otherwise Kie fallback) unless explicitly set.
- For generated artifacts, never leave stale metadata (`provider: 'kie'`) when using Fal; status matching/debugging depends on it.
- Regression checks: `tests/saas-connect.test.mjs` and `tests/pipeline-runner.test.mjs` must both pass before broader `npm test`.
```
POST https://queue.fal.run/{endpoint} → { request_id, status: "IN_QUEUE" }
GET  https://queue.fal.run/{endpoint}/requests/{request_id} → 200 (done) or 202 (processing) or 422 (failed)
```

**Auth**: `Authorization: Key {FAL_API_KEY}` (NOT Bearer)

**Node.js pitfall**: `Record<string, string>` and other generic types (`Partial<>`, etc.) cause `ERR_INVALID_TYPESCRIPT_SYNTAX` with `node --experimental-strip-types`. Replace with `{ [key: string]: string }` in .ts files that are imported by .mjs tests.

**Kie.ai video URL extraction** (legacy, still relevant for saas_connect.ts jobs): Kie returns URLs in `resultJson` as a JSON string with `resultUrls[]`, NOT in `output.video_url`.

**Video validation — HEAD not reliable**: Some CDNs (Google Cloud Storage, S3 presigned URLs) reject HEAD requests with 403/405. Pipeline `validate_source` step must try HEAD first, then fall back to GET with `Range: bytes=0-0` header. Both failing = video truly inaccessible.

**Pages project naming**: `scena-admin` (NOT `admin-scena`), `scena-connect` (new). Project names don't match custom domains. Always check with `wrangler pages project list` before deploying.

**Second smoke test (2026-05-25)**: Pipeline `pipe_mpl5h0ow_1irm9x` completed successfully after the video URL extraction fix. Video URL properly extracted from `resultJson.resultUrls[0]`. Duration ~3 min, Kie Seedance 2 Fast.

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

## Locked decisions
- `POST /api/saas/pipeline` with flower.mp4 → 202, 7 steps completed, status `waiting_async`
- Steps completed: ingest_inputs → validate_source → source_analysis → modification_plan → generate_sheets → generate_storyboard → compile_clips
- Kie Seedance video submitted, waiting for webhook resume
- Sheets/storyboard are non-fatal (pipeline continues if Kie image gen hits subrequest limit)

**Admin secret**: Stored as Worker secret (not in vault). Use `vault get scena_connect/sandbox_api_key` for SaaS API testing.

## Key Architecture Decisions

### Tool-Calling Agent (Kimi 2.6 as Orchestrator)
Scena is a PROPER agent — the LLM decides which tools to call, not hardcoded logic.

```
Client message → LLM (MiMo V2 Pro)
  → LLM sees tool descriptions in system prompt
  → LLM responds with JSON: {"tool": "tool_name", "params": {...}}
  → Agent executes tool
  → Result fed back to LLM
  → LLM synthesizes natural response
  → Message sent to client
```

**Available tools the LLM can call:**
```
analyze_image              → visual analysis of image
analyze_video              → video analysis (frames, style, motion)
generate_image             → image generation (Fal.ai)
generate_video             → video generation (Fal.ai)
estimate_cost              → estimate before generating
create_character           → create reusable character sheet
generate_character         → generate character image
list_characters            → view saved characters
remember                   → save info to memory
recall                     → retrieve from memory
check_balance              → check credits
get_time                   → date/time
upload_asset               → upload local file → Fal.ai public URL
extract_reference_frames   → extract video frames → upload → URLs
prepare_for_model          → auto-format assets for specific model
```

### LLM Configuration (Kimi 2.6 via OpenRouter — May 2026)
**Migrated from Gemini API → OpenRouter with Kimi 2.6.** No Gemini API key needed.

```
💬 Conversation (orchestrator) → moonshotai/kimi-k2.6 (OpenRouter)
🔍 Need analysis               → moonshotai/kimi-k2.6 (OpenRouter)
📋 Planning                    → moonshotai/kimi-k2.6 (OpenRouter)
🎬 Payload generation          → moonshotai/kimi-k2.6 (OpenRouter)
🖼️ Image/video analysis        → moonshotai/kimi-k2.6 (OpenRouter, native vision)
```

**API endpoint:** `https://openrouter.ai/api/v1/chat/completions`
**Auth:** `Authorization: Bearer {OPENROUTER_API_KEY}`

**Key advantage over Gemini:** SCENA_TOOLS are already in OpenAI/OpenRouter format (`type: "function"` with `function.name`, `function.description`, `function.parameters`). NO converters needed. Messages use standard `system/user/assistant/tool` roles. Response parsing is standard `data.choices[0].message`.

### OpenRouter Format (No Converters Needed)
SCENA_TOOLS already follow OpenAI function-calling spec:
```typescript
{
  type: "function",
  function: {
    name: "generate_video",
    description: "...",
    parameters: { type: "object", properties: {...}, required: [...] }
  }
}
```

Messages use standard roles: `system`, `user`, `assistant`, `tool`. The `callKimi()` function is a thin wrapper around OpenRouter's chat completions endpoint — no format translation needed. This is much simpler than Gemini's API which required uppercase types, `model` role, `functionResponse` wrappers, and `thoughtSignature` round-trips.

### Gemini Format Converters (DELETED — May 2026)

All Gemini format converters were removed during the Kimi migration:
- `convertToolsToGemini()` — deleted (SCENA_TOOLS already OpenRouter-compatible)
- `convertMessagesToGemini()` — deleted (standard roles work natively)
- `parseGeminiResponse()` — deleted (standard `choices[0].message` parsing)

The Gemini-specific pitfalls below (thoughtSignature round-trip, uppercase types, functionResponse name matching, integer enums) are **no longer relevant** for the current codebase but kept for reference if Gemini is ever brought back.

### Fal.ai Endpoint Registry (Admin Dashboard → LLM Config → Endpoints)
Each Fal.ai endpoint is stored in DB with its FULL schema. The LLM payload generator receives all endpoints + schemas to choose the right one and generate conformant JSON.

```
Admin → LLM Config → Registre des endpoints Fal.ai
  + Ajouter  → modal with: ID, name, endpoint, category, use_case, $/s or $/img, schema JSON
  Edit       → modal pre-filled with all fields
  Delete     → remove endpoint
```

Schema JSON example for Seedance Reference:
```json
{
  "prompt": {"type": "string", "required": true, "desc": "English scene description"},
  "reference_image_urls": {"type": "array<string>", "required": true, "desc": "Public URLs from Fal.ai upload"},
  "aspect_ratio": {"type": "string", "default": "auto", "options": ["16:9", "9:16", "1:1"]},
  "resolution": {"type": "string", "default": "720p", "options": ["480p", "720p"]},
  "duration": {"type": "string", "default": "5", "options": ["5", "10"]}
}
```

### Asset Preprocessor (for Seedance Reference and I2V models)
Models need public URLs, not local files. The preprocessor handles this:

```python
# Seedance Reference flow:
# 1. Client sends a reference video
frames = preprocessor.extract_reference_frames(video_path, num_frames=4)  # ffmpeg
urls = [preprocessor.upload_image(f) for f in frames]  # → Fal.ai storage URLs
# 2. URLs go into reference_image_urls parameter
# 3. Seedance generates video with same style/character
```

### Video Extension (>15s)
Models max at 15s. Extension strategy:
1. Generate first segment (T2V)
2. Extract last frame via ffmpeg (0.5s before end)
3. Upload last frame → get URL
4. Generate next segment (I2V endpoint with last_frame_url)
5. Repeat until target duration
6. Concat all segments via ffmpeg concat demuxer

### Client Matricule System
Clients get matricules (sc0001, sc0002...) instead of names in URLs:
```
Dashboard: https://app-sc0002.walter-ai.cloud
```
Admin DB stores matricule per client. Generated on signup via auto-increment.

## Network Setup

### Cloudflare Named Tunnels (Production — NOT trycloudflare)

CNAME records CANNOT point to trycloudflare.com. Must use named tunnels with cfargotunnel.com.

```bash
# 1. Create tunnel via API
curl -X POST "https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel" \
  -H "Authorization: Bearer {token}" \
  -d '{"name": "scena-main"}'
# → saves tunnel_id, credentials in result

# 2. Save credentials
# ~/.cloudflared/{tunnel_id}.json

# 3. Write config.yml
cat > /root/.cloudflared/config.yml << EOF
tunnel: {tunnel_id}
credentials-file: /root/.cloudflared/{tunnel_id}.json
ingress:
  - hostname: admin-scena.walter-ai.cloud
    service: http://localhost:5050
  - hostname: api.walter-ai.cloud
    service: http://localhost:5051
  - hostname: app-sc0002.walter-ai.cloud
    service: http://localhost:5102
  - service: http_status:404
EOF

# 4. Create CNAME records
# POST /zones/{zone_id}/dns_records
# {"type":"CNAME","name":"admin-scena","content":"{tunnel_id}.cfargotunnel.com","proxied":true}

# 5. Systemd service
cat > /etc/systemd/system/scena-tunnel.service << EOF
[Unit]
Description=Cloudflare Tunnel for Scena
After=network.target
[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable scena-tunnel && systemctl restart scena-tunnel
```

### Clerk Auth (Client Portal) — REMOVED May 2026

**Clerk has been completely replaced by Better Auth.** All Clerk code, constants, JWKS verification, `clerk_id` column, and metadata references were removed on May 2, 2026. The content below is kept for historical reference only.

### Clerk Auth (Client Portal) — HISTORICAL
Clerk SDK MUST be loaded from jsdelivr — the Clerk domain CDN (`clerk.accounts.dev/npm/...`) doesn't serve the SDK.

```html
<script>
var CLERK_PK = 'pk_test_...';

// Load from jsdelivr (NOT from clerk.accounts.dev)
var s = document.createElement('script');
s.async = false;
s.src = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
document.head.appendChild(s);

s.onload = function() {
    // Must POLL for window.Clerk — not available immediately on onload
    var iv = setInterval(function() {
        if (window.Clerk) {
            clearInterval(iv);
            initClerk();
        }
    }, 100);
};

async function initClerk() {
    await window.Clerk.load({publishableKey: CLERK_PK});
    if (window.Clerk.user) {
        showPortal(window.Clerk.user);
    } else {
        window.Clerk.mountSignIn(document.getElementById('clerk-mount'), {
            afterSignInUrl: window.location.href,
            afterSignUpUrl: window.location.href
        });
    }
}
</script>
```

Key lessons:
- **DO NOT** use `s.onload = function() { window.Clerk.load() }` — `window.Clerk` is undefined at that point
- **DO** poll with `setInterval` checking for `window.Clerk`
- **DO** use `cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js` (NOT clerk domain)
- After sign-in: call `/api/signup` with `clerk_id` + `name` + `email` → auto-provision bot + credits + matricule

### Bot Pool
Pre-create bots via @BotFather, store tokens in pool:
```bash
python3 bot_pool.py add --token "123:ABC" --name "Slot 1"
```
On signup, `assign_bot()` grabs next available → client gets `https://t.me/{username}`.

### Admin Auth (NO Basic Auth popup)
Custom login page with session cookie. The key fix: DON'T return `WWW-Authenticate: Basic` header — it triggers Chrome's native popup.

```python
@app.before_request
def before_auth():
    path = request.path
    # Public routes
    if path in ("/", "/api/auth/login", "/api/auth/logout", "/favicon.ico", "/health"):
        return None
    if not _is_authenticated(request):
        # API → JSON 401 (NO WWW-Authenticate header!)
        if path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        # Browser → redirect to login page
        return redirect("/")
```

Login page (`login.html`): dark themed form with username/password fields, inline error display (no `alert()`). On success: `document.cookie = 'scena_admin_token=' + token + ';path=/;max-age=86400'` then `window.location.href = '/dashboard'`.

## CLI Commands
```bash
python3 factory.py create --name "ClientX" --email "x@mail.com" --telegram-token "..." --credits 500
python3 factory.py agent --client clientx    # start agent
python3 factory.py start --client clientx    # start dashboard + tunnel
python3 factory.py credits --client clientx --add 500
python3 factory.py credits --client clientx --ledger
python3 factory.py list / health / stats / errors
python3 bot_pool.py add --token "..." --name "Slot 1"
python3 bot_pool.py list
```

## Production URLs
```
Landing:     https://scena.walter-ai.cloud       (Cloudflare Pages)
Login:       https://scena.walter-ai.cloud/login.html (Clerk)
Admin:       https://admin-scena.walter-ai.cloud  (tunnel, auth required)
Webhook:     https://api.walter-ai.cloud          (tunnel, public)
Dashboard:   https://app-sc000X.walter-ai.cloud   (tunnel, per client)
```

## API Keys (.env)
```
FAL_KEY=...
OPENROUTER_API_KEY=...
PIAPI_API_KEY=77a21faddd5fddbc661e26472dc1c482480c627c36fc08c96bcaf6573e33e197
CLOUDFLARE_API_TOKEN=cfut_...  (scoped, limited permissions)
CLOUDFLARE_GLOBAL_KEY=«secret:vault»  (full access)
CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com
CLOUDFLARE_ACCOUNT_ID=«secret:vault»
CLOUDFLARE_ZONE_ID=ba01ee08564dc4b2f66fa60b968a75f8
STRIPE_SECRET_KEY=...
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
ADMIN_USER=scena
ADMIN_PASS=«secret:vault»
```

## Cloudflare Serverless Architecture (V3 — Active Development)

**MIGRATING FROM Flask/VM → Cloudflare Workers + D1 + Pages.**

### Project Structure
```
/root/projects/scena-cloudflare/
├── workers/api/
│   ├── wrangler.toml          ← Worker config (D1 binding, env vars)
│   └── src/index.ts           ← Main Worker (all API routes)
├── d1/
│   └── schema.sql             ← D1 tables (clients, credit_ledger, video_jobs)
└── pages/admin/
    └── index.html             ← Admin dashboard (Cloudflare Pages)
```

### Deployed Resources
```
Worker:     scena-api → https://scena-api.lucas-jouvencon.workers.dev
Route:      api.walter-ai.cloud/* → scena-api
D1 DB:      scena-db (id: 3567d347-37d7-45d5-b348-3dfc5f674006)
Pages:      scena-admin.pages.dev → admin dashboard
```

### Multi-Tenant Telegram Routing (KEY ARCHITECTURE)
Each client has their OWN Telegram bot. Webhook URL includes matricule:
```
https://api.walter-ai.cloud/webhook/telegram/{matricule}
```
When Telegram sends an update, the Worker extracts `matricule` from URL path,
looks up client in D1 by matricule, and routes to their bot token.

**Bot validation flow:**
1. Client provides their bot token + matricule
2. Worker calls Telegram `getMe` to validate
3. Worker calls `setWebhook` with URL `https://api.walter-ai.cloud/webhook/telegram/{matricule}`
4. Saves token + username to D1 `clients` table

**Test command (Ping/Pong):**
```
Client sends /ping → Worker reads client from D1 → sends back client info + Worker status
```

### PiAPI Integration (Replaced Fal.ai)
**Unified API:** 2 endpoints for ALL models:
```
POST https://api.piapi.ai/api/v1/task      → create task
GET  https://api.piapi.ai/api/v1/task/{id}  → check status/result
```

Auth: `X-API-Key` header + **MUST include `User-Agent` header** (Cloudflare blocks requests without it — error 1010).

**Critical provider mapping note:** PiAPI is NOT fully uniform across providers.
For Dreamina Seedance, the correct request shape is:
```json
{
  "model": "seedance",
  "task_type": "seedance-2-fast",
  "input": {
    "prompt": "scene description",
    "duration": 5,
    "aspect_ratio": "9:16",
    "mode": "text_to_video"
  }
}
```

So in Scena admin routes you can keep `model_id = seedance-2-fast` or `seedance-2`, but the Worker must translate before calling PiAPI:
- `seedance-2-fast` → `model: "seedance"`, `task_type: "seedance-2-fast"`
- `seedance-2` → `model: "seedance"`, `task_type: "seedance-2"`

If you send `model: "seedance-2-fast"`, PiAPI returns:
- `invalid model: seedance-2-fast`

**Status:** Completed, Processing, Pending, Failed, Staged

### Async Video Flow (FREE TIER — No Queues)
Uses PiAPI native webhooks instead of Cloudflare Queues:

```
1. Client sends image+text on Telegram
2. Worker creates job in D1 (status=processing)
3. Worker calls PiAPI with config.webhook_config = "https://api.walter-ai.cloud/webhook/piapi"
4. Worker responds to Telegram immediately: "Rendu en cours 🍿"
5. PiAPI generates video (1-3 min)
6. PiAPI POST to /webhook/piapi with result
7. Worker updates D1 (status=completed)
8. Worker calls Telegram sendVideo → video delivered to client
```

### Available Models on PiAPI (with ELO rankings from Artificial Analysis)
```
Kling 3.0 Pro       → model:"kling" version:"3.0" mode:"pro"  → ELO 1243, $0.15-0.20/s
Kling 3.0 Std       → model:"kling" version:"3.0" mode:"std"  → ELO 1216, $0.10-0.15/s
Kling 3.0 Omni      → model:"kling" task_type:"omni_video_generation" → ELO 1230
Kling Turbo         → model:"kling-turbo"                      → ELO 1213, $0.28/5s
Seedance 2.0 Fast   → model:"seedance-2-fast"                  → $0.10/s
Seedance 2.0        → model:"seedance-2"                       → $0.13/s
Veo 3               → model:"veo3"                             → ELO 1219, $0.06-0.24/s
Veo 3.1 Fast        → model:"veo3-video-fast"                  → ELO 1211, $0.06/s
Sora 2 Pro          → model:"sora2"                            → ELO 1195
Wan 2.6             → model:"wan"                              → ELO 1186
Hailuo              → model:"hailuo"                           → ELO 1183
Hunyuan             → model:"hunyuan"                          → ELO 1014
```

### Wrangler Deploy (Cloudflare Global Key)
**Scoped API tokens DON'T work for D1/Workers creation.** Must use Global API Key:
```bash
CLOUDFLARE_API_KEY=«secret:vault» \
CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com \
wrangler deploy
```

For D1 operations:
```bash
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com \
wrangler d1 execute scena-db --command="SELECT * FROM clients;" --remote
```

## Agent Brain (Phase 3 — ReAct Multi-Agent Architecture)

### Pattern: Reason → Act → Observe → Reason → ...

Agent.ts implements a ReAct loop instead of single-shot tool calling:

```typescript
for (let iteration = 0; iteration < MAX_REACT_ITERATIONS; iteration++) {
  const response = await callMimo(env, systemPrompt, messages);
  const { cleanContent, thought } = parseInternalThought(response.content);

  // No tool calls → final text response
  if (!response.tool_calls?.length) { finalResponse = cleanContent; break; }

  // Execute ALL tool calls (not just [0])
  for (const toolCall of response.tool_calls) {
    const result = await executeTool(env, clientId, matricule, toolCall, chatId, botToken);
    toolResults.push(result);
  }

  // Feed results back → re-call LLM
  messages.push({ role: "assistant", content: cleanContent, tool_calls: response.tool_calls });
  for (let i = 0; i < response.tool_calls.length; i++) {
    messages.push({ role: "tool", content: JSON.stringify(toolResults[i]), tool_call_id: response.tool_calls[i].id });
  }

  // Async tools (generate_*) stop the loop — result comes via webhook
  if (hasAsyncTool) break;
}
```

### internal_thought (obligatory before every action)

System prompt forces Mimo to generate a JSON block before each response/tool call:

```json
{
  "internal_thought": {
    "analyse": "What the client wants",
    "variables_manquantes": ["style", "format"],
    "risques": ["wrong ratio", "provider failure"],
    "plan": ["1. Validate image", "2. Resize if needed", "3. Generate video", "4. Validate"],
    "prochaine_action": "consultation | appel_outil_X | validation_client"
  }
}
```

Parser extracts from markdown code block or inline JSON, strips from visible content.

### Tool Chaining

Agent can chain sync tools autonomously (validate → resize → generate). Stops on:
- `generate_image`/`generate_video`/`generate_voice` (async, webhook callback)
- `mark_project_complete` (final)
- Max 4 iterations reached

### Tools (v3 — ReAct)
```
validate_media(media_url, expected_ratio, media_type)  → HEAD check + metadata
resize_image(image_url, aspect_ratio, strategy)        → Fal.ai I2I crop
generate_image(prompt, style, image_ref_url)           → Fal.ai NanoBanana 2
generate_video(prompt, image_ref_url, duration, ratio) → PiAPI Seedance
generate_voice(text, emotion)                          → TTS (TODO)
mark_project_complete(final_media_url, media_type)     → Archive + reset
```

### Security (added in Phase 3)

**Admin auth** — Login form → `/api/admin/login` → HMAC token (4h) → sessionStorage. NO secret in HTML.
```typescript
// Token = base64("admin:expiresAt") + "." + HMAC-SHA256(secret, "admin:expiresAt")
async function handleAdminLogin(request, env) { ... }
async function validateAdminToken(token, env) { ... }
// API accepts both direct secret (CLI) and session token (UI)
```

**Stripe webhook** — HMAC-SHA256 signature verification via Web Crypto API:
```typescript
const sig = request.headers.get("Stripe-Signature");
// Parse t=xxx,v1=xxx
// Compute HMAC-SHA256(`${t}.${rawBody}`, STRIPE_WEBHOOK_SECRET)
// Compare with v1
```

**CORS** — Whitelist, NOT wildcard:
```typescript
const ALLOWED_ORIGINS = ["https://admin-scena.walter-ai.cloud", "https://scena.walter-ai.cloud", ...];
```

**Rate limiting** — D1-based per client per minute:
```typescript
// Check agent_log count for client in last 60s
// If > 15 → return 429
```

## Agent Brain (Phase 2 — Multi-Modal Autonomous Agent)

### Architecture
Worker becomes a state machine driven by webhooks. Agent uses OpenRouter (Mimo v2 Pro) for conversation + tool calling, and OpenRouter (Gemini 3 Flash) for vision analysis. NO direct Gemini API key needed.

### D1 Schema v2 (Agent State Machine)
```sql
ALTER TABLE clients ADD COLUMN state TEXT DEFAULT 'idle';      -- idle, waiting_image, waiting_video, waiting_voice
ALTER TABLE clients ADD COLUMN context TEXT DEFAULT '[]';      -- JSON array of messages
ALTER TABLE clients ADD COLUMN summary TEXT DEFAULT '';        -- Rolling summary after compaction
ALTER TABLE clients ADD COLUMN portfolio TEXT DEFAULT '[]';    -- Validated media URLs

-- New tables
CREATE TABLE voice_jobs (...);
CREATE TABLE image_jobs (...);
CREATE TABLE agent_log (id, client_id, role, content, tool_name, tool_args, tokens_used, created_at);
```

### Function Calling Tools (JSON Schema for Mimo)
```typescript
generate_image(prompt, style)          → PiAPI image gen
generate_video(prompt, image_ref_url, duration, aspect_ratio) → PiAPI video gen
generate_voice(text, emotion)          → TTS API
analyze_image(image_url, focus)        → Vision analysis
mark_project_complete(final_url, type) → Archive + reset state
```

### System Prompt Design (Consultative vs Execution)
- Vague messages ("fais une vidéo") → Agent CONSULTS (asks about style, ambiance, format)
- Specific messages (full description) → Agent EXECUTES (calls generate_video tool)
- After media delivery → Agent asks for validation before proceeding

### Vision via Gemini API Direct (NOT OpenRouter)
```typescript
// Gemini API uses fileData.fileUri, NOT image_url
const resp = await fetch(`${GEMINI_BASE}/gemini-2.5-flash:generateContent?key=${env.GEMINI_API_KEY}`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    contents: [{ role: "user", parts: [
      { text: "Analyse cette image..." },
      { fileData: { mimeType: "image/jpeg", fileUri: imageUrl } }  // Gemini format
    ]}],
    generationConfig: { maxOutputTokens: 300 },
  }),
});
// Response: data.candidates[0].content.parts[0].text (NOT data.choices[0].message.content)
```

### Zero-Storage Media Proxy
NEVER expose Telegram URLs (contain bot_token) to PiAPI. Use proxy route:

```
Client image → file_id → proxy URL → PiAPI fetches via proxy
Proxy URL: https://api.walter-ai.cloud/proxy/media/{file_id}?client={matricule}
```

Proxy handler:
1. Looks up client's bot_token from D1 by matricule
2. Calls Telegram getFile to get file_path
3. Streams file directly from Telegram to response (zero storage)

### Context Compaction (Rolling Summary)
When context exceeds 8 messages, call LLM to summarize, then clear context array:
```typescript
if (context.length > MAX_CONTEXT_MESSAGES * 2) {
  const newSummary = await compactContext(env, context, existingSummary);
  context = [];
  await updateClientState(env, clientId, "idle", context, newSummary, portfolio);
}
```

## Fal.ai Video Generation (Grok — Current Provider)

### Admin provider/model catalog (Scena control plane)
Scena now exposes a built-in provider/model catalog via `GET /api/admin/model-catalog` and the admin Action Route modal has a `Catalog model` picker.
Use it to choose the exact provider+model combo per action without hardcoding IDs.

Current built-in video entries can be switched by product mode. In Fal-only mode, expose only:
- `fal / xai/grok-imagine-video/text-to-video`
- `fal / xai/grok-imagine-video/image-to-video`

Recommended ops pattern for Fal-only mode:
- hide PiAPI entries from `/api/admin/model-catalog`
- set `video-default` route to `provider=fal`, `model_id=xai/grok-imagine-video/text-to-video`
- keep `endpoint=''` and let the worker choose text-to-video vs image-to-video dynamically based on whether `image_ref_url` exists
- keep default params minimal (e.g. `duration`, `resolution`) so aspect ratio can stay dynamic (`9:16` for T2V, `auto` for I2V)

The catalog also returns recommended default params JSON for the UI (duration/aspect ratio/resolution), so the route form can prefill provider/model/endpoint/params in one click.

### Field Names (Model-Specific)
Fal.ai video models use DIFFERENT field names than PiAPI:
- `xai/grok-imagine-video/image-to-video` → expects `image_url` (NOT `start_image_url`)
- Each Fal.ai model may have different param names — check the 422 error message for the exact field

### Image→Video Chaining (Critical Flow)
Agent must chain `generate_image` → `generate_video` using the Fal.ai CDN URL:

```
1. Agent calls generate_image → returns { output_url: "https://v3b.fal.media/.../image.png" }
2. Agent calls generate_video with image_ref_url = that output_url (Fal.ai CDN, NOT proxy)
3. Worker sends image_url: "https://v3b.fal.media/..." to Fal.ai
```

**DO NOT** override Fal.ai CDN URLs with Telegram proxy URLs in `generate_video`. The proxy URL is only needed for the FIRST `generate_image` call (referencing the user's original image).

### ReAct Loop — `generate_image` is SYNC
`generate_image` uses `https://fal.run/` (sync endpoint) and returns the result directly. It is NOT async.

**Only `generate_video` and `generate_voice` should stop the ReAct loop** (they use `queue.fal.run/` and polling/webhook).

If `generate_image` stops the loop, the agent never gets to call `generate_video` with the output URL.

```typescript
// CORRECT — only truly async tools stop the loop
const hasAsyncTool = response.tool_calls.some(
  (tc: any) => ["generate_video", "generate_voice"].includes(tc.function.name)
);

// WRONG — generate_image is sync, don't include it
// const hasAsyncTool = response.tool_calls.some(
//   (tc: any) => ["generate_image", "generate_video", "generate_voice"].includes(tc.function.name)
// );
```

### `ctx.waitUntil` Pattern (Cloudflare Workers)
The `fetch` handler signature must include `ctx: ExecutionContext`:

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // ...
    // Use ctx.waitUntil for background polling, NOT env.waitUntil
    ctx.waitUntil(pollFalVideoResult(env, jobId, requestId, endpoint, clientId, chatId, botToken));
  }
}
```

`waitUntil` is on the execution context (`ctx`), not on `env`. Forgetting this causes `env.waitUntil is not a function` — the polling never starts, jobs stay stuck forever.

Thread `ctx` through the call chain: `fetch` → `handleTelegramWebhook` → `handleAgentMessage` → `executeTool` → `toolGenerateVideo`.

## Pitfalls & Fixes

- **Test helper `loadWorkerModule` regex fails on escaped double quotes**: In `tests/helpers/worker-test-helpers.mjs`, the import-rewriting regex `/from\s+['\"](\.[A-Za-z0-9_-]+)['\"]/g` uses `'\'"` in a JavaScript string literal. When source `.ts` files use actual double quotes `"` (e.g., `from "./tools"`), the regex doesn't match and Node gets `ERR_MODULE_NOT_FOUND` for all imports from agent.ts/orchestration_config.ts/telegram.ts. Fix: escape the double quotes properly in the regex literal, or use a template literal to avoid escaping confusion.

- **Dashboard 500 error**: `ADMIN_DIR` in `admin/dashboard/run.py` IS the dashboard directory. Use `os.path.join(ADMIN_DIR, "templates")` NOT `os.path.join(ADMIN_DIR, "dashboard", "templates")`
- **.env path**: `admin/integrations/*.py` needs 3× dirname to reach factory root. `admin/*.py` needs 2× dirname. `admin/dashboard/*.py` needs 1× dirname (it's deeper)
- **Chrome Basic Auth popup**: Caused by `WWW-Authenticate: Basic` header on 401. Remove it. Return `jsonify({"error":"..."}), 401` instead
- **CNAME + trycloudflare**: Cloudflare rejects proxied CNAME to trycloudflare.com. Must use named tunnels with `{tunnel_id}.cfargotunnel.com`
- **Fal.ai OpenAPI schemas**: Use `https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<model_id>` to get exact parameter schemas. See `fal-openapi-schema-discovery` skill.
- **Seedance 2.0 endpoints**: `bytedance/seedance-2.0/{text-to-video,image-to-video,reference-to-video}` + `/fast/` variants. No `fal-ai/` prefix.
- **Seedance Reference format**: Uses `image_urls` (array), `video_urls` (array), `audio_urls` (array) — NOT `reference_image_urls`. Prompt uses `@Image1`, `@Video1` syntax.
- **Asset preprocessor for Seedance**: Upload video → extract 3 frames via ffmpeg → upload frames + video to Fal.ai storage → get public URLs → inject into `image_urls` + `video_urls`
- **Tunnel HTTP 000**: DNS hasn't propagated yet (new CNAME on proxied zone). Wait 5-30s or restart tunnel
- **Tunnel HTTP 530**: Service not running on the port. Check `lsof -ti :PORT`
- **Clerk "Cannot read properties of undefined (reading 'load')"`: Clerk JS SDK didn't initialize. Use `polling` pattern (setInterval checking for window.Clerk) instead of onload callback
- **Clerk timeout**: Primary CDN URL `clerk.accounts.dev/npm/...` doesn't work. Use `cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js` instead
- **agent.py import errors**: `CLIENT_DIR` must be in `sys.path` for `from tools.xxx import ...` to work
- **Pipeline "sequence item 0: expected str instance, list found"**: analyzer image_b64 list handling — ensure images_b64 is list of strings, not list of lists
- **Agent repeating questions**: Old V1 pipeline re-ran from scratch each message. V2 uses state machine (`_projects` dict) tracking step: idle → clarify → planning → confirm → done
- **Flask debug=True in subprocess**: causes reloader issues. Always use `debug=False` when running as background process
- **PiAPI 403 Forbidden (error 1010)**: Cloudflare blocks requests without User-Agent header. Must add `"User-Agent": "Scena/1.0"` to all PiAPI HTTP requests (urllib, fetch, curl)
- **Wrangler scoped token vs Global Key**: Scoped `CLOUDFLARE_API_TOKEN` lacks D1/Workers permissions. Must use `CLOUDFLARE_API_KEY` (Global Key) + `CLOUDFLARE_EMAIL` for wrangler CLI operations
- **PiAPI schema ≠ Fal.ai schema**: Same model (e.g., Kling) has different param names/nesting between providers. Fal uses `arguments` flat, PiAPI uses `input` nested object
- **D1 wrangler.toml binding**: binding name must match code (`binding = "DB"` in toml → `env.DB` in TypeScript)
- **Telegram webhook multi-tenant**: Telegram doesn't send bot token in webhook payload. Solution: put client_id in webhook URL path (`/webhook/telegram/{matricule}`)
- **PiAPI webhook for async**: Free tier alternative to Cloudflare Queues. Set `config.webhook_config.endpoint` in PiAPI task creation. PiAPI POSTs result to that URL when done.
- **D1 ALTER TABLE idempotency**: `ALTER TABLE ADD COLUMN` fails if column exists. Wrap in try/except or check schema first. In D1 via wrangler, just re-run the schema file (CREATE TABLE IF NOT EXISTS handles existing).
- **Agent stuck in waiting_* state**: If tool execution fails mid-way, client gets stuck. Add `/reset` command to clear state/context/summary.
- **OpenRouter vision with proxy URL**: Pass image URL directly in `image_url` field (OpenRouter fetches it). Proxy URL must be publicly accessible — test with curl before deploying.
- **Wrangler secrets vs vars conflict**: Can't have same name in `[vars]` and secrets. Remove from `[vars]` in wrangler.toml, set via API (`PUT /accounts/{id}/workers/scripts/{name}/secrets`).
- **PiAPI 403 Forbidden (error 1010)**: Cloudflare blocks requests without User-Agent header. Must add `"User-Agent": "Scena/1.0"` to all PiAPI HTTP requests (urllib, fetch, curl)
- **Wrangler scoped token vs Global Key**: Scoped `CLOUDFLARE_API_TOKEN` lacks D1/Workers permissions. Must use `CLOUDFLARE_API_KEY` (Global Key) + `CLOUDFLARE_EMAIL` for wrangler CLI operations
- **PiAPI schema ≠ Fal.ai schema**: Same model (e.g., Kling) has different param names/nesting between providers. Fal uses `arguments` flat, PiAPI uses `input` nested object
- **D1 wrangler.toml binding**: binding name must match code (`binding = "DB"` in toml → `env.DB` in TypeScript)
- **Telegram webhook multi-tenant**: Telegram doesn't send bot token in webhook payload. Solution: put client_id in webhook URL path (`/webhook/telegram/{matricule}`)
- **PiAPI webhook for async**: Free tier alternative to Cloudflare Queues. Set `config.webhook_config.endpoint` in PiAPI task creation. PiAPI POSTs result to that URL when done.
- **Client portal auth MUST verify Clerk JWT signature via JWKS**: decoding payload + checking `iss/exp` is insecure; forged JWTs will pass. Require RS256 verification against Clerk JWKS, exact issuer match, and `kid` lookup before trusting `clerk_id`.
- **Client sync should be idempotent by `clerk_id`**: on `/api/client/sync`, fetch the primary existing client first and update it instead of creating a new random matricule. Otherwise duplicates appear in D1.
- **Bot connection should update `clients` only** unless the live `bot_pool` schema is explicitly confirmed. Do not assume portal bot-connect should insert into `bot_pool`.
- **Live D1 can drift from local schema**: before migrations, inspect prod with `PRAGMA table_info(...)` and `PRAGMA index_list(...)`. In prod audit, `image_jobs` had a literal column named `***` and `bot_pool` used `id/token/username/status/assigned_to`, so code assumptions were wrong.
- **`env.waitUntil is not a function`**: `waitUntil` is on `ctx` (ExecutionContext), not `env`. Must pass `ctx` through the call chain from `fetch(request, env, ctx)` to polling functions.
- **Fal.ai 422 `image_url: Field required`**: `xai/grok-imagine-video/image-to-video` expects `image_url`, not `start_image_url`. Check model-specific field names.
- **ReAct loop stops after `generate_image`**: If `generate_image` is in the async-tools list, agent can't chain to `generate_video`. `generate_image` is sync (returns result directly) — only `generate_video`/`generate_voice` are truly async.
- **Fal.ai CDN URL overridden by proxy**: Code that replaces non-proxy URLs with proxy URLs breaks video gen. For `generate_video`, trust the agent's URL (should be Fal.ai CDN from previous `generate_image`).
- **Gemini can rewrite a valid Fal CDN URL into a bogus host**: In production, a previous image output like `https://v3b.fal.media/...png` was later re-issued by the model as `https://files.fal.ai/...webp`, causing Fal 422 (`image_url not accessible or expired`). Do not trust model-repeated media URLs blindly.
- **Gemini can also rewrite the image URL into dead Google Cloud Storage paths**: observed production example `https://storage.googleapis.com/fal-flux/outputs/.../output.png` returned HTTP 404, even though the real prior generated image `https://v3b.fal.media/...png` was still live with HTTP 200. Treat `storage.googleapis.com/fal-flux/outputs/...` as suspicious for Fal I2V unless it was explicitly verified.
- **Safe reference resolution for Fal image-to-video**: before submitting `generate_video`, if `image_ref_url` is missing or points to suspicious hosts (`files.fal.ai`, dead `storage.googleapis.com/fal-flux/...`, or any unverified non-proxy/non-`v3b.fal.media` URL), resolve the exact last completed `image_jobs.output_url` from D1 first, then fall back to `notes.pending_proxy_url`. The worker should prefer DB-grounded media URLs over any LLM-repeated URL.
- **Validate Grok payloads against Fal OpenAPI enums before submit**: current verified schemas are:
  - `xai/grok-imagine-video/text-to-video`: required `prompt`; `aspect_ratio ∈ {16:9,4:3,3:2,1:1,2:3,3:4,9:16}`; `duration` integer `1..15`; `resolution ∈ {480p,720p}`
  - `xai/grok-imagine-video/image-to-video`: required `prompt,image_url`; `aspect_ratio ∈ {auto,16:9,4:3,3:2,1:1,2:3,3:4,9:16}`; same `duration` and `resolution`
  Clamp/sanitize worker payloads to those exact values before calling Fal to avoid 422s from bad admin params or LLM-proposed values.
- **Fal Grok request polling endpoint can require POST, not GET**: live probing of `https://queue.fal.run/xai/grok-imagine-video/image-to-video/requests/{request_id}` returned `405 Allow: POST` for GET and `401` for POST without auth, meaning a GET-based poller is wrong for this endpoint family. If jobs stay stuck in `processing`, verify the HTTP method against live behavior/OpenAPI and adjust pollers accordingly.
- **Better Fal queue pattern: trust provider URLs**: the most robust queue flow is to keep `status_url` and `response_url` returned by Fal on submit. Poll `status_url` until `COMPLETED`, then fetch `response_url` for the final media. This is safer than reconstructing queue URLs by hand and survives endpoint/method quirks.
- **Telegram inline confirmation flow works better than free-text execution for video jobs**: when enough context exists for a video request, do not send the request straight into the LLM/tool call. Instead, create an ephemeral `production_draft` in `clients.notes`, show inline keyboards for duration / aspect ratio / resolution, then edit the same Telegram message into a final summary with `✅ Oui — <credits>` and `Cancel`. Only after confirm should the worker call `generate_video`. This materially reduces hallucinated params and gives a cleaner Telegram UX.
- **Suggested Telegram draft state machine**: `awaiting_prompt` → `select_params` → `confirm`. Persist in `clients.notes.production_draft` fields like `kind`, `mode`, `prompt`, `reference_image_url`, `duration`, `aspect_ratio`, `resolution`, `style`.
- **Parse video preferences from the user's free-text before rendering the picker**: extract obvious tokens like `3 sec`, `5 sec`, `10 sec`, `480p`, `720p`, and ratios like `9:16` / `16:9` from the Telegram message so the first picker render is already preselected. This reduces friction and makes the confirmation summary match the user's intent immediately.
- **Do not trigger the Telegram video picker just because an image exists in context**: a naive `hasImageContext => video request` heuristic breaks normal chat. Casual messages like `comment tu vas ?` can get trapped into `Réglages de production` if an old image is still available. Require explicit video cues (`video`, `animer`, `animation`, `ugc`, etc.), explicit production specs (`3s`, `480p`, `9:16`), or a true motion instruction tied to a fresh image context.
- **Text-only Telegram requests with no reference media should stay in consultation mode, not jump straight to the picker**: keep the production picker for (a) requests that already include an image, or (b) the explicit `awaiting_prompt` continuation after the user clicked `🎬 Animer`. A planning sentence like `je veux que tu animes une image que je vais te faire parvenir` should ask for the missing image first, not open production settings.
- **Image context for picker auto-routing must be freshness-bounded**: when reusing `pending_proxy_url` or the last completed image as implicit context for Telegram messages, enforce a short freshness window (production fix used 30 minutes). Without a TTL, an old completed image can hijack later text-only conversation and push the user back into the picker.
- **Picker-confirmed values must override admin route defaults**: in `submitVideoGeneration` / `generate_video`, normalize settings with explicit user args first (`args.duration`, `args.aspect_ratio`, `args.resolution`) and only then fall back to `route.params`. If route defaults are read first, Fal receives stale defaults like `6s` / `720p` even when the Telegram picker shows `3s` / `480p`.
- **Do not inject stale active-project context into every conversational turn**: if the user message is casual small talk (`comment tu vas`, `tu es là ?`) or clearly starts a fresh brief instead of continuing an in-flight render, suppress `active_project_id` / project summary injection in `assembleAgentContext`. Otherwise the agent answers with irrelevant baggage (`on s'était arrêtés sur...`) and feels dumb.
- **Memory summary generation must NOT recurse through prior `memory_summary_md`**: rebuild from stable facts + `client.summary`, not from the previous generated memory block. Reusing `config.memory_summary_md` creates nested `## Memory summary` sections and re-anchors obsolete project state in the prompt.
- **Do not treat `tenant_agent_config.user_md` as the admin-editable base User.md**: in Scena V3, `user_md` is a runtime snapshot regenerated by `assembleAgentContext(...)`. For a true editable static layer in the admin dashboard, keep a separate stable field (production fix used `tenant_agent_config.base_user_md`) and merge it into the generated `user.md` at prompt-assembly time. Otherwise admin edits get silently overwritten on the next agent turn.
- **Workflow runner must require stronger execution signals than a weak intent like `je veux`**: for text-only requests without media, stay in `consultation` unless there is explicit launch approval (`vas-y`, `ok lance`, `go`, etc.) or attached media. Starting deterministic execution too early makes the agent over-eager and bypasses the validation-first UX.
- **For confirmed Telegram image-animation requests, default to skipping style preset injection**: if the draft comes from the Telegram confirm flow, pass `skip_style_preset=true` (or equivalent) so the exact user action prompt is sent to Fal. Otherwise route/admin presets can wrap a simple action like `il ferme la bouche et fait un clin d'oeil` into an unwanted template such as `UGC style video of ...`.
- **Fal delivery needs a scheduled recovery path, not only `waitUntil`**: even with provider `status_url`/`response_url`, a Cloudflare Worker background poll can be missed. Add a cron-triggered sweeper (for example every minute) that scans `video_jobs` still in `processing` for Fal Grok models, polls provider status again, and sends the final Telegram video if the original async path failed.
- **Multi-image product requests can be supported without changing the DB schema**: keep `image_jobs.output_url` single-value and create one `image_jobs` row per generated variation. A safe production pattern is `generate_image(count>1)` → expand into N adapted prompts (Gemini or deterministic fallback) → charge `N * image_cost` once → create N jobs → call Fal N times → deliver N Telegram photos independently. This gives real parallel variants while preserving existing tables and webhook semantics.
- **Multi-video batch requests can follow the same pattern without changing the DB schema**: add `generate_video(count>1, variation_instructions)` at the tool layer, charge `N * video_cost` once, create one `video_jobs` row per variant, submit N Fal requests in parallel, and let each poller/webhook deliver its Telegram video independently. Return a batch summary to the agent/user, but keep one `video_jobs` row per output for recovery and idempotent delivery.
- **Telegram video picker must preserve requested batch count and show total cost**: when a user sends a photo+text like `3 vidéos UGC`, the picker flow in `index.ts` must parse and persist `draft.count`, carry `variation_instructions`, show `xN vidéos` + `N * VIDEO_GENERATION_COST` in the summary, and pass `count` through `submitVideoGeneration(...)`. Otherwise image-context requests silently collapse back to a single video even if the agent/tool supports batching.
- **Telegram retries webhook deliveries after 60 seconds if the Worker doesn't return 200 OK**: this is the #1 cause of infinite agent loops in production. If `handleAgentMessage` (vision analysis + tool calls + generation) takes >60s, Telegram considers it failed and resends the exact same message. The agent processes it again, generates again, takes >60s again → infinite loop. Fix with message_id deduplication in the webhook handler BEFORE any agent processing. Do NOT use `ctx.waitUntil` to send responses asynchronously — the synchronous 200 OK is needed, but the agent must still finish processing before returning.
- **ReAct loop guard — block repeated generate_image/generate_video within a single session**: even with webhook dedup, the ReAct loop itself can call generate_image repeatedly across iterations. Add a guard that counts how many times `generate_image` or `generate_video` tool results already exist in the messages array. If count >= 1, skip the tool call with a neutral "already done" response. This prevents infinite loops both from Telegram retries AND from LLM re-reasoning loops within a single invocation.
- **Always investigate with `agent_log` D1 table before assuming the root cause**: when debugging production loops, query `agent_log` for recent entries to see the actual tool call timestamps. 60s intervals = Telegram retries. Few minutes apart = user resending messages. Instant repetition within seconds = ReAct loop within single invocation.
- **Video batch (count>1) creates N parallel pollers via ctx.waitUntil**: each variant gets its own `pollFalVideoResult(...)` inside `ctx.waitUntil`. The scheduled cron is a safety net for jobs that complete after the Worker instance terminates. Both paths can race — the poller writes `telegram_message_id` first, and the cron skips already-delivered jobs.
- **Vision LLM hallucination drift across retries causes Fal.ai to generate wrong products**: when Telegram retries trigger re-processing, the vision Gemini call re-analyzes the same image and often identifies a different product each time (non-deterministic). If the agent injects the vision text ("perfume bottle", "shoes", "insoles") into `generate_image` prompts, Fal generates wrong products. Fix with two layers: (a) system prompt instruction telling the agent the vision analysis is indicative only and prompts with image_ref_url should describe ANGLES/COMPOSITIONS generically, never mention specific product types; (b) message builder warning that the product identity comes from the image, not the text.
- **Concurrent webhook dedup with in-memory Set + D1**: use a global `Set<string>` keyed by `matricule:message_id` as the first line of defense against concurrent webhook deliveries within the same Worker isolate. Also write the dedup marker to D1 (`clients.notes.last_processed_message_id`) BEFORE the slow agent processing starts, so cross-isolate retries also hit the marker. Cleanup the in-memory Set after 2 minutes as a safety net. Both layers are needed — in-memory handles the race condition, D1 handles isolate restarts.
- **Never use ctx.waitUntil to send the Telegram webhook response asynchronously**: if you return 200 OK before the agent finishes, Telegram considers it delivered. But the agent might still be generating images, and if the Worker instance is recycled, the background task is lost. Always await `handleAgentMessage` synchronously and use message_id dedup to prevent retries instead.
- **Always run the FULL test suite after any changes to the ReAct loop or webhook handler**: the telegram-ui tests check the synchronous response path, and agent tests check the ReAct loop behavior. A change that fixes one can break the other.
- **Track Telegram delivery separately from generation completion**: `status='completed'` is not enough to prove the user received the video. Persist the Telegram send result (at minimum `video_jobs.telegram_message_id`) after successful `sendVideo`/fallback `sendDocument`. This creates an idempotent delivery marker and avoids guessing whether a completed render was actually sent.
- **Recovery sweep must also scan completed-but-undelivered jobs**: only rescanning `status='processing'` misses the exact class of bug where generation completed, `output_url` exists, but Telegram delivery crashed afterward. Add a second scheduled pass over `video_jobs` with `status='completed' AND output_url != '' AND COALESCE(telegram_message_id, 0) = 0` and retry delivery there.
- **Telegram messages are sent with `parse_mode='HTML'`, so raw Markdown like `**gras**` will render literally**: if the LLM returns Markdown-style emphasis, normalize outgoing text/captions before `sendMessage`/`editMessageText`/`sendVideo`/`sendDocument` by converting `**text**` → `<b>text</b>`, preserving supported existing Telegram HTML tags, and escaping raw `<` / `>` from plain text. Otherwise chats show stray `**` and malformed angle-bracket content.
- **Telegram 403 on delivery can be a stale chat target, not a generation failure**: if direct bot sends return 403, verify the stored `telegram_chat_id` has been refreshed by a recent inbound user message before debugging Fal further.
- **Wrangler deploy fails without token**: Use `CLOUDFLARE_API_KEY` (Global Key) + `CLOUDFLARE_EMAIL` env vars. Scoped API tokens lack D1/Workers permissions.
- **Video validation HEAD unreliable**: Some CDNs (GCS, S3 presigned) reject HEAD with 403/405. Pipeline `validate_source` must try HEAD, fallback to GET with `Range: bytes=0-0`. Both failing = truly inaccessible.
- **Kie resultJson extraction**: Kie video URLs are in `taskData.resultJson` as JSON string with `resultUrls[]`, NOT in `taskData.output.video_url`. Always parse `resultJson` first, fallback to `output.*` fields.
- **Pages project names ≠ custom domains**: `scena-admin` → `admin-scena.walter-ai.cloud`, `scena-connect` → `scena-connect.pages.dev`. Always check `wrangler pages project list` before deploy.
- **`gemini-2.0-flash` deprecated**: Google deprecated `gemini-2.0-flash` for new AI Studio users. Use `gemini-2.5-flash` instead. Error: "This model models/gemini-2.0-flash is no longer available to new users"
- **Gemini format ≠ OpenRouter format**: When migrating from OpenRouter to Gemini API, must convert: tool schema (lowercase→uppercase types), message roles (assistant→model, tool→functionResponse), response parsing (choices→candidates). See converters in agent.ts.
- **Gemini 3 Flash requires thoughtSignature round-trip**: `thoughtSignature` is at the PART level (alongside `functionCall`), NOT inside `functionCall`. Putting it inside `functionCall` causes: `Unknown name "thoughtSignature" at 'contents[X].parts[0].function_call': Cannot find field`. Solution: store the RAW Gemini parts from the response (`_geminiParts` on assistant message) and pass them back verbatim. Don't reconstruct parts from OR format — that loses the thoughtSignature.

  ```typescript
  // parseGeminiResponse: store raw parts
  return { content, tool_calls: toolCalls, tokens: ..., rawParts: parts };
  
  // ReAct loop: store raw parts in assistant message
  messages.push({
    role: "assistant", content: cleanContent, tool_calls: response.tool_calls,
    _geminiParts: response.rawParts,
  });
  
  // convertMessagesToGemini: use raw parts directly
  if (msg._geminiParts && Array.isArray(msg._geminiParts)) {
    contents.push({ role: "model", parts: msg._geminiParts });
  } else {
    // Fallback: reconstruct (won't have thoughtSignature)
  }
  ```

- **Gemini functionResponse.name must match functionCall.name**: Gemini requires `functionResponse.name` to match the `functionCall.name` that triggered it. Using a hardcoded `"tool_result"` causes errors. Solution: find the function name from the previous model message's functionCall, or store `_functionName` on the tool message.

  ```typescript
  // When creating tool messages in ReAct loop:
  messages.push({
    role: "tool", content: JSON.stringify(result),
    tool_call_id: tc.id,
    _functionName: tc.function.name, // Store for Gemini round-trip
  });
  
  // In convertMessagesToGemini, when processing "tool" messages:
  let funcName = msg._functionName || "result";
  for (let i = contents.length - 1; i >= 0; i--) {
    if (contents[i].role === "model" && contents[i].parts) {
      for (const p of contents[i].parts) {
        if (p.functionCall) { funcName = p.functionCall.name; break; }
      }
      break;
    }
  }
  contents.push({ role: "user", parts: [{ functionResponse: { name: funcName, response: simplified } }] });
  ```

- **Gemini doesn't support integer enums**: Tool parameters with `enum: [5, 10, 15]` and `type: "integer"` cause `Invalid value at '...enum[0]' (TYPE_STRING)`. Must use `type: "string"` with `enum: ["5", "10", "15"]` and parse to int in the tool handler.

## Additional Lessons Learned (April 2026)

- **D1 legacy column `image_jobs."***"` may be effectively unrenamable in-place** through the usual Cloudflare D1 API workflow. If production already has this column, prefer **runtime compatibility** over risky table surgery: keep code writing/reading the legacy column name where needed, expose a normalized `fal_request_id` field at the API layer, and defer physical schema cleanup to a controlled table rebuild migration.
- **Admin API can normalize dirty DB rows before returning JSON**. For example, `/api/admin/image-jobs` should map legacy `"***"` → `fal_request_id` and hide the raw field so frontends stay stable even when production schema drifts.
- **Use a local Worker regression harness before redeploying**. In `scena-cloudflare`, a lightweight pattern works well:
  - `package.json` with `node --experimental-strip-types --test`
  - copy `index.ts/agent.ts/tools.ts` to a temp dir and rewrite local imports to include `.ts`
  - mock `fetch` + mock D1 `prepare().bind().first/all/run()`
  - cover auth bypass attempts, ReAct loop behavior, provider routing, and bot connection writes
- **Best stabilization order for Scena prod**:
  1. Write failing regression tests for the real bug
  2. Fix Worker logic locally until tests pass
  3. Clean conflicting production data (duplicate `clerk_id`, duplicate bot token)
  4. Add unique indexes in D1
  5. Deploy Worker
  6. Deploy Pages
  7. Run live HTTP/security regression checks
  8. Only then stop legacy services/tunnels

## Per-client `memory.md` for true multi-tenant agents (May 2026)

For Scena's Telegram media agent, each tenant/client should have a logical memory artifact at `clients/{matricule}/memory.md`, persisted in D1 rather than local disk. Store it on `tenant_agent_config.memory_md` + `memory_md_updated_at`, generate it from DB-grounded tenant data (`base_user_md`, `tenant_memory_entries`, `tenant_projects`, `image_jobs`, `video_jobs`, `tenant_memory_events`), return it from `/api/admin/clients/:id/brain`, and inject a clipped version into `assembleAgentContext(...)`. Keep it separate from `user_md` (runtime snapshot) and `memory_summary_md` (compact summary). See `references/client-memory-md-pattern.md` for the concrete schema/API/test pattern and pitfalls.

## Telegram agent-first UX (May 2026)

When Lucas says the Telegram experience feels like a dumb bot, inspect routing before tweaking copy. A proper `agent.ts` ReAct loop can still be bypassed by deterministic `index.ts` intake rules.

Preferred pattern:
- Buttons are optional accelerators, not the primary brain.
- Adaptive agent proposal buttons use `agent:*` callbacks (not `intake:*`) after project-like agent replies. They should be built from the current user text + agent response, omitted for casual small talk or missing-media prompts, and never create `notes.project_intake`.
- `agent:*` callbacks should answer the callback, remove the old inline keyboard, append a fresh Telegram message, and call `handleAgentMessage(...)` with an action prompt like `Action cliquée: Script/storyboard. Continue avec le projet actif...` so Qwen re-enters the ReAct loop with prior project context.
- `/start` and `/reset` should not seed `notes.project_intake` by default; otherwise the next natural text/voice gets trapped in a questionnaire.
- Free text with no active guided intake should route to `handleAgentMessage(...)` and Qwen, then optionally attach adaptive `agent:*` buttons.
- Voice with no active guided intake should use Gemini STT only, then pass the transcript to Qwen/agent and optionally attach adaptive `agent:*` buttons.
- Existing guided intake remains valid only when the user explicitly entered/clicked that flow (`notes.project_intake` exists and is not confirmed).
- Add a no-cost `record_project_plan` tool so the agent can create/update `tenant_projects`, set `tenant_agent_config.active_project_id`, record a memory event, then answer naturally with plan + next step.
- Keep credit-consuming `generate_*` behind explicit validation.

Reference: `references/telegram-agent-first-ux.md` contains the concrete routing, tool shape, and regression tests from the session.

## Deterministic workflow runner (April 2026)

When Scena evolves from workflow guidance in the prompt to real step execution, add a DB-backed workflow runner instead of relying only on injected workflow docs.

### Required tables
- `workflow_runs`
  - `id`, `client_id`, `project_id`, `workflow_id`
  - `status` (`running`, `waiting_async`, `awaiting_user`, `failed`, `completed`)
  - `current_step_key`
  - `last_tool_name`, `last_job_type`, `last_job_id`, `last_error`
  - `trigger_message_md`, timestamps
- `workflow_step_runs`
  - one row per workflow step per run
  - `step_key`, `status`, `tool_name`, `input_json`, `output_json`, `error_md`, `attempt_count`
- `workflow_trace_events`
  - append-only trace with `event_type`, `message_md`, `payload_json`

Also extend async job tables so callbacks can reconnect to the run:
- `video_jobs`: add `project_id`, `workflow_run_id`, `workflow_step_key`
- `image_jobs`: add `project_id`, `workflow_run_id`, `workflow_step_key`

### Runtime pattern
Create `workers/api/src/workflow_runner.ts` with functions like:
- `prepareWorkflowExecution(...)`
- `recordWorkflowToolResult(...)`
- `recordWorkflowAsyncResult(...)`

Flow:
1. After `assembleAgentContext(...)`, decide consultation vs deterministic workflow execution.
2. If executing:
   - ensure/create `tenant_projects`
   - set `tenant_agent_config.active_project_id`
   - create `workflow_runs`
   - seed `workflow_step_runs`
   - pick first step as `current_step_key`
3. Inject current step instructions into the system prompt every ReAct iteration.
4. After each tool call, update the current step and move deterministically.
5. Persist `workflow_run_id` / `workflow_step_key` on image/video jobs.
6. In PiAPI/Fal webhooks or Fal polling completion handlers, call `recordWorkflowAsyncResult(...)` so async completion actually advances the workflow.

### Critical rule: skip fallback nodes on normal success
If a step's immediate next ordered row is its fallback step, normal success must skip that fallback node and go to the next primary step.

Example:
- step 2 = `animate_face`
- step 3 = `fallback_video`
- step 4 = `review`

On success of `animate_face`, go to `review`, not `fallback_video`.
Use a helper like `getNextPrimaryStep()` instead of blindly taking the next ordered step.

### Critical rule: createWorkflowRun can return in-memory seeded state
In tests/mocks, re-querying immediately after inserts may not reflect seeded rows unless every query is mocked. Returning the created run + stepRuns in-memory makes the runner easier to test and more deterministic.

### Regression tests worth keeping
- workflow run creation selects the first step
- sync success advances to next step
- failure branches to `fallback_workflow_step_key`
- async completion advances to review/next step
- `handleAgentMessage(...)` writes `workflow_run_id`, `workflow_step_key`, `project_id` into jobs
- webhook completion updates workflow state

## Source video → target regeneration workflow (May 2026)

Lucas validated the Scena source-video-to-target-video workflow from `workflow_video_ai_seedance_agent_spec.md` with these decisions:
- Channels: Scena Telegram **and** Scena Connect SaaS.
- Default video provider: Kie.ai `bytedance/seedance-2-fast`.
- Rollout: step-by-step testing before complete generation.
- Heavy artifacts: Google Drive shared folder `w.alter`.
- Infrastructure: free tier for now — no R2 and no Cloudflare Queues.

Installed artifacts in `/root/projects/scena-cloudflare/`:
- `docs/workflows/workflow_video_ai_seedance_agent_spec.md` — full Drive spec copied into repo.
- `docs/workflows/video-source-to-target-regeneration.md` — operational Scena summary.
- `workers/api/src/builtin_video_workflows.ts` — built-in model docs + workflow pack catalog.
- `scripts/seed-video-workflows.mjs` — API seeder (`--dry-run` by default, `--apply` mutates via admin API if `SCENA_ADMIN_SECRET` exists).
- `tests/video-workflow-catalog.test.mjs`
- `tests/video-workflow-seed-script.test.mjs`

Production D1 seed was applied directly with wrangler because no local `ADMIN_SECRET` was available:
- DB: `scena-db` (`3567d347-37d7-45d5-b348-3dfc5f674006`)
- Workflow pack: `video-source-to-target-regeneration-v1`
- Steps: 16
- Model docs: `gemini-video-json-analysis`, `kie-seedance-2-fast-video`, `kie-gpt-image-2-sheets-storyboards`, `google-drive-workflow-artifacts`
- Assigned only to Lucas active client id `3` (`scmnw15oh9wll1`) for staged testing.

Core rule encoded in workflow guidance:
```text
Never do: source video → final prompt
Always do: source video → objective source analysis → client modification plan → target video plan → sheets → target storyboard → generation clips → Seedance-aware reference plan → provider payloads → QA → validation → generation
```

Useful commands:
```bash
# Local tests for the installed catalog/seeder
node --experimental-strip-types --test tests/video-workflow-catalog.test.mjs tests/video-workflow-seed-script.test.mjs

# Relevant regression bundle
node --experimental-strip-types --test \
  tests/video-workflow-catalog.test.mjs \
  tests/video-workflow-seed-script.test.mjs \
  tests/workflow-library.test.mjs \
  tests/workflow-runner.test.mjs \
  tests/provider-payloads.test.mjs \
  tests/saas-connect.test.mjs

# Dry-run API seeder
node --experimental-strip-types scripts/seed-video-workflows.mjs --dry-run

# Direct D1 verification
CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)" CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com" \
wrangler d1 execute scena-db --remote --command="SELECT wp.id, wp.title, COUNT(ws.id) steps FROM workflow_packs wp LEFT JOIN workflow_steps ws ON ws.workflow_id=wp.id WHERE wp.id='video-source-to-target-regeneration-v1' GROUP BY wp.id;"
```

Drive folder created under `w.alter` for workflow docs:
https://drive.google.com/drive/folders/1iBpCTpdsQgno86Qwu63fCLiCwHIkuAWf

Important caveat from the install run: full `npm test` had unrelated pre-existing portal/vitrine HTML failures (`client-credit-checkout-ui` / `scena-vitrine`). The targeted workflow/provider/SaaS tests passed. Do not attribute those portal failures to the workflow catalog changes unless the HTML files were touched in the same task.

## Admin dashboard redesign pattern (April 2026)

When Lucas asks for a "complete redesign" of the admin dashboard, he often means:
- radically improve hierarchy, navigation, and aesthetics
- do **not** break the DB schema or backend production flows
- keep existing endpoints working unless a tiny additive API is clearly necessary

### Safe redesign approach
1. Prefer redesigning `pages/admin/index.html` first, keeping the Worker/API stable.
2. Use a strong dashboard design system (Linear-style worked well):
   - sticky left sidebar
   - operator-focused topbar
   - clear section framing (`Command Center`, `Production Chain`, `Control Plane`, etc.)
   - stronger visual distinction between static admin config vs client-organic state
3. Reorganize labels and layout around operator intent, not raw technical tabs.
4. Explicitly surface these concepts in the UI copy:
   - `Static Files`
   - `Organic Memory`
   - `Runtime`
5. Only add tiny backend/API changes if they unlock a clearly needed admin capability (for example an editable stable `base_user_md` field for the Client Brain). Avoid broad refactors during a UI redesign pass.
6. Regression-test the admin HTML with string-based tests to assert that the new information architecture exists (`Command Center`, `Production Chain`, `Static Files`, `Organic Memory`, etc.).
7. Deploy Pages separately after test pass; verify the production custom domain, not just the preview URL.

### Important product lesson
Do not confuse:
- editable stable admin-authored files (`Agent.md`, workflow docs, presets, stable user notes)
with
- generated organic/runtime artifacts (`user_md`, memory summary, active project snapshot)

If admin needs a stable editable User layer, keep it in a separate field (production fix used `tenant_agent_config.base_user_md`) and merge it into the generated runtime `user_md`.

## Scena Ops / Scena Sentinel (May 2026)

When Lucas asks for a dedicated Scena operational brain, daily integrity checks, safe auto-repair, or AI-model/provider watch, use the **Scena Ops / Scena Sentinel** pattern. Keep runtime product data in `scena-db` and create a separate `scena-ops-db` for operational checks, incidents, repair actions, metrics, research items, and recommendations.

Core rule: Sentinel may auto-apply only safe, non-destructive repairs (repoll stuck jobs, retry completed-but-undelivered Telegram delivery, reseed built-ins, close verified duplicate incidents, write reports/recommendations). D1 migrations, provider-route changes, pricing/credits, auth/secrets, deploy/rollback, and bulk data mutations are guarded repairs requiring explicit approval.

Reference: `references/scena-ops-sentinel.md` contains the schema shape, daily flow, checks, repair policy, research-watch sources, admin routes, and report format. Production is installed with D1 `scena-ops-db` bound as `OPS_DB` (`database_id=cfedbcb0-6788-400b-a577-6369dda355df`). Session artifacts in `/root/projects/scena-cloudflare/`: `d1/scena-ops-db.sql`, `docs/scena-ops-agent.md`, `workers/api/src/ops_*.ts`, and `tests/ops-sentinel.test.mjs`.

Reference: `references/scena-production-readiness.md` captures the production-readiness audit pattern, P0 blockers, audit commands, and partner-ready Scena Connect criteria. Use it when Lucas asks what is missing before launch or before onboarding SaaS partners.

Reference: `references/scena-p0-hardening-may-2026.md` captures the concrete P0 hardening run: Scena Connect key rotation/revoke, quotas, rate limit, usage ledger, webhook delivery audit/retry/idempotency, Sentinel Telegram notifications, historical job cleanup, D1 `updated_at` drift pitfall, test/deploy sequence, and final prod verification.

Reference: `references/scena-vitrine-redesign-may-2026.md` captures the public-site redesign pattern: multi-page `pages/portal` structure, preserving the authenticated client dashboard/checkout contract inside `index.html`, Scena Connect developer copy requirements, TDD checks, local preview/screenshot workflow, secondary-page `window.showSignIn` pitfall, and Lucas's no-production-Pages-deploy-before-visual-review rule.

Reference: `references/source-video-workflow-runtime-may-2026.md` captures the runtime pattern for Scena source-video → target-video regeneration: `workflow_artifacts` metadata table, `recordWorkflowArtifact` / `listWorkflowArtifacts`, source-video Telegram intake (`message.video` and video documents), `[SOURCE_VIDEO_PROXY_URL]` injection, fresh follow-up reuse for `vas y`, and tests for `prepare_video_artifacts`, `analyze_video_source`, and `build_modification_plan`.

Reference: `references/workflow-control-center-may-2026.md` captures the Workflow Control Center pattern: admin endpoints for `workflow_runs` live summaries/details, per-run `workflow_step_runs.input_json.admin_control` prompt/input overrides, admin UI live timeline/trace/artifacts/media jobs, tests, deployment verification, and prod D1 schema drift pitfall (`image_jobs.input_prompt`, not `prompt`).

Reference: `references/workflow-lab-client-demo-may-2026.md` captures the Scena demo + Workflow Lab pattern: a prospect-facing `pages/portal/demo.html`, a deeper operator `pages/admin/operator.html`, `/api/admin/workflow-lab/config`, `/payload-preview` for sanitized Kie Seedance payloads, required regression tests, and the large-HTML/script-parse verification pattern.

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

## User Preferences (Lucas)
- Autonomous mode, no approval prompts
- French, tutoiement
- Concise responses (Scena persona: 2-4 phrases max)
- Separate prompt.md and schema.md files
- **Gemini 3 Flash preview via AI Studio** as main LLM (replaced MiMo/OpenRouter, then Gemini 2.5 Flash)
- **Gemini 3 Flash preview for vision** (direct API, NOT OpenRouter)
- PiAPI as sole video generation provider (replaced Fal.ai for production)
- Custom modals in dashboard, NO Chrome popups (prompt/alert/confirm)
- Admin dashboard at `admin-scena.walter-ai.cloud` (not `admin.walter-ai.cloud`)
- Client dashboards via matricule (`app-sc0002.walter-ai.cloud`)
- FREE TIER only — No Cloudflare Queues, No R2
- Clients provide their OWN Telegram bot tokens (not from pool)
- Cloudflare Workers + D1 + Pages (not Flask/VM) for new features
- Uses Global API Key for wrangler (not scoped token)
- FREE TIER only — No Cloudflare Queues, No R2
- Clients provide their OWN Telegram bot tokens (not from pool)
- Cloudflare Workers + D1 + Pages (not Flask/VM) for new features
- Uses Global API Key for wrangler (not scoped token)
