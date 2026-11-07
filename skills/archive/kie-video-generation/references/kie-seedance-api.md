# Kie.ai Seedance 2.0 API Reference

Extracted from docs.kie.ai — session May 2026.

## Base URL

```
POST https://api.kie.ai/api/v1/jobs/createTask
GET  https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=<taskId>
```

## Authentication

```
Authorization: Bearer <token>
```

## Models

| Model | ID | Speed | Quality |
|-------|-----|-------|---------|
| Seedance 2.0 | `bytedance/seedance-2` | Standard | High |
| Seedance 2.0 Fast | `bytedance/seedance-2-fast` | Fast | High |
| Seedance 1.5 Pro | `bytedance/seedance-1-5-pro` | Standard | Medium |

## Request Body

```json
{
  "model": "bytedance/seedance-2",
  "callBackUrl": "https://your-domain.com/webhook/kie",
  "input": {
    "prompt": "A serene beach at sunset...",
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

## Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | ✅ | Model ID |
| `callBackUrl` | string | ❌ | Webhook for completion notifications |
| `input.prompt` | string | ✅ | Text description |
| `input.first_frame_url` | string | ❌ | First frame (image-to-video) |
| `input.last_frame_url` | string | ❌ | Last frame |
| `input.reference_image_urls` | string[] | ❌ | Reference images |
| `input.reference_video_urls` | string[] | ❌ | Reference videos |
| `input.reference_audio_urls` | string[] | ❌ | Reference audio |
| `input.return_last_frame` | boolean | ❌ | Return last frame image |
| `input.generate_audio` | boolean | ❌ | Generate audio |
| `input.resolution` | string | ❌ | `720p`, `1080p` |
| `input.aspect_ratio` | string | ❌ | `16:9`, `9:16`, `1:1`, `3:4`, `4:3` |
| `input.duration` | integer | ❌ | Seconds (5-15 typical) |
| `input.web_search` | boolean | ❌ | Web search augmentation |

## Mutual Exclusivity Rules

- **Image-to-Video (First Frame)**, **Image-to-Video (First & Last Frames)**, and **Multimodal Reference-to-Video** are **mutually exclusive**.
- For strict first/last frame matching, use `first_frame_url` + `last_frame_url`.

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

## Polling

```bash
curl "https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=$TASK_ID" \
  -H "Authorization: Bearer <token>"
```

## Pricing Context

- Seedance 2.0 via Kie.ai is significantly cheaper than equivalent quality via Fal.ai.
- Fal.ai credits exhausted as of April 2026 — Kie.ai is the cost-effective replacement.
