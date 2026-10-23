---
name: scena-cloudflare-serverless
description: Scena V2 — Cloudflare serverless architecture (Workers + D1 + Pages) replacing Flask/VM. Multi-tenant Telegram bot routing, zero-storage media proxy, PiAPI webhook async flow, agent brain with Mimo v2 Pro.
category: devops
---

# Scena Cloudflare Serverless V2

## Architecture

```
api.walter-ai.cloud → Cloudflare Worker (scena-api)
                        ├── /webhook/telegram/{matricule}  ← Multi-tenant Telegram
                        ├── /webhook/piapi                 ← Video callback
                        ├── /webhook/piapi-image           ← Image callback
                        ├── /webhook/fal-image             ← Fal.ai fallback
                        ├── /proxy/media/{file_id}?client= ← Zero-storage proxy
                        ├── /api/register                  ← Client signup
                        ├── /api/bot/validate              ← Bot token → webhook
                        └── /api/admin/*                   ← Admin API
```

## Key Patterns

### Multi-Tenant Webhook Routing
Each client's Telegram bot webhook points to `https://api.walter-ai.cloud/webhook/telegram/{matricule}`. The Worker looks up the client in D1 by matricule. Bot token never leaves D1.

### Zero-Storage Media Proxy
Telegram URLs contain the bot token (security risk). Solution: proxy route `/proxy/media/{file_id}?client={matricule}`.
- Worker looks up client's bot token from D1
- Calls Telegram getFile → streams response directly
- No files stored anywhere
- PiAPI receives `https://api.walter-ai.cloud/proxy/media/xxx?client=sc0001` — token hidden

### PiAPI Webhook Async Flow (Free Tier — No Queues)
1. Client sends message → Worker creates job in D1 (status=processing)
2. Worker submits to PiAPI with `config.webhook_config.endpoint = https://api.walter-ai.cloud/webhook/piapi`
3. Worker responds 200 to Telegram immediately ("Rendu en cours 🍿")
4. PiAPI finishes → hits `/webhook/piapi` → Worker sends result to Telegram

### Agent Brain (State Machine)
States: `idle`, `waiting_image`, `waiting_video`, `waiting_voice`, `consulting`

### Admin-manageable orchestration layer (style presets + action routes)
To avoid hardcoding all creative logic in `tools.ts`, add two D1-backed control-plane tables and expose them in the admin dashboard:

- `style_presets`
  - slug, title, description
  - `image_prompt_template`, `video_prompt_template`
  - `negative_prompt`, `tags_json`, priority
  - examples: `cinematic`, `ugc`, `thumbnail`, `product-shot`, `lifestyle`

- `action_model_routes`
  - id, `action_type` (`image_gen`, `video_gen`, `resize_image`, ...)
  - provider, model_id, endpoint
  - `default_style_slug`, `params_json`, priority
  - examples:
    - `image_gen` → `fal-ai/nano-banana-2`
    - `video_gen` → `seedance-2-fast`

Runtime precedence should be:
1. workflow step overrides (`model_provider`, `model_id`, `params_json.style_preset_slug`)
2. global `action_model_routes` default for the action type
3. built-in fallback in code

This lets the agent choose a high-level action while the Worker injects the right model + prompt preset into the provider payload.

D1 columns on `clients` table:
- `state TEXT DEFAULT 'idle'`
- `context TEXT DEFAULT '[]'` — JSON array of conversation messages
- `summary TEXT DEFAULT ''` — compacted project summary
- `portfolio TEXT DEFAULT '[]'` — archived validated media URLs

System prompt enforces bifurcation: vague → consult (text only), specific → execute (tool call).

### Telegram conversation policy (production-safe)
For Scena's Telegram UX, don't let the agent jump straight to generation on every clear request. Use a guided intake layer before the free-form agent when the user starts a project.

## Deploy flow (Worker + D1)

**Critical**: `CLOUDFLARE_API_TOKEN` (from vault `cloudflare/api_token`) lacks D1 execute permissions. Use global key for D1 migrations:

```bash
# D1 migration
export CLOUDFLARE_API_KEY="$(vault get cloudflare/global_api_key)"
export CLOUDFLARE_EMAIL="lucas.jouvencon@gmail.com"
unset CLOUDFLARE_API_TOKEN
npx wrangler d1 execute scena-saas-db --remote --file d1/saas-pipeline-runs.sql

# Worker deploy (same auth)
npx wrangler deploy --config workers/api/wrangler.toml
```

**Verify after deploy**:
```python
import urllib.request
for path in ['/health', '/ping']:
    req = urllib.request.Request(f'https://api.walter-ai.cloud{path}', headers={'User-Agent': 'Scena/1.0'})
    with urllib.request.urlopen(req, timeout=10) as r:
        print(f'{path} → {r.status}')
```

