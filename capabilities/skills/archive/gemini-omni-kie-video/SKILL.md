---
name: gemini-omni-kie-video
description: "Use for Gemini Omni Flash video generation via Kie.ai API."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [kie, gemini-omni, video-generation, extend, pricing, api]
    related_skills: [kie-gemini-mastery, fal-mcp-integration, model-value-analysis]
---

# Gemini Omni Flash — Video via Kie.ai

Gemini Omni Flash (`gemini-omni-flash-preview`) is Google's multimodal video generation model. On Kie.ai available as `gemini-omni-video` (plus Character and Audio endpoints).

## When to Use

- Generating video with Gemini Omni Flash via Kie.ai API
- Comparing Gemini Omni pricing across providers (Google API, Kie.ai, Fal.ai)
- Attempting video extension/prolongation beyond the 10s limit
- Debugging safety filter blocks on input video audio
- Understanding `video_list` vs `image_urls` + `<FIRST_FRAME>` for continuity

## API Endpoints (Kie.ai)

```
POST https://api.kie.ai/api/v1/jobs/createTask
GET  https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<id>
```

**CRITICAL:** The polling endpoint is `recordInfo`, NOT `getTaskDetail` (returns 404).

### Response fields

| Field | Meaning |
|---|---|
| `data.state` | `waiting` → `success` / `fail` |
| `data.resultJson` | JSON string with `resultUrls` array |
| `data.creditsConsumed` | 63 (4s/1080p), 168 (video_list mode) |
| `data.failMsg` | Failure reason (e.g. Google Safety) |
| `data.failCode` | HTTP-style code (400 = safety block) |
| `data.costTime` | Processing time in seconds |

## Pricing (July 2026, 1 credit ≈ $0.005)

### Without video input

| Duration | 720p/1080p | 4K |
|---|---|---|
| 4s | 63 cr ($0.315) | 147 cr ($0.735) |
| 6s | 84 cr ($0.42) | 168 cr ($0.84) |
| 8s | 105 cr ($0.525) | 189 cr ($0.945) |
| 10s | 126 cr ($0.63) | 210 cr ($1.05) |

### With video input (extend/edit mode)

| Resolution | Flat rate |
|---|---|
| 720p/1080p | 168 cr ($0.84) |
| 4K | 252 cr ($1.26) |

Duration is auto-determined by the model when `video_list` is present — the `duration` parameter is ignored.

## Request Parameters

```json
{
    "model": "gemini-omni-video",
    "input": {
        "prompt": "...",
        "duration": "4",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "image_urls": ["https://..."],
        "video_list": [{"url": "https://...", "start": 0, "ends": 4}],
        "audio_ids": ["..."],
        "character_ids": ["..."]
    }
}
```

Quota: images=1 unit, videos=2 units, character_ids=1 unit. Max 7 units.

## Video Extension Mechanics

### `video_list` behavior

Input video is used as **contextual reference** — same location, lighting, aesthetic. The API accepts it. However:

- **NOT frame-perfect:** Last frame clip1 ≠ first frame clip2
- **Scene may drift** while keeping same vibe
- Per Google docs: *"Video extension and video interpolation are not supported."*

### Why Flow's "prolonger" works

Flow uses the Interactions API (`previous_interaction_id`) which keeps full video state across turns — this stateful mechanism is NOT exposed by Kie.ai's REST API.

### FIRST_FRAME tag (partial workaround)

Google supports using an image as exact starting frame via `<FIRST_FRAME>` or `[# Sources <FIRST_FRAME>@Image1]`.

Via Kie.ai pipeline:
1. `ffmpeg -sseof -1 -i clip.mp4 -vframes 1 frame.jpg`
2. Upload: `curl -F "fileToUpload=@frame.jpg" https://catbox.moe/user/api.php`
3. Submit with `image_urls=[frame_url]` + FIRST_FRAME prompt
4. Result: better than `video_list` alone, but not pixel-perfect

## Safety Pitfalls

**Audio flagging (CRITICAL):** Input videos with speech/voice are blocked: `failCode: 400, failMsg: "The uploaded audio was flagged by Google safety review."` Use visual-only clips for `video_list`. 0 credits consumed on block.

**Regional:** Video editing not available for EEA, Switzerland, UK users.

## Cross-Provider Pricing (720p, per-second)

| Model | Google API | Kie.ai | Fal.ai |
|---|---|---|---|
| Gemini Omni Flash | $0.10/s | **$0.063/s** | $0.13/s |
| Seedance 2.0 Fast | — | **$0.165/s** | $0.242/s |
| Grok Imagine 1.5 | $0.05/s (xAI) | **$0.015/s** | N/A |

See `references/gemini-omni-provider-pricing.md` for full table with 4K, Seedance variants, and clip costs.

## Related Skills

- `kie-gemini-mastery` — LLM provider setup, Claude/GPT pricing, WAF bypass
- `fal-mcp-integration` — Fal.ai tool catalog, Kling/Seedance pricing
- `model-value-analysis` — Provider price comparison, Pareto frontier
