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
