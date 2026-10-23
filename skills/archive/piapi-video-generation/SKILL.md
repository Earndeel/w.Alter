---
name: piapi-video-generation
description: Integrate PiAPI.ai as a unified video generation provider — single API for Kling, Seedance, Veo3, WanX, Hailuo, Sora2, Hunyuan, and more. Use this when switching from Fal.ai or adding video models.
category: mlops
---

# PiAPI Video Generation

## Unified API — 2 endpoints for ALL models

```
POST https://api.piapi.ai/api/v1/task      → create job
GET  https://api.piapi.ai/api/v1/task/{id}  → check status + result
```

Auth: `X-API-Key: <key>` header.

## Create Task schema (same structure for every model)

```json
{
  "model": "kling",
  "task_type": "video_generation",
  "input": {
    "prompt": "...",
    "duration": 5,
    "aspect_ratio": "16:9",
    "image_url": null
  }
}
```

## Response status values
- `Completed` — done, check `data.output`
- `Processing` — running (counts as concurrent)
- `Pending` — queued waiting for accounts
- `Failed` — error, check `data.error`
- `Staged` — exceeded concurrent limit

## Video Models & Pricing

### Kling — `model: "kling"`
- `task_type`: `video_generation`, `extend_video`, `lip_sync`, `effects`, `avatar`, `motion_control`, `virtual_try_on`, `sound`
- For **Kling o1 / 3.0 Omni**: use `task_type: "omni_video_generation"` (different endpoint)
- Input params (standard):
  - `prompt` (string, max 2500)
  - `negative_prompt` (string, max 2500)
  - `cfg_scale` (float 0-1, recommended 0.5)
  - `duration` (3-15 for v3.0, 5/10 for older)
  - `aspect_ratio` (16:9, 9:16, 1:1)
  - `image_url` (string URL or null — null=T2V, URL=I2V)
  - `version` (string — must be `"3.0"` for Kling 3.0)
  - `mode` (`"std"` = 720p, `"pro"` = 1080p)
  - `enable_audio` (bool — native audio generation)
  - `prefer_multi_shots` (bool)
  - `resolution` (`"720"`, `"1080"` — for omni)
- Versions: 2.5, 2.6, 3.0, 3.0-omni, o1, turbo
- Pricing (3.0): 720p=$0.10/s, 720p+audio=$0.15/s, 1080p=$0.15/s, 1080p+audio=$0.20/s
- Pricing (Turbo): $0.28/5s, $0.56/10s (fixed)
- Pricing (o1): 720p/5s=$0.39, 1080p/10s=$1.04
- Kling 3.0 Omni: same pricing as 3.0, supports multi-references via `@image_1`, `@video` in prompt

### Seedance — `model: "seedance-2"` or `"seedance-2-fast"`
- `task_type`: `video_generation`
- `mode` (required): `text_to_video`, `first_last_frames`, `omni_reference`
- Input params:
  - `prompt` (string, max 4000)
  - `duration` (int 4-15)
  - `aspect_ratio` (21:9, 16:9, 4:3, 1:1, 3:4, 9:16, auto)
  - `image_urls` (array of URLs, max 12)
  - `video_urls` (array of URLs, mp4/mov)
  - `audio_urls` (array of URLs, mp3/wav, max 15s)
- Pricing (updated April 2026): seedance-2=$0.13/s, seedance-2-fast=$0.10/s
  - With input videos: cost = unit_price × (total_input_video_duration + output_duration)
  - Max output: 15s, max total input video: 15.4s

### Veo3 — `model: "veo3"` or `"veo3-video-fast"`
- `task_type`: `veo3-video` or `veo3-video-fast`
- **Veo3.1**: separate endpoints (`veo31-api`), same pattern
- Input params:
  - `prompt` (string)
  - `duration` (int 4-8)
  - `aspect_ratio` (16:9, 9:16)
  - `generate_audio` (bool — native audio)
- Pricing: veo3+audio=$0.24/s, no audio=$0.12/s | fast=$0.09/s, fast no audio=$0.06/s

### Wan 2.6 — `model: "wan"` / WanX
- `task_type`: `video_generation`
- Open source, LoRA support, camera control
- Available on PiAPI

### Hailuo — via PiAPI
- Budget-friendly, good quality

### Sora 2 — via PiAPI
- `task_type`: `video_generation`
- Pro and standard variants

### Hunyuan — via PiAPI
- Open source, LoRA support

## Key differences vs Fal.ai

| | Fal.ai | PiAPI |
|---|---|---|
| Endpoints | 1 per model | 1 unified endpoint |
| Schema | Model-specific | Uniform: model+task_type+input |
| Auth | FAL_KEY env var | X-API-Key header |
| Status | custom per model | Completed/Processing/Pending/Failed/Staged |
| SDK | fal_client (Python) | Plain HTTP (no SDK) |

## Migrating from Fal.ai to PiAPI

