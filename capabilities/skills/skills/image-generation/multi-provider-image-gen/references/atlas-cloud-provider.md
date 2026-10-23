---
name: atlas-cloud-provider
description: Atlas Cloud (api.atlascloud.ai) — image generation, editing, and model API. Async task-based workflow with /api/v1/model/generateImage and /api/v1/model/prediction/{id}.
category: mlops
---

# Atlas Cloud Provider

## Base URL

- API: `https://api.atlascloud.ai`
- Standard OpenAI endpoints (`/v1/...`) do NOT support image generation.

## Authentication

```
Authorization: Bearer <API_KEY>
```

## Image Generation (Async Task API)

### Submit

```
POST https://api.atlascloud.ai/api/v1/model/generateImage
```

### Poll

```
GET https://api.atlascloud.ai/api/v1/model/prediction/{prediction_id}
```

### Supported Image Models

| Model | Use Case |
|-------|----------|
| `baidu/ERNIE-Image-Turbo/text-to-image` | Text-to-image |
| `openai/gpt-image-2/text-to-image` | High-quality text-to-image |
| `openai/gpt-image-2/edit` | Image editing |

### ⚠️ CRITICAL: Not OpenAI-Compatible for Images

Atlas Cloud's `/v1/images/generations` and `/v1/chat/completions` endpoints do NOT work for image generation. You MUST use `/api/v1/model/generateImage`.

### Submit Payload

```json
{
  "model": "baidu/ERNIE-Image-Turbo/text-to-image",
  "prompt": "A beautiful sunset over the ocean...",
  "size": "1024x1024",
  "n": 1,
  "enable_sync_mode": false,
  "enable_base64_output": false
}
```

For GPT Image 2:
```json
{
  "model": "openai/gpt-image-2/text-to-image",
  "prompt": "A beautiful sunset...",
  "size": "1440x2560",
  "n": 1,
  "quality": "low",
  "enable_sync_mode": false,
  "enable_base64_output": false
}
```

For image edit:
```json
{
  "model": "openai/gpt-image-2/edit",
  "prompt": "Change the woman's top to vibrant red, keep everything else the same",
  "image": "https://example.com/source.png",
  "size": "1536x1024",
  "quality": "low",
  "n": 1,
  "enable_sync_mode": false,
  "enable_base64_output": false
}
```

### Poll Response

```json
{
  "code": 200,
  "data": {
    "id": "...",
    "status": "completed",
    "outputs": ["https://atlas-img.oss-us-west-1.aliyuncs.com/images/xxx.png"]
  }
}
```

## Reference Files

- `references/api-notes.md` — API quirks, performance benchmarks, size/quality options
- `scripts/batch-image-gen.py` — Batch image generation with polling

## ⚡ Performance Reference

| Model | Size | Time per image | Throughput |
|-------|------|---------------|------------|
| ERNIE-Image-Turbo | 1440x2560 | ~9s avg | 0.11 img/s |
| GPT Image 2 | 1440x2560 | ~18s avg | 0.06 img/s |
| GPT Image 2 edit | 1536x1024 | ~60s | single |
