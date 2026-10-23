# Pipeline API Contracts

## POST /api/saas/pipeline

Launch autonomous video generation pipeline.

### Request

```json
{
  "source_video_url": "https://example.com/source.mp4",  // required
  "brief": "Create a premium product reveal",             // required
  "product_name": "Parfum Noir",                          // optional
  "product_image_url": "https://example.com/product.png", // optional
  "character_image_url": "https://example.com/char.png",  // optional
  "brand_assets": ["https://example.com/logo.png"],       // optional
  "target_platform": "tiktok",       // default: tiktok
  "target_aspect_ratio": "9:16",     // default: 9:16
  "target_language": "fr-FR",        // default: fr-FR
  "target_duration": 10,             // default: 10 seconds
  "model_profile": "seedance-2-fast", // default: seedance-2-fast
  "callback_url": "https://partner.com/webhook",  // optional
  "external_user_id": "user_123",    // optional, passed through to webhooks
  "external_project_id": "proj_456", // optional, passed through to webhooks
  "variants": 1                      // optional, 1-5
}
```

### Response (202 Accepted — async video generation)

```json
{
  "ok": true,
  "pipeline_id": "pipe_abc123",
  "status": "waiting_async",
  "steps_completed": ["ingest_inputs", "validate_source", "source_analysis", "modification_plan", "generate_sheets", "generate_storyboard", "compile_clips"],
  "poll_url": "/api/saas/pipeline/pipe_abc123/status",
  "note": "Video generation submitted. Poll status_url or wait for webhook callback."
}
```

### Response (200 OK — no async step needed)

```json
{
  "ok": true,
  "pipeline_id": "pipe_abc123",
  "status": "completed",
  "steps_completed": ["ingest_inputs", "validate_source", "...", "export_package"]
}
```

### Response (400 — validation)

```json
{"error": "source_video_url is required"}
{"error": "brief is required"}
```

### Response (401 — auth)

```json
{"error": "Missing Scena API key"}
{"error": "Invalid Scena API key"}
```

## GET /api/saas/pipeline/:id/status

Poll pipeline status.

### Response

```json
{
  "ok": true,
  "pipeline_id": "pipe_abc123",
  "status": "running|waiting_async|completed|failed",
  "current_step": "source_analysis",
  "connection_id": "conn_xyz",
  "external_user_id": "user_123",
  "external_project_id": "proj_456",
  "artifacts_count": 5,
  "error_message": "",
  "output": { "...only when completed..." },
  "created_at": "2026-05-25T11:26:53.405Z",
  "updated_at": "2026-05-25T11:28:35.239Z"
}
```

## Webhooks (progression)

Sent to `callback_url` at each step boundary.

### Headers

```
X-Scena-Event: pipeline.started|step.started|step.completed|step.failed|pipeline.completed|pipeline.failed
X-Scena-Timestamp: 1770000000
X-Scena-Signature: sha256=<hmac>
X-Scena-Pipeline-Id: pipe_abc123
```

### Events

| Event | Body fields | When |
|-------|-------------|------|
| `pipeline.started` | input{} | Pipeline created |
| `step.started` | step | Step begins |
| `step.completed` | step, async_job_id? | Step succeeds |
| `step.failed` | step, error | Step fails |
| `pipeline.completed` | output{} | All steps done |
| `pipeline.failed` | failed_step, error | Pipeline fails |

### Signature verification

```js
const signed = `${timestamp}.${rawBody}`;
const expected = hmacSha256(SCENA_WEBHOOK_SECRET, signed);
assert(req.headers['x-scena-signature'] === `sha256=${expected}`);
```

## Pipeline steps

| # | Step | Provider | Duration | Fatal? |
|---|------|----------|----------|--------|
| 1 | ingest_inputs | — | instant | yes |
| 2 | validate_source | HEAD/GET Range | 1-2s | yes |
| 3 | source_analysis | Gemini via OpenRouter | 10-30s | yes |
| 4 | modification_plan | Gemini via OpenRouter | 10-20s | yes |
| 5 | generate_sheets | Kie GPT Image 2 | 20-60s | no (non-fatal) |
| 6 | generate_storyboard | Kie GPT Image 2 | 20-40s | no (non-fatal) |
| 7 | compile_clips | — | instant | yes |
| 8 | submit_generation | Kie Seedance 2 Fast | 2-5s submit | yes |
| 9 | qa_validation | — | instant | yes |
| 10 | export_package | — | instant | yes |

## BYOK

Provider keys stored encrypted per connection (`encrypted_provider_keys_json`).
Decrypted by `getProviderKeys()` at runtime. Falls back to global env keys.

```json
{
  "provider_keys": {
    "kie": "kie_api_key_here",
    "fal": "fal_api_key_here"
  }
}
```

## POST /api/saas/connections (public — portal self-service)

Create a new SaaS connection. No admin auth required (public endpoint for portal).

### Request

```json
{
  "name": "My SaaS Partner",
  "tenant_id": "partner_acme",
  "callback_url": "https://partner.com/api/scena/webhook",
  "default_provider": "kie",
  "default_model_id": "bytedance/seedance-2-fast",
  "scopes": ["generate", "pipeline"],
  "provider_keys": { "kie": "optional_initial_key" }
}
```

### Response (201 Created)

```json
{
  "ok": true,
  "connection": { "id": "conn_abc", "name": "My SaaS Partner", "..." : "..." },
  "api_key": "sk_scena_...",
  "webhook_secret": "whsec_scena_...",
  "note": "Store api_key securely. It is returned only once."
}
```

## PATCH /api/saas/connections/:id/keys (client auth)

Update BYOK provider keys for a connection. Requires the connection's own API key.

### Headers

```
Authorization: Bearer sk_scena_...
Content-Type: application/json
```

### Request

```json
{
  "provider_keys": {
    "kie": "new_kie_key",
    "fal": "new_fal_key"
  }
}
```

### Response

```json
{ "ok": true, "updated_keys": ["kie", "fal"] }
```

### Errors

```json
{ "error": "provider_keys is required" }
{ "error": "Cannot update another connection" }
```

## Preset catalog (15 presets)

| Slug | Pack | Type | Description |
|------|------|------|-------------|
| `ugc_product_demo` | ugc | video_gen | UGC product demo, social format |
| `cinematic_product_reveal` | cinematic | video_gen | Premium reveal, dramatic lighting |
| `animation_subtle_motion` | animation | video_gen | Subtle image animation |
| `narrative_mini_story` | narrative | video_gen | Problem → desire → product story |
| `docu_explainer_short` | docu | video_gen | Documentary/explainer style |
| `image_to_image_campaign_visual` | image | image_to_image | Product → campaign visual |
| `social_proof_testimonial` | social | video_gen | Authentic testimonial |
| `product_tutorial_howto` | tutorial | video_gen | Step-by-step tutorial |
| `before_after_transformation` | transformation | video_gen | Before/after reveal |
| `event_launch_announcement` | event | video_gen | Product launch |
| `fashion_lookbook` | fashion | video_gen | Editorial fashion showcase |
| `food_lifestyle` | food | video_gen | Appetite appeal |
| `real_estate_walkthrough` | realestate | video_gen | Property tour |
| `text_to_video_concept` | text2video | video_gen | Pure text-to-video |
| `image_to_video_animation` | img2video | video_gen | Animate product photo |
