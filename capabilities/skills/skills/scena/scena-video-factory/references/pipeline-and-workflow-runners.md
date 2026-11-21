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

## Locked decisions
- `POST /api/saas/pipeline` with flower.mp4 → 202, 7 steps completed, status `waiting_async`
- Steps completed: ingest_inputs → validate_source → source_analysis → modification_plan → generate_sheets → generate_storyboard → compile_clips
- Kie Seedance video submitted, waiting for webhook resume
- Sheets/storyboard are non-fatal (pipeline continues if Kie image gen hits subrequest limit)

**Admin secret**: Stored as Worker secret (not in vault). Use `vault get scena_connect/sandbox_api_key` for SaaS API testing.

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
