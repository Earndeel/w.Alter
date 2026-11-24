# Kie.ai Seedance 2.0 API Reference

Extracted from https://docs.kie.ai/market/bytedance/seedance-2 and seedance-2-fast.

## Endpoint

```
POST https://api.kie.ai/api/v1/jobs/createTask
Authorization: Bearer <token>
Content-Type: application/json
```

## Models

| Model ID | Quality | Speed | Best For |
|----------|---------|-------|----------|
| `bytedance/seedance-2` | High | Standard | Quality-first productions |
| `bytedance/seedance-2-fast` | High | Fast | Daily production, iterations |

## Request Body

```json
{
  "model": "bytedance/seedance-2",
  "callBackUrl": "https://api.walter-ai.cloud/webhook/kie",
  "input": {
    "prompt": "Cinematic product reveal...",
    "first_frame_url": "https://...png",
    "last_frame_url": "https://...png",
    "reference_image_urls": ["https://...png"],
    "reference_video_urls": ["https://...mp4"],
    "reference_audio_urls": ["https://...mp3"],
    "return_last_frame": false,
    "generate_audio": false,
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 15,
    "web_search": false
  }
}
```

## Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | ✅ | `bytedance/seedance-2` or `bytedance/seedance-2-fast` |
| `callBackUrl` | string | ❌ | Webhook for completion (use in production) |
| `input.prompt` | string | ✅ | Scene description in English |
| `input.first_frame_url` | string | ❌ | First frame image (Image-to-Video) |
| `input.last_frame_url` | string | ❌ | Last frame image |
| `input.reference_image_urls` | string[] | ❌ | Style/character reference images |
| `input.reference_video_urls` | string[] | ❌ | Motion/style reference videos |
| `input.reference_audio_urls` | string[] | ❌ | Audio reference for lip-sync |
| `input.return_last_frame` | boolean | ❌ | Return last frame (default: false) |
| `input.generate_audio` | boolean | ❌ | Generate audio (default: false) |
| `input.resolution` | string | ❌ | `720p`, `1080p` (model-dependent) |
| `input.aspect_ratio` | string | ❌ | `16:9`, `9:16`, `1:1`, `3:4`, `4:3` |
| `input.duration` | integer | ❌ | Duration in seconds (5-15 typical) |
| `input.web_search` | boolean | ❌ | Enable web search augmentation |

## ⚠️ Mutual Exclusivity Rules

- **Image-to-Video (First Frame)**, **Image-to-Video (First & Last Frames)**, and **Multimodal Reference-to-Video** are **mutually exclusive**.
- Cannot use `first_frame_url` + `reference_image_urls` simultaneously.
- For "First/Last Frame + Multimodal Reference" effect, use reference images via prompts in multimodal mode.
- If you need strict first/last frame matching, use `first_frame_url` + `last_frame_url` only.

## Response

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "taskId": "task_bytedance_1765186743319"
  }
}
```

## Query Status

```
GET https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=<taskId>
Authorization: Bearer <token>
```

## Pricing Context

- Seedance 2.0 via Kie.ai is **significantly cheaper** than equivalent quality via Fal.ai.
- Exact pricing is dynamic per credit — check https://kie.ai/market.
- Fal.ai credits exhausted as of April 2026 → Kie.ai is the primary cost-effective replacement.

## Other Video Models on Kie.ai

| Provider | Model IDs |
|----------|-----------|
| Kling | `kling/kling-3-0`, `kling/text-to-video`, `kling/image-to-video` |
| Hailuo | `hailuo/2-3-image-to-video-pro`, `hailuo/02-text-to-video-pro` |
| Wan | `wan/2-7-text-to-video`, `wan/2-7-image-to-video` |
| Sora2 | `sora2/sora-2-text-to-video`, `sora2/sora-2-image-to-video` |
| Grok | `grok-imagine/text-to-video`, `grok-imagine/image-to-video` |