## Oracle FFmpeg media-worker sidecar

Scena uses the Oracle VM only for deterministic zero-credit post-production after provider-generated clips. Runtime flow: `render_video` creates a `video_jobs` row (`task_type='video_composition'`, `cost_credits=0`) → `POST https://temp-scena.walter-ai.cloud/jobs/render-video` → FFmpeg/ffprobe → signed `/webhook/media-worker` callback → D1 completion → multimodal QA → retry or Telegram human gate.

Security contract for Scena↔VM jobs and callbacks:
- Shared key: Cloudflare secret and VM env both named `SCENA_TEMP_STORAGE_TOKEN` / `SCENA_TEMP_UPLOAD_TOKEN` respectively.
- Headers: `X-Scena-Timestamp` and `X-Scena-Signature: sha256=<hex>`.
- Canonical bytes: `<timestamp>\n<METHOD>\n<URL pathname>\n<exact raw body>`.
- Reject timestamps outside 300 seconds, malformed signatures, Bearer-only job/callback requests, private/non-HTTPS asset URLs, and callback hosts other than `api.walter-ai.cloud`.
- Legacy operator `/upload` remains Bearer-authenticated; job submit/status and callbacks require HMAC.

Production service:
- Source: `services/scena-media-worker/server.py`
- Tests: `python3 -m unittest -v services.scena-media-worker.test_server` and `node --experimental-strip-types --test tests/media-worker-integration.test.mjs`
- Installed code: `/opt/scena-temp-storage/server.py`
- Unit: `scena-temp-storage.service`
- Local/public health: `http://127.0.0.1:8799/health`, `https://temp-scena.walter-ai.cloud/health`
- Cloudflare Worker deploy must include the same shared secret and the `/webhook/media-worker` route. Always verify the shared key without printing it: a valid signed callback for an unknown `scena-media-*` job must return `404 media_job_not_found`, not `401`.
- End-to-end verification must render real clips, wait for D1 `status=completed`, download the master, run `ffprobe`, visually inspect a frame, confirm `cost_credits=0`, then delete the temporary D1 job row.

## Pipeline runner architecture

The autonomous pipeline (`pipeline_runner.ts`) uses a state-machine pattern:
- Sync steps (Gemini analysis, image gen with polling) execute in the Worker request
- Async steps (Kie Seedance video) submit and return `waiting_async`
- Resume happens via webhook callback to `/webhook/pipeline/kie-video`
- D1 table `saas_pipeline_runs` stores full state (input, artifacts, output, current_step)

**BYOK is already wired** in `saas_connect.ts` — don't re-implement it. The `getProviderKeys()` function decrypts `encrypted_provider_keys_json` from the connection and falls back to global env keys.

**Gemini via OpenRouter**: Use `video_url` content type in messages array, not base64. Model: `google/gemini-2.5-flash`.

**Kie image gen**: Synchronous — poll `recordInfo` endpoint (10 attempts × 2s max). Don't treat as async. Reduce polling attempts to save subrequests.

## Cloudflare Workers subrequest limit

A single Worker invocation has a 1000 subrequest limit. The pipeline does: HEAD/GET validation (1-2), Gemini calls (2), Kie image gen with polling (~30 per image). With 2-3 images, that's 90+ subrequests just for polling. **Sheets and storyboard are non-fatal** — if they hit the limit, the pipeline continues without them.

**Mitigation**: Reduce Kie polling to 10 attempts. Make optional steps return `completed` with warning artifacts instead of `failed`.

## Pages project names

| Custom domain | Wrangler project name |
|---|---|
| `admin-scena.walter-ai.cloud` | `scena-admin` |
| `scena.walter-ai.cloud` | `scena` |

Always check `wrangler pages project list` before deploying — project name != domain name.

### Cloudflare Workers subrequest limit (critical pitfall)

A single Worker invocation has a **1000 subrequest limit**. Polling loops burn through this fast:
- Each Kie `createTask` = 1 subrequest
- Each Kie `recordInfo` poll = 1 subrequest
- 3 image gens × 10 polls each = 30+ subrequests just for polling
- Add Gemini analysis calls, validation, webhooks → easily hits 1000

**Fixes applied:**
1. Reduce polling to 10 attempts max (was 30)
2. Make optional steps (sheets, storyboard) **non-fatal** — catch errors, return `status: 'completed'` with warning artifact, continue pipeline
3. Use async webhook pattern for video generation (submit + return, resume on callback)
4. Never do sync polling for video generation — always submit and wait for webhook

**Pattern for non-fatal steps:**
```typescript
try {
  const result = await callKieImageGen(...);
  return { status: 'completed', artifacts: [...] };
} catch (e) {
  // Non-fatal: continue without this artifact
  return {
    status: 'completed',
    artifacts: [{ step: 'step_name', type: 'warning', data: { error: e.message, fallback: 'proceeding without X' } }],
  };
}
```

