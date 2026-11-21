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