### Model config change
Fal.ai config:
```json
{"name": "Kling v3", "endpoint": "fal-ai/kling-video/v3/pro/text-to-video"}
```
PiAPI config:
```json
{"name": "Kling v3", "provider": "piapi", "piapi_model": "kling", "task_type": "video_generation"}
```

### Submission code (Python, no SDK needed)
```python
import urllib.request, json

PIAPI_BASE = "https://api.piapi.ai/api/v1/task"

def submit(api_key, piapi_model, task_type, input_params):
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "WAlter-Pipeline/1.0",  # Required — Cloudflare blocks without it
    }
    body = json.dumps({
        "model": piapi_model,
        "task_type": task_type,
        "input": input_params,
    }).encode()
    req = urllib.request.Request(PIAPI_BASE, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())
    # → {"data": {"task_id": "uuid", "status": "Pending"}, ...}
```

### Status polling code
```python
def get_task(api_key, task_id):
    headers = {"X-API-Key": api_key}
    url = f"{PIAPI_BASE}/{task_id}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())
    # → {"data": {"status": "Completed", "output": {"video_url": "..."}, ...}}

STATUS_MAP = {
    "completed": "completed",
    "processing": "in_progress",
    "pending": "in_queue",
    "failed": "failed",
    "staged": "submitted",
}
```

### Status mapping (PiAPI → internal)

| PiAPI status | Internal (Fal-compatible) |
|---|---|
| Completed | completed |
| Processing | in_progress |
| Pending | in_queue |
| Failed | failed |
| Staged | submitted |

### Pitfalls when migrating
- Remove `fal_client` dependency — PiAPI is plain HTTP (urllib/requests)
- LLM prompt must output the `input` dict only (not wrapped in `endpoint` + `arguments` like Fal)
- PiAPI responses nest results under `data.output` not top-level
- Video URLs expire — download/cache immediately after completion
- `image_url` must be explicit `null` for T2V (not empty string — causes errors)
- `mode` field is REQUIRED for Seedance (text_to_video / first_last_frames / omni_reference)
- **Cloudflare blocks urllib**: PiAPI sits behind Cloudflare. Python's `urllib` requests are blocked (HTTP 403, error code 1010) unless you add a `User-Agent` header. Always include `"User-Agent": "WAlter-Pipeline/1.0"` (or any non-empty value) in your request headers.
- **Auto-polling**: After submit, start a background thread polling every 30s to check completion. Don't rely on manual user action to sync. Pattern:
  ```python
  import threading, time
  _active_polls = {}
  
  def start_auto_polling(card_id, sync_fn):
      if card_id in _active_polls and _active_polls[card_id].is_alive():
          return
      t = threading.Thread(target=lambda: _poll_loop(card_id, sync_fn), daemon=True)
      t.start()
      _active_polls[card_id] = t
  
  def _poll_loop(card_id, sync_fn):
      for attempt in range(120):
          time.sleep(30)
          result = sync_fn(card_id)
          if result.get("status") in ("completed", "failed"):
              break
  ```

## Image Generation via PiAPI (Uncertain)

PiAPI primarily focuses on video generation. Image generation support exists but is less documented than video.

**Known pitfalls:**
- Do NOT use `model: "gemini"` — this is not a valid PiAPI model
- If Fal.ai is unavailable for images, verify PiAPI image model names via their docs before using as fallback
- PiAPI image generation models and task_types are not as standardized as video models

For reliable image generation, prefer Fal.ai (NanoBanana 2, Flux) as primary provider.

## Docs
- Overview: https://piapi.ai/docs/overview
- Unified schema: https://piapi.ai/docs/unified-api-schema
- Webhooks: https://piapi.ai/docs/unified-webhook
- Kling: https://piapi.ai/docs/kling-api/create-task
- Seedance: https://piapi.ai/docs/seedance-api/seedance-2
- Veo3: https://piapi.ai/docs/veo3-api/text-to-video
- Full list: https://piapi.ai/docs/llms.txt

## Model Rankings (Artificial Analysis, April 2026)

Full leaderboard cross-referenced with PiAPI availability (ELO-based, human votes):

