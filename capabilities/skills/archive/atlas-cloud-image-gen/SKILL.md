---
name: atlas-cloud-image-gen
description: Atlas Cloud (`api.atlascloud.ai`) image generation via custom async API — models include baidu/ERNIE-Image-Turbo, openai/gpt-image-2. Submit+poll pattern, not OpenAI-compatible endpoints.
category: mlops
---

# Atlas Cloud Image Generation

## Overview

Atlas Cloud (`api.atlascloud.ai`) is a One-API / New-API style proxy that routes to multiple upstream model providers (Baidu ERNIE, OpenAI GPT Image, etc.). It uses a **custom async API** for image generation — the standard `/v1/images/generations` and `/v1/chat/completions` endpoints **do not work** for image models.

## Auth

```
Authorization: Bearer <ATLAS_API_KEY>
```

Key stored in vault: `atlas/api_key`

## Endpoints

| Action | Endpoint | Method |
|--------|----------|--------|
| Submit job | `/api/v1/model/generateImage` | POST |
| Poll result | `/api/v1/model/prediction/{prediction_id}` | GET |

**⚠️ CRITICAL: Standard OpenAI-compatible endpoints return errors for image models:**
- `/v1/images/generations` → `{"code": 400, "msg": "not found"}`
- `/v1/chat/completions` with image models → `{"code": 400, "msg": "not found"}`

## Submit Payload

```json
{
  "model": "baidu/ERNIE-Image-Turbo/text-to-image",
  "prompt": "A beautiful sunset over the ocean at golden hour, photorealistic",
  "size": "1440x2560",
  "n": 1,
  "quality": "low",
  "seed": -1,
  "use_pe": true,
  "num_inference_steps": 8,
  "guidance_scale": 1,
  "enable_sync_mode": false,
  "enable_base64_output": false
}
```

### Required fields
- `model` — **Must include the `/text-to-image` suffix** for both ERNIE and GPT Image models
- `prompt` — The text description

### Common fields
- `size` — WidthxHeight (e.g., `1440x2560`, `1024x1024`)
- `n` — Number of images (1-10)
- `quality` — `"low"` or `"high"` (for GPT Image 2)
- `enable_sync_mode` — If `true`, waits for completion (not recommended; default `false`)
- `enable_base64_output` — If `true`, returns base64 instead of URL

## Submit Response

```json
{
  "code": 200,
  "message": "",
  "data": {
    "id": "0555f2295cb9429b8112251e7aef7b50",
    "model": "baidu/ERNIE-Image-Turbo/text-to-image",
    "outputs": null,
    "status": "processing",
    "error": "",
    "prediction_id": "..."
  }
}
```

Extract `data.id` as the `prediction_id` for polling.

## Poll Response

### Completed
```json
{
  "code": 200,
  "data": {
    "id": "0555f2295cb9429b8112251e7aef7b50",
    "status": "completed",
    "outputs": ["https://atlas-media.oss-us-west-1.aliyuncs.com/images/xxx.png"]
  }
}
```

### Failed
```json
{
  "code": 200,
  "data": {
    "status": "failed",
    "error": "upstream returned success but no output image"
  }
}
```

### Still Processing
```json
{
  "code": 200,
  "data": {
    "status": "processing"
  }
}
```

**⚠️ CRITICAL: Failed jobs still return `"code": 200`!** Always check `data.status`, never just the top-level `"code"` field.

## GPT Image 2 Upscale/Refine Fallback

When Atlas Cloud GPT Image 2 is unavailable, use OpenAI direct API:
- Endpoint: `POST https://api.openai.com/v1/images/edits` (multipart form)
- Model: `gpt-image-2`, quality: `medium` or `high`
- Auth: `vault get openai/api_key`
- Full reference: `references/openai-image-edit-fallback.md`

## Image Editing / Upscaling

**⚠️ GPT Image 2 is NO LONGER available on Atlas Cloud** (as of May 2026). The `/api/v1/model/generateImage` endpoint returns `400 "not found"` for `openai/gpt-image-2/*`. Only Gemini image models remain on Atlas Cloud.

### Recommended: OpenAI Direct API (image-to-image editing)

Use the OpenAI `/v1/images/edits` endpoint directly with `gpt-image-2`. This is the best path for image quality enhancement, upscaling, and style-preserving edits.

