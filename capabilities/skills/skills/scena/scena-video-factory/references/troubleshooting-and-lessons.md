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