### Video URL validation (HEAD + GET Range fallback)

Some CDNs reject HEAD requests but serve GET fine (GCS returns 403, some CDNs return 522):
```typescript
let resp = await fetch(videoUrl, { method: 'HEAD' });
if (!resp.ok) {
  resp = await fetch(videoUrl, { method: 'GET', headers: { 'Range': 'bytes=0-0' } });
}
if (!resp.ok && resp.status !== 206) {
  return { status: 'failed', error: `Not accessible: HTTP ${resp.status}` };
}
```
Accept 206 (Partial Content) as success — it means the URL is valid and accessible.

Guided intake pattern:
- `/start` or project-launch text should create `notes.project_intake` and show inline buttons.
- `/start` must first introduce Scena, explain its role, and invite the user to describe the project in text or voice. Do not start with shallow `Vidéo / Image / UGC` buttons; start from deeper entrypoints like product, idea, zero, or existing brief.
- `/reset` must clear client chat/memory state (`clients.notes/context/summary/portfolio`, `tenant_memory_entries`, `tenant_memory_events`, `agent_log`, and tenant memory fields) and relaunch the same `/start` flow.
- Start global, then refine: entrypoint → objective → media/livrable → style → format → plan + short summary/confirmation.
- Recap before validation must include the estimated price in user credits, and the validation button should repeat that credit price when known.
- Intake callbacks must append the next Scena message with `sendMessage`; do not replace previous questions with `editMessageText`. If needed, only call `editMessageReplyMarkup` to remove stale buttons from the previous message while keeping the text visible in chat history.
- Every question must stay concise and include buttons, but free-text replies must be parsed and preserved in `project_intake.answers_text` / `brief_text`; do not force button-only UX. When a free-text/audio answer adds context but does not resolve the current missing choice, explicitly acknowledge it (`J’ai noté: ...`) before repeating the next missing question so the user sees that context was captured. Once intake reaches `summary`, do not blindly append every follow-up to `brief_text` and repeat the recap: answer plan/parameter questions conversationally, apply direct edits like `change par 3:4 format`, then keep validation buttons visible. Button proposals should be ranked from the current brief context (e.g. luxury perfume → Premium first; TikTok/creator → UGC/9:16 first), with the top context match visibly recommended.
- Do not rely on keyword-only heuristics for “intelligent” intake adaptation. For real client text/audio context, ask OpenRouter `qwen/qwen3.6-plus` for structured recommendations and use those arrays to reorder buttons before falling back to local keyword scoring. Mark the top Qwen/context recommendation with `⭐`.
- Infer common text choices: `j’ai un produit/parfum/boisson` → entrypoint product, `brief/script` → brief, `zéro/pas d’idée` → zero, `idée/je veux` → idea, `vidéo/reel/ugc` → video, `image/visuel` → image, `premium/luxe` → premium, `vertical/9:16/reel` → 9:16, etc.
- For image-only messages, reply with action buttons (animate / edit / ideate) instead of a numbered text-only menu.
- Voice messages should use a two-stage pipeline: (1) STT/transcription uses Gemini Developer API model `gemini-3.1-flash-lite-preview` internally (the non-preview `gemini-3.1-flash-lite` returns 404 on `v1beta generateContent`), but do NOT show the full transcript to the user; (2) run the transcript through OpenRouter `qwen/qwen3.6-plus` for structured brief understanding, chat/orchestration, and tool-calling decisions. Qwen must produce a non-truncated user-facing synthesis plus extracted fields/recommendations (`entrypoint`, `objective`, `media`, `style`, `aspect_ratio`, `recommendations`). The Telegram reply should display the Qwen synthesis, not raw STT output, and route through the same text/intake flow.

Use a 4-stage generation approval policy with **two distinct durable transitions**:

1. vague brief
   - ask only 2-4 ultra-targeted missing questions
   - no production tool call
2. clear brief, not yet recorded
   - call `record_project_plan` (control-plane tool, always allowed even if a workflow run exists)
   - show a short synthesis and the expected workflow
3. brief approval
   - accept explicit brief-validation language such as `je valide le brief`, `brief validé`, `je confirme le cadrage`, or a bare `je valide`
   - create the D1 `workflow_run`, then confirm `Brief validé et enregistré`; never claim this before the D1 write succeeds
   - automatically advance internal no-tool/non-validation steps while carrying their instructions into the execution prompt
   - show the credit estimate and ask for a separate production launch
4. production approval
   - accept concise launch language such as `Je lance`, `vas-y`, `ok lance`, `go`, `execute`, `fais-le`, `tu peux lancer`
   - reject planning/cadrage/brief language as production approval
   - only then allow `generate_*`

