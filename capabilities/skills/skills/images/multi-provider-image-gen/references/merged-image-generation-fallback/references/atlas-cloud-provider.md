# Atlas Cloud (AtlasCloud.ai) — Provider Reference

## Overview
Atlas Cloud is a Chinese proxy API (One-API/New-API backend) providing access to multiple LLM providers including Baidu ERNIE, OpenAI, Google Gemini, and more. It is now a **primary image generation provider** for this setup.

## Base URLs
- **Text/Chat (OpenAI-compat)**: `https://api.atlascloud.ai/v1`
- **Image Generation (Atlas native)**: `https://api.atlascloud.ai/api/v1`

## Auth
- `Authorization: Bearer apikey-<hex>` (standard Bearer)
- Key format: `{{bw:W.Alter · atlas:field:api_key}}`
- Stored in vault: `atlas/api_key`

## 🔑 IMAGE GENERATION — ERNIE-Image-Turbo (VERIFIED WORKING)

### Submit Generation
```
POST https://api.atlascloud.ai/api/v1/model/generateImage
```

**Payload:**
```json
{
  "model": "baidu/ERNIE-Image-Turbo/text-to-image",
  "prompt": "Your image description here",
  "size": "1440x2560",
  "n": 1,
  "seed": -1,
  "use_pe": true,
  "num_inference_steps": 8,
  "guidance_scale": 1,
  "enable_sync_mode": false,
  "enable_base64_output": false
}
```

**Required fields:** `model`, `prompt`
**Optional:** `size` (default 1024x1024), `n` (1-10), `seed`, `use_pe` (default true), `num_inference_steps` (1-100, default 8), `guidance_scale` (1-20, default 1)

**Response:**
```json
{
  "code": 200,
  "data": {
    "id": "prediction-uuid",
    "model": "baidu/ERNIE-Image-Turbo/text-to-image",
    "status": "processing",
    "urls": {"get": "https://api.atlascloud.ai/api/v1/model/prediction/{id}"}
  }
}
```

### Poll for Result
```
GET https://api.atlascloud.ai/api/v1/model/prediction/{id}
Authorization: Bearer {ATLAS_KEY}
```

**Poll every 2-3s.** Statuses: `processing` → `completed` or `failed`

**Completed response:**
```json
{
  "code": 200,
  "data": {
    "status": "completed",
    "outputs": ["https://atlas-media.oss-us-west-1.aliyuncs.com/images/{uuid}.png"]
  }
}
```

**Failed response:**
```json
{
  "code": 200,
  "data": {
    "status": "failed",
    "error": "error description"
  }
}
```

### Performance Benchmarks (verified 2026-05-12)
- Single image (1024x1024): ~36s
- Batch 10 images (1440x2560): ~95s total (parallel submit, ~9.5s avg)
- Success rate: 9/10 (1 failed with "upstream returned success but no output image")
- Image size: ~5-7 MB each (PNG)
- Images stored on Aliyun OSS with ~1 hour+ availability
- Sizes tested: `1024x1024`, `1440x2560` (portrait) — both work

### Python Workflow (Batch)
```python
import requests, time

BASE = "https://api.atlascloud.ai"
KEY = "apikey-xxx"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

def submit(prompt, size="1440x2560"):
    resp = requests.post(f"{BASE}/api/v1/model/generateImage",
        headers=HEADERS, json={
            "model": "baidu/ERNIE-Image-Turbo/text-to-image",
            "prompt": prompt, "size": size, "n": 1,
            "enable_sync_mode": False})
    return resp.json()["data"]["id"]

def poll(prediction_id, timeout=120):
    for _ in range(timeout // 2):
        r = requests.get(f"{BASE}/api/v1/model/prediction/{prediction_id}",
            headers={"Authorization": f"Bearer {KEY}"})
        d = r.json()["data"]
        if d["status"] == "completed": return d["outputs"][0]
        if d["status"] == "failed": raise Exception(d.get("error"))
        time.sleep(2)
    raise Exception("Timeout")
```

## TEXT/CHAT MODELS (OpenAI-compatible endpoint)

- **Endpoint**: `POST /v1/chat/completions`
- **GET /v1/models**: Returns ~105 models
- Working models: `deepseek-ai/DeepSeek-V3-0324`, `qwen/qwen3-32b`, `google/gemini-2.5-flash`, etc.

## Image Models in Model List (NOT via OpenAI endpoint)
These appear in `/v1/models` but **do NOT work for image generation via the OpenAI-compatible endpoints** (`/v1/images/generations` or `/v1/chat/completions`). They likely require the Atlas native image endpoint above:
- `google/gemini-2.5-flash-image`
- `google/gemini-3-pro-image-preview`
- `google/gemini-3.1-flash-image-preview`

## Common Pitfalls

1. **WRONG endpoint for images**: `/v1/images/generations` and `/v1/chat/completions` return 400 bad request or 404 for image models. Always use `/api/v1/model/generateImage`.

2. **Async by default**: `enable_sync_mode: false` is default. You MUST poll the prediction endpoint for results. Setting `enable_sync_mode: true` blocks until complete.

3. **No ERNIE models in text endpoint**: `baidu/ERNIE-Image-Turbo` doesn't appear in `/v1/models` list but works fine via the image endpoint.

4. **Failed jobs**: ~10% failure rate ("upstream returned success but no output image") — implement retry logic.

5. **OSS URL expiration**: Images are stored on Aliyun OSS. URLs appear persistent but verify availability before using in production.

## Verdict
Atlas Cloud is now the **primary image generation provider** for this setup. ERNIE-Image-Turbo produces high-quality UGC-style images reliably. Use it first for image generation tasks, with Fal.ai and Pollinations.ai as fallbacks.
