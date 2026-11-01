---
name: multi-provider-image-gen
description: "Cross-provider image generation parameters — Atlas Cloud, Kie.ai, OpenAI native. How `size`, `quality`, `aspect_ratio` map differently per provider. Also covers: image generation fallback."
category: mlops
---

# Multi-Provider Image Generation

Unified guide to how different image generation providers expose resolution, quality, and ratio parameters for the same underlying models.

## Atlas Cloud (`api.atlascloud.ai`)

**Endpoint**: `POST /api/v1/model/generateImage`
**Auth**: `Authorization: Bearer <key>`
**Style**: OpenAI-compatible full parameter set

```json
{
  "model": "openai/gpt-image-2/text-to-image",
  "prompt": "...",
  "size": "1440x2560",
  "quality": "low",
  "n": 1,
  "enable_sync_mode": false,
  "enable_base64_output": false
}
```

### Parameters (full control)

| Field | Values | Description |
|-------|--------|-------------|
| `size` | `"1024x1024"`, `"1536x1024"`, `"1024x1536"`, `"768x1280"`, `"1280x768"`, `"1440x2560"`, `"4K"` | Exact pixel dimensions |
| `quality` | `"low"`, `"medium"`, `"high"` | Detail/realism level. `low` = faster + cheaper |
| `n` | 1–10 | Number of images |

### Async polling

Submit returns `data.id`. Poll at `/api/v1/model/prediction/{id}`:
```json
{"code": 200, "data": {"status": "completed", "outputs": ["https://...png"]}}
```

### Supported image models (via Atlas)

| Model ID | Type |
|----------|------|
| `baidu/ERNIE-Image-Turbo/text-to-image` | T2I (Baidu) |
| `openai/gpt-image-2/text-to-image` | T2I (OpenAI) |
| `openai/gpt-image-2/edit` | Image Edit (OpenAI) |
| `google/gemini-2.5-flash-image` | T2I (Google, limited via proxy) |

## Kie.ai (`api.kie.ai`)

**Endpoint**: `POST /api/v1/jobs/createTask`
**Auth**: `Authorization: Bearer <key>`
**Style**: Simplified Market API — auto-selects resolution/quality

### GPT Image 2 T2I

```json
{
  "model": "gpt-image-2-text-to-image",
  "callBackUrl": "https://your-domain.com/api/callback",
  "input": {
    "prompt": "...",
    "aspect_ratio": "auto"
  }
}
```

⚠️ **Only `prompt` and `aspect_ratio` ("auto" only) are exposed.** No `size`, no `quality` — Kie/OpenAI auto-selects.

### GPT Image 2 Edit

```json
{
  "model": "gpt-image-2-image-to-image",
  "callBackUrl": "https://your-domain.com/api/callback",
  "input": {
    "prompt": "...",
    "input_urls": ["https://example.com/image.png"],
    "aspect_ratio": "auto"
  }
}
```

### Video models (Grok Imagine, etc.)

Video models on Kie have **full parameters** — `resolution`, `duration`, `aspect_ratio`, prompts, etc. See `kie-video-generation` skill for details.

### Polling & Download

- Poll: `GET /api/v1/jobs/getTaskDetail?taskId=...` or `GET /api/v1/jobs/recordInfo?taskId=...`
- Download presigned URL: `POST /api/v1/common/download-url` with body `{"url": "https://tempfile..."}` (**field must be `"url"`, not `"file_url"`)

### Supported image models (via Kie Market)

| Model | ID | Params |
|-------|-----|--------|
| GPT Image 2 T2I | `gpt-image-2-text-to-image` | `prompt`, `aspect_ratio: "auto"` only |
| GPT Image 2 Edit | `gpt-image-2-image-to-image` | `prompt`, `input_urls`, `aspect_ratio: "auto"` |
| Grok Imagine T2I | `grok-imagine/text-to-image` | Market API |
| Grok Imagine I2I | `grok-imagine/image-to-image` | Market API |
| Z-Image | `z-image` | `prompt`, `aspect_ratio`, `nsfw_checker` |
| Various (Seedream, Nano Banana, Flux, Qwen, Ideogram, etc.) | Market IDs | Varies per model |

## OpenAI Native (`api.openai.com`)

**Endpoint**: `POST /v1/images/generations`
**Auth**: `Authorization: Bearer <key>`
**Style**: The standard — same params as Atlas Cloud

```json
{
  "model": "gpt-image-2",
  "prompt": "...",
  "size": "1536x1024",
  "quality": "low"
}
```

## Parameter Comparison

