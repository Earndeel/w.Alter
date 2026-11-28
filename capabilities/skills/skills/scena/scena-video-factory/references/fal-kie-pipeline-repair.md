# Fal + Kie Pipeline Repair Notes (2026-05-25)

## Trigger
User corrected the provider assumption: Kie must remain available for generation tests/legacy, while Fal.ai and OpenRouter remain core to the autonomous pipeline.

## Durable contract
- OpenRouter: LLM video analysis and modification planning.
- Fal.ai: primary image/video generation path.
- Kie.ai: retained as test/legacy provider for generation.
- Client-facing portal may be simple, but backend must keep both provider adapters functional.

## Required routes
Register all four routes in `workers/api/src/index.ts`:

```ts
/webhook/saas/fal      -> handleSaasProviderWebhook(..., 'fal')
/webhook/saas/kie      -> handleSaasProviderWebhook(..., 'kie')
/webhook/pipeline/fal-video -> handlePipelineFalWebhook
/webhook/pipeline/kie-video -> handlePipelineKieWebhook
```

## SaaS generation adapter requirements
`submitSingleSaasJob()` should dispatch by `job.provider` and `action_type`:

- `video_gen + fal` -> `submitFalVideoJob`
- `video_gen + kie` -> `submitKieVideoJob`
- `image_gen/image_to_image + fal` -> `submitFalImageJob`
- `image_gen/image_to_image + kie` -> `submitKieImageJob`

`createConnection()` default provider should derive from supplied provider keys: Fal key present -> `fal`; otherwise Kie fallback, unless explicitly set.

## BYOK envelope
`encrypted_provider_keys_json` uses the same AES-GCM envelope as `saas_connect.ts`:

```txt
v1.<base64url iv>.<base64url ciphertext>
```

Pipeline runners must actually decrypt this envelope and prefer `providerKeys.fal` / `providerKeys.kie` over global env keys. A stub returning `{}` silently disables BYOK.

## Fal extraction pitfalls
Fal image output can be any of:

```ts
result.images?.[0]?.url
result.image?.url
result.outputUrl
result.output_url
result.imageUrl
result.url
```

Fal video webhooks/results can use:

```ts
output.video_url
output.videoUrl
output.url
output.video?.url
output.videos?.[0]?.url
taskData.video_url
taskData.videoUrl
taskData.video?.url
taskData.url
```

## Metadata pitfall
When a code path submits to Fal, artifact/job metadata must not say `provider: 'kie'` or `model: 'bytedance/seedance-2-fast'`. That breaks auditability and webhook matching assumptions.

## Node strip-types pitfall
Node `--experimental-strip-types` can choke on TypeScript patterns in imported `.ts` files. Prefer index signatures like `{ [key: string]: X }` over `Record<string, X>` in files imported directly by `.mjs` tests.

## Verification checklist
Run in this order:

```bash
node --experimental-strip-types --test tests/saas-connect.test.mjs
node --experimental-strip-types --test tests/pipeline-runner.test.mjs
node --experimental-strip-types --test tests/client-credit-checkout-ui.test.mjs
node --experimental-strip-types --test tests/scena-vitrine.test.mjs
npm test
```

Expected targeted results after repair:
- SaaS Connect: 7/7
- Pipeline Runner: 8/8
- Checkout UI: 2/2
- Vitrine: 3/3