After each asset delivery, ask for validation in one short line such as `C'est le rendu voulu ? Ajuste ou valide ✅`.

Implementation pattern:
- keep `hasBriefApproval()` and `hasProductionApproval()` separate; `hasExecutionApproval()` may remain an alias for production compatibility
- scope active workflow-run lookup through `tenant_agent_config.active_project_id` and `workflow_runs.project_id`; if no active project is configured, ignore historical runs
- reconcile `waiting_async` runs against their backing job; terminal `archived_stale`/`archived_failed` jobs must fail the run/project and clear the active-project pointer
- `record_project_plan` bypasses workflow-order gating but must not advance the current workflow step unless it is that step's declared `tool_name`
- regression-test brief vs production approval, no-active-project isolation, archived jobs, internal no-tool steps, and control-plane tool behavior

### Tools (Function Calling)
```
generate_image(prompt, style, aspect_ratio)     → PiAPI Nano Banana 2 (Fal.ai fallback)
generate_video(prompt, image_ref_url, duration)  → PiAPI Seedance 2 Fast
generate_voice(text, emotion)                    → TTS provider
analyze_image(image_url, focus)                  → Gemini 3 Flash via OpenRouter
mark_project_complete(final_media_url, media_type) → Archive + reset state
```

### Context Compaction (Rolling Summary)
When context > 8 messages → LLM call to summarize → replace context with summary. Keeps D1 small and OpenRouter costs low.

## Cloudflare Setup

### Wrangler Authentication (Global API Key)
```bash
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com wrangler deploy
```
NOT `CLOUDFLARE_API_TOKEN` — Global API Key has full access.

### Secrets (via Cloudflare API, NOT wrangler.toml vars)
```python
# PUT https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/{name}/secrets
body = {"name": "OPENROUTER_API_KEY", "text": "sk-or-...", "type": "secret_text"}
```

### D1 Schema (tables)
- `clients` — matricule, name, telegram_bot_token, state, context, summary, portfolio, credits
- `video_jobs` — client_id, input_prompt, input_image_urls, status, piapi_task_id, output_url
- `image_jobs` — client_id, input_prompt, style, status, output_url
- `voice_jobs` — client_id, input_text, emotion, status, output_url
- `credit_ledger` — client_id, type, amount, balance_after
- `agent_log` — client_id, role, content, tool_name

## Deployment

```bash
# Global API Key auth (required for full Workers/D1 access)
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com npx wrangler deploy

# D1 remote queries (without --remote it hits local sqlite)
npx wrangler d1 execute scena-db --remote --command "SELECT * FROM clients"
npx wrangler d1 execute scena-db --remote --json --command "SELECT COUNT(*) FROM clients"

# Secrets list
npx wrangler secret list --name scena-api
```

### DNS Routing
- `admin-scena.walter-ai.cloud` → CNAME to scena-admin.pages.dev (Pages)
- `scena.walter-ai.cloud` → CNAME to scena.pages.dev (Pages)
- `api.walter-ai.cloud` → CNAME to Cloudflare Tunnel (VM), NOT the Worker
- Worker is also accessible at `scena-api.lucas-jouvencon.workers.dev`
- To route `api.walter-ai.cloud` to the Worker instead: add a Worker route in CF dashboard or use `wrangler` route commands

## Adding a New Video Provider (e.g., Kie.ai)

When adding a new video generation provider to Scena, follow this 5-step pattern. Example: Kie.ai Seedance 2.0 integration.

### 1. Model Catalog — `orchestration_config.ts`

Add entries to `BUILTIN_MODEL_CATALOG` with `provider: 'kie'` (or the new provider slug):

```typescript
{
  id: 'video-kie-seedance-2-fast',
  action_type: 'video_gen',
  provider: 'kie',
  model_id: 'bytedance/seedance-2-fast',
  label: 'Seedance 2 Fast (Kie.ai)',
  family: 'Seedance 2',
  media_kind: 'video',
  mode: 'text-to-video / image-to-video',
  supports_image_ref: true,
  default_params: { duration: '5', aspect_ratio: '9:16', resolution: '720p' },
}
```

Remove any hard `provider === 'fal'` filters in `listModelCatalog()` so the new provider appears in admin UI.

### 2. Env Interface — `agent.ts` + `index.ts`

Add the API key to both `Env` interfaces:

```typescript
export interface Env {
  DB: D1Database;
  PIAPI_API_KEY: string;
  FAL_API_KEY: string;
  KIE_API_KEY: string;  // ← new
  OPENROUTER_API_KEY: string;
  // ...
}
```

### 3. Provider Branch — `agent.ts` in `submitSingleVideoGeneration()`

Add an `else if (routeProvider === 'kie')` branch before the PiAPI fallback:

