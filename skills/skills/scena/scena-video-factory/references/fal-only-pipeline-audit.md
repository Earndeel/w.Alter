# Fal-only SaaS video pipeline audit notes

Use this when auditing or repairing the Scena autonomous video generation engine after a Kie.ai → Fal.ai migration.

## Target contract

Client-facing SaaS API must be Fal BYOK only:
- Client provides: Scena API key, Fal.ai API key during connection setup, source media, brief, callback URL, optional product/brand inputs.
- Client must not choose: provider, model, endpoint, or routing policy.
- Workflow owns: OpenRouter analysis/planning model, Fal image model, Fal video model, fallback strategy, QA/export.

## Critical audit checklist

1. Buildability first
   - Import `workers/api/src/saas_connect.ts` with Node `--experimental-strip-types` before deeper debugging.
   - Watch for broken migration artifacts such as object fields inserted into `.bind(...)` argument lists.
   - Node strip-types can choke on some TS syntax; prefer `{ [key: string]: X }` over `Record<string, X>` in `.ts` files imported directly from `.mjs` tests.

2. Remove Kie from runtime path
   - `/api/saas/pipeline` must not pass `KIE_API_KEY` or `GEMINI_API_KEY` into `PipelineEnv`.
   - `index.ts` route must use `/webhook/pipeline/fal-video`, not `/webhook/pipeline/kie-video`.
   - Replace `handlePipelineKieWebhook` with a Fal webhook handler that keys on `request_id`, not `taskId`.
   - `/api/saas/generate` video jobs must not call `submitKieVideoJob`.

3. Enforce workflow-managed models server-side
   - Do not trust UI simplification. Server must ignore or reject `body.provider`, `input.provider`, `body.model_id`, `input.model_id`, `model_profile` from SaaS clients.
   - Store/display provider as `fal`; store model as selected by internal workflow policy.

4. Make BYOK real
   - `pipeline_runner.ts` must decrypt `connection.encrypted_provider_keys_json` and use `providerKeys.fal` before falling back to `env.FAL_API_KEY`.
   - Avoid stubs returning `{}` from `getProviderKeys`; that silently turns BYOK into platform-key execution.

5. Fal response extraction
   - Image sync endpoints commonly return `images[0].url`; do not only read `outputUrl`, `output_url`, or `imageUrl`.
   - Video queue submissions return `request_id` plus often `status_url`/`response_url`; store those artifacts instead of reconstructing URLs later when possible.
   - Video completion extraction should check `video.url`, `output.video_url`, `data.video.url`, `result.video.url`, and fetched `response_url` payloads.

6. Recovery path
   - Webhook-only async pipelines can stay `waiting_async` forever.
   - Add/reuse cron sweeper: find `saas_pipeline_runs.status='waiting_async'`, poll Fal status/response URLs, then call resume logic.

## Minimal tests to require

- Create SaaS connection with `{ provider_keys: { fal: '...' } }` only.
- Client-supplied provider/model is ignored or rejected.
- Pipeline decrypts BYOK Fal key and uses it.
- Sheets/storyboard extract `images[0].url`.
- Generation stores `request_id`, `status_url`, `response_url`.
- `/webhook/pipeline/fal-video` resumes a waiting pipeline.
- Final status exposes video output URL and sends signed client webhook.
- No Kie symbols remain in SaaS/pipeline runtime paths except explicitly marked legacy/archive code.
