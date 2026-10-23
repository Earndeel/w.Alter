# Gemini Veo 3.1 Lite — Integration Pattern for Scena

Tested 2026-05-25. Model `veo-3.1-lite-generate-preview` via direct Gemini API (NOT PiAPI, NOT Kie.ai).

## SDK & Authentication

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="AIzaSy...")  # vault get gemini/api_key
```

SDK package: `google-genai` (NOT `google-generativeai` — different package, different API shape).

## Video Generation

```python
operation = client.models.generate_videos(
    model="veo-3.1-lite-generate-preview",
    prompt="scene description...",
    config=types.GenerateVideosConfig(
        number_of_videos=1,
        aspect_ratio="16:9",   # "16:9" or "9:16"
        resolution="720p",     # "720p" or "1080p"
    ),
)
```

This returns a **long-running operation**, not a video. Must poll.

## Polling

```python
while not operation.done:
    time.sleep(10)
    operation = client.operations.get(operation)
```

**Pitfall:** `operation.done` returns `None` (not `False`) while running. Use `not operation.done` (truthy check), not `== False`.

Poll interval: 10s is fine. Observed 5 polls (~50s) for an 8-second 720p video.

## Download

```python
if operation.result and operation.result.generated_videos:
    video = operation.result.generated_videos[0]
    client.files.download(file=video.video)
    video.video.save("/tmp/output.mp4")
```

## Empirical Benchmarks (2026-05-25)

| Metric | Value |
|--------|-------|
| Model | `veo-3.1-lite-generate-preview` |
| Duration | 8 sec |
| Resolution | 720p |
| Total time | 53.6 sec (~1 min) |
| Polls | 5 (every ~10s) |
| Output size | 8.7 MB |
| API launch overhead | 2.1 sec |

## Pricing (public rates, May 2026)

| Resolution | Per second | 8 sec video |
|------------|-----------|-------------|
| 720p | $0.05 | **$0.40** |
| 1080p | $0.08 | **$0.64** |

**vs Kie.ai Seedance 2.0 Fast:** Veo Lite is comparable on speed and price, but goes through Google's API directly (no intermediary). For Scena integration, this means a third provider path: `provider=gemini-veo`.

## Capabilities

- Text-to-video (T2V) and image-to-video (I2V)
- Aspect ratios: 16:9, 9:16
- Durations: 4, 6, 8 seconds
- Resolutions: 720p, 1080p
- Native audio support included

## Scena Integration Notes

To add as a Scena provider:
1. New provider route in `agent.ts`: `provider=gemini-veo`
2. Auth: reuse existing `GEMINI_API_KEY` Worker secret
3. No webhook needed — poll synchronously in `ctx.waitUntil` (similar to Fal pattern)
4. Poll via `client.operations.get()` instead of HTTP status_url
5. Shorter max duration (8s vs 15s for Seedance) — may need chaining for longer videos
6. Payload contract in `provider_payloads.ts`: `{ prompt, aspect_ratio?, resolution? }`
7. I2V support: pass image as `types.Part` in `contents` (not a URL field)

## Comparison: Veo Lite vs Seedance 2.0 Fast vs Grok Imagine

| | Veo 3.1 Lite | Seedance 2.0 Fast | Grok Imagine |
|---|---|---|---|
| Provider | Google (direct) | Kie.ai | Kie.ai / Fal |
| Max duration | 8s | 15s | 6s |
| 720p 8-sec cost | $0.40 | ~$0.40 | ~$0.30 |
| Latency | ~54s | ~30-60s | ~20-40s |
| Audio | Yes | No (unless `generate_audio`) | No |
| I2V | Yes | Yes (first_frame_url) | Yes (image_urls) |
| Reference style | No | Yes (reference_image_urls) | No |