```typescript
} else if (routeProvider === 'kie') {
  const kieModelId = requestedModelId || 'bytedance/seedance-2-fast';
  await env.DB.prepare('UPDATE video_jobs SET model = ? WHERE id = ?').bind(kieModelId, jobId).run();
  const kiePayload: any = {
    model: kieModelId,
    callBackUrl: 'https://api.walter-ai.cloud/webhook/kie',
    input: {
      prompt: injected.prompt,
      resolution: resolution || '720p',
      aspect_ratio: aspectRatio || '9:16',
      duration: durationInt || 5,
      generate_audio: false,
    },
  };
  if (hasRef) kiePayload.input.first_frame_url = imageUrl;
  // POST to https://api.kie.ai/api/v1/jobs/createTask
  // On success: UPDATE video_jobs SET piapi_task_id = ?, piapi_status = 'submitted'
  // Return { success: true, state: 'submitted', job_id, request_id: taskId }
}
```

Key: reuse the existing `video_jobs` table — the `piapi_task_id` column stores the external task ID regardless of provider.

### 4. Webhook Handler — `index.ts`

Add route + handler:

```typescript
// Route
if (path === "/webhook/kie" && method === "POST") {
  return await handleKieWebhook(request, env);
}

// Handler pattern
async function handleKieWebhook(request: Request, env: Env): Promise<Response> {
  const body = await request.json<any>();
  const taskData = body.data || body;
  const taskId = taskData.taskId || taskData.task_id;
  const status = String(taskData.status || taskData.msg || '').toLowerCase();
  const job = await env.DB.prepare("SELECT * FROM video_jobs WHERE piapi_task_id = ?").bind(taskId).first<any>();
  // completed → UPDATE status, send Telegram video, recordWorkflowAsyncResult
  // failed → UPDATE status, refund credits, notify client
}
```

### 5. Deploy Secret + Update D1 Route

```bash
# Upload secret
echo "$KIE_KEY" | npx wrangler secret put KIE_API_KEY --name scena-api

# Deploy
npx wrangler deploy

# Set as default video provider in D1
INSERT INTO action_model_routes (id, action_type, title, provider, model_id, enabled, priority)
VALUES ('default-video-kie', 'video_gen', 'Default Kie Video', 'kie', 'bytedance/seedance-2-fast', 1, 1)
ON CONFLICT(id) DO UPDATE SET provider='kie', model_id='bytedance/seedance-2-fast', enabled=1;
```

### Pitfalls
- Do NOT create a separate jobs table — `video_jobs` is provider-agnostic. The `piapi_task_id` name is legacy but stores any provider's task ID.
- The `routeProvider` variable in `submitSingleVideoGeneration` was previously hardcoded to `'fal'`. Change it to `requestedProvider || 'fal'` so the `action_model_routes` provider field actually routes requests.
- Kie.ai uses `callBackUrl` (camelCase) in the payload, not `webhook_url`.
- Always test the webhook route with `curl -X POST https://scena-api.lucas-jouvencon.workers.dev/webhook/kie` after deploy.

## Prompt Injection Middleware (PRE_PROMPTS_DICTIONARY)

L'agent Mimo génère un payload minimaliste (`prompt` = sujet court + `style`). Le Worker intercepte et injecte la "recette qualité agence" avant l'envoi à PiAPI/Fal.ai.

```typescript
// tools.ts — Dictionary de 6 styles
export const PRE_PROMPTS_DICTIONARY: Record<string, PrePromptEntry> = {
  cinematic: { image_prompt: "...{SUBJECT}...", video_prompt: "...{SUBJECT}...", negative_prompt: "..." },
  ugc: { ... },
  minimalist: { ... },
  product_shot: { ... },
  lifestyle: { ... },
  dramatic: { ... },
};

// Injection function
export function injectPrePrompt(style: string, subject: string, mediaType: "image" | "video") {
  const entry = PRE_PROMPTS_DICTIONARY[style] || PRE_PROMPTS_DICTIONARY["cinematic"];
  const template = mediaType === "image" ? entry.image_prompt : entry.video_prompt;
  return { prompt: template.replace(/\{SUBJECT\}/g, subject), negative_prompt: entry.negative_prompt };
}

// Usage in agent.ts — toolGenerateImage / toolGenerateVideo
const injected = injectPrePrompt(args.style || "cinematic", args.prompt, "image");
const falPayload = { prompt: injected.prompt, negative_prompt: injected.negative_prompt, ... };
```

**Pattern**: Mimo (LLM) = décide QUOI + STYLE. Worker (code) = injecte COMMENT (qualité). Sépare raisonnement et craft.

## CORS Pattern for Worker Endpoints

When a Cloudflare Pages frontend calls a Worker API, CORS headers must be manually added to EVERY response. The Worker doesn't auto-handle this.

