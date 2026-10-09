---
name: piapi-video-integration
description: Integrate PiAPI.ai as a video generation provider — unified API for all models (Kling, Seedance, Veo3, Wan, Hailuo, Sora, Hunyuan, Luma). Single submit+poll pattern.
category: mlops
---

# PiAPI Video Generation Integration

## Quick Reference

PiAPI uses a **unified API** — 2 endpoints for ALL models:

```
POST https://api.piapi.ai/api/v1/task          → create job
GET  https://api.piapi.ai/api/v1/task/{task_id} → poll status + result
```

Auth: `X-API-Key: <key>` header.

## PITFALL: Cloudflare blocks urllib without User-Agent

PiAPI is behind Cloudflare. `urllib.request` gets `403 (error code: 1010)` unless you set a User-Agent header. Always include it:

```python
headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json",
    "User-Agent": "WAlter-Pipeline/1.0",  # REQUIRED — Cloudflare blocks without it
}
```

`curl` works fine without it (curl sends its own UA), but Python's urllib does NOT.

## Request Format (all models)

```json
{
  "model": "kling",
  "task_type": "video_generation",
  "input": {
    "prompt": "scene description",
    "duration": 5,
    "aspect_ratio": "9:16"
  }
}
```

The `model` and `task_type` fields change per model variant. The `input` fields change per model. See schemas below.

## Status Values

PiAPI returns: `Completed` / `Processing` / `Pending` / `Failed` / `Staged`

Map to internal: completed / in_progress / in_queue / failed / submitted

## Key Models on PiAPI (as of April 2026)

| PiAPI model | task_type | Version | Pricing | Notes |
|---|---|---|---|---|
| `kling` | `video_generation` | 3.0 | $0.10/s (std 720p), $0.15/s (pro 1080p) | Best quality/price |
| `kling` | `video_generation` | 2.6 | $0.08/s (std), $0.13/s (pro) | Cheaper |
| `kling` | `omni_video_generation` | 3.0 | Same as above | Multi-ref (images+video+audio) |
| `kling-turbo` | `video_generation` | turbo | $0.28/5s fixed | Fastest |
| `seedance-2-fast` | `video_generation` | 2.0 | $0.10/s | Top benchmark, 4-15s, multi-ref |
| `seedance-2` | `video_generation` | 2.0 | $0.13/s | Higher quality Seedance |
| `veo3` | `veo3-video` | 3.0 | $0.06-0.24/s | Google quality, native audio |
| `veo3` | `veo3-video-fast` | 3.1 | $0.06/s | Budget Google |
| `sora2` | — | 2.0 | ~$0.50/s | OpenAI |

## Kling 3.0 Input Params

```json
{
  "prompt": "string (max 2500)",
  "version": "3.0",
  "mode": "std | pro",
  "duration": "3-15",
  "aspect_ratio": "16:9 | 9:16 | 1:1",
  "enable_audio": false,
  "image_url": "url or null for T2V",
  "prefer_multi_shots": false
}
```

## Seedance 2.0 Input Params

```json
{
  "prompt": "string (max 4000)",
  "duration": "4-15",
  "aspect_ratio": "21:9 | 16:9 | 4:3 | 1:1 | 3:4 | 9:16 | auto",
  "mode": "text_to_video | first_last_frames | omni_reference",
  "image_urls": ["url1"],
  "video_urls": ["url1"],
  "audio_urls": ["url1"]
}
```

Modes:
- `text_to_video` — pure text
- `first_last_frames` — 1-2 images as first/last frame
- `omni_reference` — mixed refs (images+video+audio, 1-12 total)

## Python Submit + Poll Pattern

```python
import urllib.request, json, time, threading

PIAPI_BASE = "https://api.piapi.ai/api/v1/task"

def _piapi_request(path="", method="GET", data=None, api_key=""):
    url = PIAPI_BASE + (f"/{path}" if path else "")
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "MyApp/1.0",  # REQUIRED
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

def submit(model, task_type, input_params, api_key):
    result = _piapi_request(method="POST", data={
        "model": model,
        "task_type": task_type,
        "input": input_params,
    }, api_key=api_key)
    return result["data"]["task_id"]

def poll(task_id, api_key, interval=30, max_attempts=120):
    for _ in range(max_attempts):
        time.sleep(interval)
        result = _piapi_request(path=task_id, method="GET", api_key=api_key)
        status = result["data"]["status"].lower()
        if status == "completed":
            return result["data"]["output"]
        if status == "failed":
            raise Exception(f"Task failed: {result['data'].get('error')}")
    raise TimeoutError("Polling timed out")

def auto_poll(task_id, api_key, callback, interval=30):
    """Background polling with callback on completion."""
    def _loop():
        try:
            output = poll(task_id, api_key, interval=interval)
            callback({"status": "completed", "output": output})
        except Exception as e:
            callback({"status": "failed", "error": str(e)})
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
```

## Response Structure (GET task)

```json
{
  "code": 200,
  "data": {
    "task_id": "uuid",
    "model": "kling",
    "task_type": "video_generation",
    "status": "Completed",
    "input": { ... },
    "output": {
      "video_url": "https://storage.theapi.app/videos/xxx.mp4",
      "works": [{ "video": { "resource": "...", "resource_without_watermark": "..." } }]
    },
    "meta": {
      "created_at": "...",
      "ended_at": "...",
      "usage": { "frozen": 2600000, "consume": 2600000 }
    }
  }
}
```

## Pitfalls

- **User-Agent header required** — Cloudflare 403 without it
- **Pricing is per-second** for most models (not per-video)
- **Input video duration counts toward cost** for Seedance with refs
- **`version` field required** for Kling — defaults may not work
- **Seedance `mode` field required** — determines which params are valid
- **Auto-poll recommended** — no webhook needed, just poll every 30s
- **Frozen vs consume** in meta.usage — frozen is reserved at submit, consume is actual cost after completion