**Auth**: OpenAI API key from vault: `openai/api_key`

**Endpoint**: `POST https://api.openai.com/v1/images/edits` (multipart form)

**Fields**:
- `model` — `gpt-image-2`
- `prompt` — describes desired output (e.g. "Improve quality preserving all original details")
- `image` — the source image file (multipart upload)
- `size` — `1024x1024`, `1536x1536`, `1792x1024`, `1024x1792`, `auto`
- `n` — number of variants (1-10)
- `quality` — `low`, `medium`, `high`, `auto`

**Response**: JSON with `data[0].b64_json` (base64 image) or `data[0].url`.

**Python example**:
```python
import requests, base64

resp = requests.post(
    "https://api.openai.com/v1/images/edits",
    headers={"Authorization": f"Bearer {OPENAI_KEY}"},
    files={"image": ("input.jpg", open("input.jpg", "rb"), "image/jpeg")},
    data={"model": "gpt-image-2", "prompt": "Improve quality", "size": "1024x1024", "n": "1", "quality": "medium"},
    timeout=120
)
result = resp.json()
img_bytes = base64.b64decode(result['data'][0]['b64_json'])
```

**Latency**: ~15-20s per image. For batch processing (8+ images), expect 2-4 minutes per batch.

### Legacy: Atlas Cloud image-to-image (DEPRECATED)

The Atlas Cloud `image-to-image` suffix model no longer works. If it's restored in the future, the payload format was:
```json
{
  "model": "openai/gpt-image-2/image-to-image",
  "prompt": "...",
  "image": ["data:image/jpeg;base64,..."],
  "size": "1024x1024",
  "n": 1,
  "quality": "low",
  "enable_sync_mode": false,
  "enable_base64_output": true
}
```

## Available Models

⚠️ **GPT Image 2 is no longer available on Atlas Cloud (as of May 2026).** The `/v1/models` endpoint no longer lists it, and `/api/v1/model/generateImage` returns `{"code":400,"msg":"not found"}`. Available image models are now Gemini-based (`google/gemini-2.5-flash-image`, `google/gemini-3-pro-image-preview`).

**Fallback for image-to-image / upscale tasks:** Use the OpenAI API directly via `/v1/images/edits` with `gpt-image-2`. Requires an OpenAI API key (check vault: `openai/api_key`). See `references/openai-image-edit-fallback.md`.

| Model ID | Provider | Status | Avg time | Notes |
|----------|----------|--------|----------|-------|
| `baidu/ERNIE-Image-Turbo/text-to-image` | Baidu | ✅ Active | ~9.5s/image | ~90% reliability, 1 in 10 may fail silently |
| `openai/gpt-image-2/text-to-image` | OpenAI | ❌ **Removed** | — | No longer available on Atlas Cloud (May 2026). Use OpenAI direct API instead. |
| `openai/gpt-image-2/image-to-image` | OpenAI | ❌ **Removed** | — | Use OpenAI direct `/v1/images/edits` endpoint |
| `google/gemini-2.5-flash-image` | Google | unknown | unknown | ⚠️ Untested on generateImage |

**Model name convention**: Always append `/text-to-image`. Without it → 404.

## GPT Image 2: Size Constraint (CRITICAL)

GPT Image 2 **requires BOTH width and height to be multiples of 16**. If you get `"invalid params, size must be multiples of 16"`, your size is wrong.

- ✅ `1024x1792` — best for vertical 9:16 TikTok/Instagram (1024/16=64, 1792/16=112)
- ✅ `1024x1024` · `1792x1024` · `2048x2048`
- ❌ `1080x1920` — 1080/16=67.5, NOT a multiple → error
- ERNIE accepts `1440x2560` for 9:16 (no multiple-of-16 constraint)

## GPT Image 2: Always Use enable_base64_output

**ALWAYS use `enable_base64_output: true` for GPT Image 2.** URL-based output expires quickly — you'll get `NoSuchKey` XML errors from the Aliyun OSS bucket if you don't download within seconds. Base64 returns the image data directly in the poll response, avoiding expiration entirely. Save directly from the `data:image/png;base64,...` string.

## Balance Exhaustion → ERNIE Fallback