```typescript
// Define allowed origins
const ALLOWED_ORIGINS = [
  "https://admin-scena.walter-ai.cloud",
  "https://scena.walter-ai.cloud",
  "http://localhost:3000",
];

// CORS helper — also allow *.pages.dev for preview deployments
function getCorsHeaders(request: Request): Record<string, string> {
  const origin = request.headers.get("Origin") || "";
  const allowed = ALLOWED_ORIGINS.includes(origin) || origin.endsWith(".pages.dev") ? origin : "";
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
    "Vary": "Origin",
  };
}

// In fetch handler — handle preflight
if (method === "OPTIONS") {
  return new Response(null, { headers: getCorsHeaders(request) });
}

// For each route — wrap response with CORS headers
if (path.startsWith("/api/client/")) {
  const cors = getCorsHeaders(request);
  const resp = await handleClientPortal(request, env, path, method);
  const newHeaders = new Headers(resp.headers);
  for (const [k, v] of Object.entries(cors)) newHeaders.set(k, v);
  return new Response(resp.body, { status: resp.status, headers: newHeaders });
}
```

**Critical**: Without this wrapper, all cross-origin fetch calls fail silently with `ERR_FAILED`. The `json()` helper alone doesn't add CORS headers. Every route handler needs the CORS wrapper.

## Admin UI Patterns

### Bot Pool vs Client Bots
The admin "Bots" tab queries `/api/admin/bots` which reads `bot_pool` table. But client bots are stored directly in `clients.telegram_bot_token/username`. The admin UI should show BOTH:
- Pool bots (available for assignment)
- Client bots (already assigned, from `clients` table)

`bot_pool` schema: `bot_username TEXT PRIMARY KEY, bot_token TEXT, client_id INTEGER, status TEXT, created_at TEXT`

### Credits Modal
Don't use `prompt()` for admin input — unreliable across browsers. Use proper HTML modals with `<input type="number">`, quick-select buttons, and Enter key support.

### Deployment Auth (Global API Key)
```bash
CLOUDFLARE_API_KEY=cfk_... CLOUDFLARE_EMAIL=lucas.jouvencon@gmail.com npx wrangler pages deploy . --project-name=scena-admin
```
`CLOUDFLARE_API_TOKEN` doesn't work for Pages deploy — must use Global API Key + Email.

### Reset Stuck Client State
When image/video jobs fail and client state stays in `waiting_image`, add admin endpoint:

```typescript
// In handleAdminAPI
if (path.match(/^\/api\/admin\/clients\/\d+\/reset-state$/) && request.method === "POST") {
  const clientId = path.split("/")[4];
  await env.DB.prepare("UPDATE clients SET state = 'idle', context = '[]', summary = '', updated_at = datetime('now') WHERE id = ?").bind(clientId).run();
  return json({ ok: true, state: "idle" });
}
```

Admin UI button:
```javascript
async function resetClientState(){
  if(!_currentClient)return;
  if(!confirm('Reset client state to idle?'))return;
  await fetch(API+'/api/admin/clients/'+_currentClient+'/reset-state',{method:'POST',headers:{'Authorization':'Bearer '+ADMIN_TOKEN}});
  openDetail(_currentClient);
}
```

## Autonomous Pipeline Runner (SaaS Connect)

The `/api/saas/pipeline` endpoint runs a full video generation workflow **without a chat agent** — directly calling providers (Gemini for analysis, Kie for image/video). This is the "Scena Engine" that SaaS partners plug into.

### Architecture

```
POST /api/saas/pipeline (source_video + brief + params + Bearer sk_scena_*)
  → pipeline_runner.ts orchestrates:
    1. ingest_inputs (validate required fields)
    2. validate_source (HEAD request on video URL)
    3. source_analysis (Gemini via OpenRouter — strict JSON scene breakdown)
    4. modification_plan (Gemini — atomic changes from client brief)
    5. generate_sheets (Kie GPT Image 2 — product/character sheets)
    6. generate_storyboard (Kie GPT Image 2 — key visual panel)
    7. compile_clips (build canonical clip plan from analysis + modifications)
    8. submit_generation (Kie Seedance 2 Fast — async, returns task IDs)
    → 202 { pipeline_id, status: "waiting_async", steps_completed }
    → Webhooks: pipeline.started, step.started, step.completed at each step

  Kie webhook arrives → /webhook/pipeline/kie-video
    → resumePipelineAfterAsync()
    → qa_validation
    → export_package
    → pipeline.completed webhook with full output
```

### Key files