| Rank | ELO | Model | PiAPI? | $/min | Use case |
|------|-----|-------|--------|-------|----------|
| 1 | 1388 | HappyHorse-1.0 | ❌ | Coming soon | — |
| 2 | ~1274 | Seedance 2.0 720p | ✅ | ~$6-8 | Top quality, multi-ref |
| 3 | 1244 | SkyReels V4 | ❌ | $7.20 | — |
| 4 | 1243 | Kling 3.0 Pro 1080p | ✅ | $13.44 | Premium |
| 5 | 1230 | Kling 3.0 Omni Pro | ✅ | $13.44 | Multi-reference |
| 6 | 1230 | grok-imagine-video | ❌ | $4.20 | — |
| 7 | 1224 | PixVerse V5.6 | ❌ | $9.00 | — |
| 8 | 1224 | Runway Gen-4.5 | ❌ | N/A | — |
| 9 | 1223 | Vidu Q3 Pro | ❌ | $9.60 | — |
| 10 | 1219 | Veo 3 | ✅ | $12.00 | Native audio |
| 11 | 1218 | Kling 3.0 Omni Std | ✅ | $10.08 | Multi-ref value |
| 12 | 1216 | Kling 3.0 Std 720p | ✅ | $10.08 | Best value |
| 13 | 1213 | Kling 2.5 Turbo | ✅ | $4.20 | Fast tests |
| 14 | 1212 | Veo 3.1 | ✅ | $12.00 | Google quality |
| 15 | 1211 | Veo 3.1 Fast | ✅ | $6.00 | Budget |
| 16 | 1209 | PixVerse V6 | ❌ | $5.40 | — |
| 17 | 1204 | Luma Ray 3 | ✅ | $13.20 | Luma quality |
| 20 | 1195 | Sora 2 Pro | ✅ | $30.00 | OpenAI quality |
| 23 | 1186 | Wan 2.6 | ✅ | $9.00 | Open source |
| 25 | 1183 | Hailuo 2.3 | ✅ | $2.80 | Budget |
| 58 | 1014 | Hunyuan Video | ✅ | $4.50 | Open source |

**Recommended stack for ads pipeline:**
- Default: **Seedance 2.0 fast** ($0.10/s) — #2 benchmark, 4-15s, multi-ref
- Premium: **Kling 3.0 Pro** ($0.15/s) — #4, 1080p, audio natif
- Budget: **Veo 3.1 Fast** ($0.06/s) — #15, half price
- Test: **Kling Turbo** ($0.28/5s) — fast turnaround

## Auto-Polling (don't make users click Sync)

After submit, start a background thread that polls every 30s until completed/failed. Both server-side (Python thread) and client-side (JS setInterval):

```python
import threading, time

_active_polls = {}
POLL_INTERVAL = 30

def start_auto_polling(card_id):
    if card_id in _active_polls and _active_polls[card_id].is_alive():
        return
    t = threading.Thread(target=_poll_loop, args=(card_id,), daemon=True)
    t.start()
    _active_polls[card_id] = t

def _poll_loop(card_id):
    for attempt in range(120):  # Max 1 hour
        time.sleep(POLL_INTERVAL)
        result = sync(card_id)  # your sync function
        if result.get("status") in ("completed", "failed"):
            break
```

Frontend auto-poll:
```javascript
function startAutoPoll(cardId) {
    var timer = setInterval(async function() {
        const res = await fetch('/api/sync/' + cardId, {method: 'POST'});
        const data = await res.json();
        if (data.status === 'completed' || data.status === 'failed') {
            clearInterval(timer);
            toast('Card #' + cardId + ': ' + data.status);
            loadData();
        }
    }, 30000);
}
```

## Webhook Callback (Async — No Polling Needed)

Instead of polling, PiAPI can call YOUR server when the job is done. Include `config.webhook_config` in the create request:

```json
{
  "model": "seedance-2-fast",
  "task_type": "video_generation",
  "input": { "prompt": "...", "duration": 5 },
  "config": {
    "webhook_config": {
      "endpoint": "https://api.hermes-workspace.com/webhook/piapi"
    }
  }
}
```

When done, PiAPI POSTs to your webhook:
```json
{
  "data": {
    "task_id": "uuid",
    "status": "Completed",
    "output": {
      "video_url": "https://...",
      "works": [{ "video": { "resource_without_watermark": "https://..." } }]
    }
  }
}
```

Status values in webhook: `Completed`, `Failed` (not lowercase).

This pattern replaces Cloudflare Queues entirely for free-tier async:
1. Submit job with webhook_config → respond to user immediately
2. PiAPI processes (1-3 min)
3. PiAPI hits your webhook → send result to user

No polling, no queues, no timeout issues.

## Pitfalls
- **User-Agent required**: PiAPI sits behind Cloudflare. Python urllib is blocked (HTTP 403, error 1010) without a `User-Agent` header. Always include `\"User-Agent\": \"WAlter-Pipeline/1.0\"` in headers.
- Seedance requires `mode` field — without it the API returns an error
- Kling image_url: pass null explicitly for T2V, not empty string
- Seedance duration is 4-15s (not 5/10 like Kling)
- PiAPI statuses are capitalized (`Completed` not `completed`)
- Output video URLs from PiAPI expire — download/cache them
- Kling 3.0 input: `version` must be `"3.0"`, `mode` is `"std"` (720p) or `"pro"` (1080p)
- Kling o1/3.0 Omni: use `task_type: "omni_video_generation"` with references via `@image_1`, `@video` in prompt
- Multi-shots: PiAPI Kling supports `scenes` array with per-shot prompt + duration