| Capability | Atlas Cloud | Kie.ai | OpenAI Native |
|------------|-------------|--------|---------------|
| `size` (exact pixels) | ✅ Full | ❌ Auto only | ✅ Full |
| `quality` (low/med/high) | ✅ Full | ❌ Auto only | ✅ Full |
| `aspect_ratio` | ❌ Via `size` | `"auto"` only | ❌ Via `size` |
| `n` (batch count) | ✅ 1–10 | ❌ Not available | ✅ 1–10 |
| Image edit/I2I | ✅ Via `/image-to-image/` model | ✅ Via `input_urls` | ✅ |
| Callback/webhooks | ❌ | ✅ `callBackUrl` | ❌ |
| Cost | Per gen | ~3× cheaper than OpenRouter | OpenAI pricing |

## Routing Decision

- **Use Atlas Cloud** when the client needs specific resolution (1440×2560, 4:3, etc.) and quality control (`low`/`high`)
- **Use Kie.ai** for default/scenario where auto resolution is fine — more economical, supports webhooks
- **Use OpenAI native** only when neither proxy has the model or for cost comparison

## Routing Rules (Scena)

**Default provider: Kie.ai** — fallback on 402 (funds depleted) → Atlas Cloud ERNIE.

| Use Case | Provider | Model |
|----------|----------|-------|
| GPT-Image 2 I2I | Kie.ai | grok-imagine/image-to-image |
| GPT-Image 2 T2I | Atlas Cloud | gpt-image-2/text-to-image |
| Rapide + cheap | Atlas Cloud | ERNIE-Image-Turbo |
| Fallback | Atlas Cloud | ERNIE-Image-Turbo |
| Vidéos I2V | Kie.ai | Seedance 2.0, Kling v2 |

## Atlas Cloud Async API (Detailed)

Atlas Cloud uses a **custom async API** for image generation — standard OpenAI-compatible endpoints do NOT work for image models.

### Submit + Poll Pattern
- Submit: `POST /api/v1/model/generateImage` → returns `data.id` as `prediction_id`
- Poll: `GET /api/v1/model/prediction/{prediction_id}` → check `data.status`
- **CRITICAL**: Failed jobs still return `code: 200`! Always check `data.status`.

### Model Name Convention
Always append `/text-to-image` suffix: `baidu/ERNIE-Image-Turbo/text-to-image`. Without it → 404.

### GPT Image 2 Sizing
Requires BOTH width and height to be multiples of 16.
- ✅ `1024x1792`, `1024x1024`, `1792x1024`, `2048x2048`
- ❌ `1080x1920` (1080/16=67.5, NOT a multiple)

### Base64 Output
**ALWAYS use `enable_base64_output: true` for GPT Image 2.** URL-based output expires quickly — `NoSuchKey` XML errors from Aliyun OSS.

### Balance Exhaustion Fallback
When Atlas balance runs out (HTTP 402), fall back to `baidu/ERNIE-Image-Turbo/text-to-image` — ~10x cheaper.

### Available Models (May 2026)

| Model ID | Status | Avg time |
|----------|--------|----------|
| `baidu/ERNIE-Image-Turbo/text-to-image` | ✅ Active | ~9.5s/image |
| `openai/gpt-image-2/*` | ❌ Removed from Atlas | Use OpenAI direct API |
| `google/gemini-2.5-flash-image` | Unknown | Untested |

### Python Async Polling Script
See `scripts/generate_atlas_images.py` for reusable async generator with parallel polling.

### Full Atlas Cloud API Reference
See `references/atlas-cloud-provider.md` (if present) for complete endpoint details.

## Pitfalls

1. **Kie I2I/GPT Image 2**: Do NOT forward Fal-style fields (`output_format`, `resolution`, `num_images`, `safety_tolerance`) — they are silently ignored
2. **Atlas Cloud sync mode**: `enable_sync_mode: true` blocks until complete but may hit timeout for large renders. Prefer async + polling
3. **Kie download URLs**: The field name is `"url"` in the download-url request, not `"file_url"`. Wrong field returns `"图片url不能为空"`
4. **Image-to-image parameter naming varies by provider**: Fal uses `image_urls` (array), Flux uses `image_url` (string), Kie uses `input_urls` (array) — check each provider's docs

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **image-generation-fallback** — The provider fallback chain for images (OpenAI direct → Codex → Fal MCP → Atlas Cloud → Pollinations) when the preferred provider fails.
  Read `references/merged-image-generation-fallback/image-generation-fallback.md` (+ 2 supporting files in that folder).