- `workers/api/src/pipeline_runner.ts` — autonomous orchestrator (state machine, step handlers, BYOK, webhooks)
- `workers/api/src/saas_connect.ts` — route wiring: `createPipeline()`, `getPipelineStatusResponse()`, `handlePipelineKieWebhook()`
- `d1/saas-pipeline-runs.sql` — D1 migration for `saas_pipeline_runs` table
- `tests/pipeline-runner.test.mjs` — 8 tests (validation, status, webhook resume, full flow, failure handling, progression webhooks)

### Pipeline step handlers pattern

Each step is a function `(ctx: PipelineContext) => Promise<PipelineStepResult>`:
- `status: 'completed'` — step done, artifacts recorded
- `status: 'failed'` — step failed, pipeline stops, failure webhook sent
- `status: 'waiting_async'` — async job submitted (video gen), pipeline pauses, resumes via webhook

Artifacts accumulate in `run.artifacts_json` and are available to subsequent steps via `findArtifact(run, stepKey, type?)`.

### BYOK (Bring Your Own Key)

Already wired in existing SaaS Connect:
- `encrypted_provider_keys_json` on `saas_connections` stores encrypted provider keys per connection
- `getProviderKeys(env, connection)` decrypts and returns `{ kie: '...', fal: '...' }`
- Each `submitKie*` function uses `providerKeys.kie || env.KIE_API_KEY` (client key → fallback global)

### Progression webhooks

`sendPipelineWebhook(env, run, event, data)` sends to `run.callback_url` with:
- `X-Scena-Event`: pipeline.started | step.started | step.completed | step.failed | pipeline.completed | pipeline.failed
- `X-Scena-Timestamp`: unix seconds
- `X-Scena-Signature`: HMAC-SHA256 of `timestamp.rawBody` using `SAAS_CREDENTIAL_SECRET`
- `X-Scena-Pipeline-Id`: the pipeline run ID

### Gemini analysis via OpenRouter

The pipeline calls Gemini for video analysis through OpenRouter (not directly):
```typescript
fetch('https://openrouter.ai/api/v1/chat/completions', {
  model: 'google/gemini-2.5-flash',
  messages: [{ role: 'user', content: [
    { type: 'text', text: analysisPrompt },
    { type: 'video_url', video_url: { url: videoUrl } },
  ]}],
  response_format: { type: 'json_object' },
  temperature: 0.2,
})
```

### Pitfalls (Pipeline)

- The pipeline uses `stepInput` from `parseJson(run.input_json)` — always re-parse, never rely on stale references.
- Kie image gen uses polling (`pollKieTask`) since images are fast. Video gen is async (webhook resume).
- `pipeline_runner.ts` does NOT use the chat agent — it calls providers directly. This is intentional for SaaS Connect where there's no Telegram conversation.
- The `saas_pipeline_runs` table is separate from `workflow_runs` (which is for the chat-agent flow). Don't mix them.
- Pipeline webhooks use the same HMAC signing pattern as SaaS Connect webhooks but with `X-Scena-Pipeline-Id` header instead of `X-Scena-Job-Id`.
- The video analysis prompt must ask for strict JSON with `response_format: { type: 'json_object' }` — Gemini returns raw text otherwise.
- Kie video generation callback URL is `/webhook/pipeline/kie-video` (not `/webhook/saas/kie`). The pipeline webhook route must be separate from the SaaS Connect webhook route.

## Pitfalls — General Scena — `Buffer.from(...)` throws "Buffer is not defined". Fix:
  - `Buffer.from(str).toString("base64")` → `btoa(str)`
  - `Buffer.from(b64, "base64").toString()` → `atob(b64)`
  - Found in admin login handler `handleAdminLogin` and `validateAdminToken` in index.ts
  - Worker deploy with broken Buffer = 500 on `/api/admin/login` every time
