# Grok Imagine Image-to-Video via Kie.ai

## API Endpoint

```
POST https://api.kie.ai/api/v1/jobs/createTask
```

## Payload

```json
{
    "model": "grok-imagine/image-to-video",
    "callBackUrl": "https://your-domain.com/api/callback",
    "input": {
        "image_urls": [
            "https://example.com/input-image.png"
        ],
        "prompt": "Camera slowly pans across the scene, subtle ambient motion",
        "mode": "normal",
        "duration": "6",
        "resolution": "480p",
        "aspect_ratio": "16:9"
    }
}
```

### Input Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image_urls` | string[] | ✅ | Array of 1 input image URL |
| `prompt` | string | ✅ | Motion/animation description |
| `mode` | string | ❌ | `"normal"` (default) |
| `duration` | string | ❌ | Duration in seconds, `"5"`, `"6"`, `"8"`, `"10"` etc. |
| `resolution` | string | ❌ | `"480p"`, `"720p"`, `"1080p"` |
| `aspect_ratio` | string | ❌ | `"16:9"`, `"9:16"`, `"1:1"`, `"4:3"`, `"3:4"` |

## Polling

Unified endpoint:
```
GET https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=<taskId>
```

Try `getTaskDetail` first, fallback to `recordInfo`:
```
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>
```

Response:
```json
{
    "code": 200,
    "data": {
        "taskId": "...",
        "state": "success",
        "videoUrl": "https://kie-media...",
        "resultJson": "{\"video_urls\": [\"https://...\"]}"
    }
}
```

## Submit Response

```json
{
    "code": 200,
    "msg": "success",
    "data": {
        "taskId": "281e5b0...f39b9"
    }
}
```
