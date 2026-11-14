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