Atlas Cloud balance can be exhausted mid-session (HTTP 402 "insufficient balance"), especially with GPT Image 2 (~$0.04-0.06/image behavior). When this happens:
- Already-submitted jobs may still complete
- New submissions return code 402 immediately
- **Fall back to `baidu/ERNIE-Image-Turbo/text-to-image`** for remaining images — it's ~10x cheaper and often still has credits when GPT Image 2 is exhausted
- ERNIE output is URL-based, so download immediately after polling

## Social Media Storyboard Workflow

For TikTok/UGC ad storyboards — generate 2 keyframes per scene (before/after states), vertical.

### Pattern
1. Write all prompts (2 per scene) with consistent character reference ("Same man with mustache, wearing [X] in same [decor]")
2. Submit all frames in parallel via async submit+poll
3. Use `quality: "low"` for storyboards/drafts; `"high"` for final assets
4. Download via base64 (GPT Image 2) or immediate URL fetch (ERNIE)

### Prompt Template for UGC/Storyboard
```
"Vertical 9:16, photorealistic UGC style. [CHARACTER] in [DECOR], [ACTION]. [LIGHTING]. TikTok social media aesthetic."
```

Consistency tip: Reference the same character across frames with identical descriptors.

## Performance Summary

| Metric | ERNIE-Image-Turbo | GPT Image 2 (OpenAI direct) |
|--------|-------------------|---------------------------|
| Endpoint | Atlas Cloud `/api/v1/model/generateImage` | OpenAI `/v1/images/edits` |
| Per-image avg | ~9.5s | ~15-20s |
| Batch 10 images | ~95s | ~150-200s |
| Reliability | ~90% (silent failures) | ~100% |
| Auth | Atlas API key | OpenAI API key (vault) |

## Python Async Polling Pattern

```python
import requests
import time

BASE = "https://api.atlascloud.ai"
HEADERS = {"Authorization": "Bearer <KEY>", "Content-Type": "application/json"}

def generate_async(prompt, model, size="1024x1024", n=1, **kwargs):
    resp = requests.post(f"{BASE}/api/v1/model/generateImage",
        headers=HEADERS,
        json={"model": model, "prompt": prompt, "size": size, "n": n,
              "enable_sync_mode": False, "enable_base64_output": False, **kwargs},
        timeout=30)
    data = resp.json()
    if data.get("code") != 200:
        raise Exception(f"Submit failed: {data}")
    pred_id = data["data"]["id"]

    for _ in range(80):  # ~4 min max
        resp = requests.get(f"{BASE}/api/v1/model/prediction/{pred_id}",
            headers={"Authorization": "Bearer <KEY>"}, timeout=10)
        r = resp.json()
        status = r["data"]["status"]
        if status == "completed":
            return r["data"]["outputs"]
        elif status == "failed":
            raise Exception(r["data"].get("error", "unknown"))
        time.sleep(3)
    raise Exception("Timed out")
```

## Common Pitfalls

1. **Wrong endpoints**: `/v1/images/generations` and `/v1/chat/completions` return 400 for image models. Always use `/api/v1/model/generateImage`.

2. **Missing `/text-to-image` suffix**: Model names must include it. `openai/gpt-image-2` → 404.

3. **GPT Image 2 removed from Atlas Cloud**: As of May 2026, `openai/gpt-image-2/*` returns `400 "not found"`. Use OpenAI direct API for image editing/quality enhancement tasks.

4. **Silent ERNIE failures**: ERNIE occasionally fails with `"upstream returned success but no output image"` — code 200, status "failed".

5. **Failed jobs return code 200**: Always check `data.status`, never just `"code"`.

6. **Submission latency**: Submission is fast (~400ms) but first image takes 40-50s regardless of model.

7. **URL bucket difference**: ERNIE → `atlas-media.oss`, GPT → `atlas-img.oss`.

8. **ERNIE vs OpenAI Direct**: Use OpenAI direct for product images, ERNIE for generic placeholders. When user requests product-adapted images, use OpenAI `/v1/images/edits` with `gpt-image-2`.

## Language Matching

ALWAYS generate page content in the user's language. If the user writes in French, the page must be in French. Double-check by grepping for unwanted characters before deployment.

## References

- `references/atlas-cloud-api-details.md` — endpoint details, model list, benchmarks
- `references/landing-page-adaptation.md` — workflow for cloning landing pages
- `references/gpt-image-2-sizing.md` — GPT Image 2 size constraints and best practices
- `scripts/generate_atlas_images.py` — reusable async generator with parallel polling