- D1 column `notes` must be added via ALTER TABLE (not in original schema)
- Wrangler vars in wrangler.toml conflict with secrets of same name — use secrets only
- workers.dev subdomain has Cloudflare bot protection (403) — use custom domain
- PiAPI needs `User-Agent` header or Cloudflare blocks the request
- OpenRouter primary LLM for Scena agent/intake should be `qwen/qwen3.6-plus` unless Lucas explicitly changes routing. If tests or code still refer to Kimi/Moonshot for the primary chat/reasoning path, treat it as stale routing and migrate constants/tests to a neutral `PRIMARY_MODEL` style name.
- Image jobs: track by most recent pending job (PiAPI webhook doesn't include job_id)
- **D1 column names display bug**: wrangler JSON output can show `***` instead of real column name. The DB column is correct. Diagnose with `SELECT hex(name) FROM pragma_table_info('image_jobs')`. Example: `fal_request_id` (hex `66616C5F726571756573745F6964`) displayed as `***` with len=14 in JSON.
- **Stripe keys**: `sk_live_` or `rk_live_` = API key (for Stripe API calls). `whsec_` = webhook signing secret (for verifying incoming webhooks). They are DIFFERENT. Get `whsec_` from Stripe Dashboard → Developers → Webhooks → endpoint → Signing secret. Can also create endpoint via API: `POST /v1/webhook_endpoints` with `url` and `enabled_events[]`.
- **Wrangler secret put**: pipe the value via stdin, not as CLI arg: `echo "value" | npx wrangler secret put NAME --name scena-api`
- **Admin Pages stale session bug**: if `sessionStorage` restores an expired `scena_token`, the dashboard can hide the login overlay and render fake red integration cards from `{error:"Unauthorized"}` responses. Fix the frontend with two rules: (1) auto-login must immediately call `loadAll()` after restoring the token, and (2) all admin fetches should go through a shared helper like `apiFetchJson()` that detects `401/403` or `error:"Unauthorized"`, clears the token, and shows the login overlay again instead of rendering bogus error states.
- **`env.waitUntil` is NOT available** — `waitUntil` is on the execution context (`ctx`), not on `env`. The `fetch` handler is `fetch(request, env, ctx)` but `ctx` was never passed through to tool functions. This causes `Exception: env.waitUntil is not a function` when trying to start async polling (Fal.ai video, image). Fix: pass `ctx` (or just `ctx.waitUntil` as a callback) through the call chain: `fetch → handleTelegramWebhook → handleAgentMessage → executeTool → toolGenerateVideo`. Or restructure so polling is kicked off at the top-level handler where `ctx` is available.
- **Fal.ai video (Grok) image URL**: Fal.ai needs a direct, publicly accessible URL. The proxy URL `https://api.walter-ai.cloud/proxy/media/...` redirects to Telegram which may timeout (522) or be rejected. For image-to-video, either: (a) fetch the image bytes from proxy and re-upload to a public CDN, or (b) pass the direct Telegram file URL with bot token to Fal.ai (security trade-off).
- **Fal.ai Grok video model**: endpoint is `xai/grok-imagine-video/image-to-video` (with image) or `xai/grok-imagine-video/text-to-video` (text only). Uses `queue.fal.run` (async). Payload: `{ prompt, duration, aspect_ratio, cfg_scale, start_image_url? }`. Poll via `queue.fal.run/xai/grok-imagine-video/requests/{request_id}`.
- **Worker test helper import rewriting**: tests load Worker TS files by copying `workers/api/src/*.ts` into `/tmp/scena-worker-*` and importing with Node `--experimental-strip-types`. Relative imports like `from "./tools"` must be rewritten to `from "./tools.ts"`. Regex must handle `./` and `../` paths, not only `.` followed by letters; otherwise many tests fail with `ERR_MODULE_NOT_FOUND` from `/tmp/scena-worker-*/tools` or `/agent`.
- **Kimi/OpenRouter migration tests**: legacy tests often mocked Gemini via URLs containing `:generateContent` and returned `candidates[].content.parts[].functionCall`. When the runtime calls OpenRouter `/api/v1/chat/completions`, update `installFetchMock` or each test to return OpenAI-style `choices[].message.tool_calls[]` with `function.arguments` as a JSON string. A compatibility bridge in the helper can convert old Gemini functionCall mocks into OpenRouter tool calls during migration.

## Debugging D1 Without Wrangler Auth

When `wrangler d1 execute --remote` fails with "set CLOUDFLARE_API_TOKEN", query D1 directly via REST API using the **Global API Key** (`cfk_...`), NOT the API token (`cfut_...`).

**Critical distinction**:
- `CLOUDFLARE_API_TOKEN` (`cfut_...`) = fine-grained token. Works for Worker deploys, secrets, Pages. **Does NOT work for D1 REST API** → returns `403` with error `7403` ("account not authorized for this service").
- `CLOUDFLARE_API_KEY` (`cfk_...`) = Global API Key. Has full access including D1 REST API.

```python
import requests

CF_API_KEY = "cfk_..."       # Global API Key, NOT cfut_ token
CF_EMAIL = "lucas.jouvencon@gmail.com"
ACCOUNT_ID = "«secret:vault»"
DB_ID = "3567d347-37d7-45d5-b348-3dfc5f674006"

url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/d1/database/{DB_ID}/query"
headers = {
    "X-Auth-Email": CF_EMAIL,
    "X-Auth-Key": CF_API_KEY,     # ← cfk_... required
    "Content-Type": "application/json"
}
payload = {"sql": "SELECT * FROM video_jobs ORDER BY rowid DESC LIMIT 10"}
resp = requests.post(url, headers=headers, json=payload)
data = resp.json()
# data["result"][0]["results"] = list of rows as dicts
```

Use this to inspect stuck jobs, check error messages, and verify piapi_task_id/status without needing a properly configured wrangler CLI.
