---
name: google-veo-official-api
category: mlops
description: Google Veo 3.1 video generation via the official Gemini API (google-genai SDK). Covers three models (Quality/Fast/Lite), full GenerateVideosConfig, polling, download, pricing, and pitfalls.
---

# Google Veo 3.1 — Official Gemini API

Generate videos via Google's official `google-genai` SDK. Direct API, not PiAPI/Kie.ai wrappers, not the Flow web UI.

## Model Catalog (July 2026)

| Model ID | Grade | Speed | $/sec | 8s 1080p |
|----------|-------|-------|-------|----------|
| `veo-3.1-generate-001` | Quality | 2-5 min | $0.75 | ~$6.00 |
| `veo-3.1-fast-generate-001` | Fast | 40-60s | $0.08 | ~$0.64 |
| `veo-3.1-lite-generate-001` | Lite | ~54s | $0.05 | ~$0.40 |

Old `*-preview` suffixed model IDs still work but prefer `-001` stable.

## Quickstart

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="...")

operation = client.models.generate_videos(
    model="veo-3.1-generate-001",
    prompt="A detailed video description...",
    config=types.GenerateVideosConfig(
        aspect_ratio="9:16",          # "16:9" or "9:16"
        number_of_videos=1,           # 1 or 2
        duration_seconds=8,           # 4, 6, or 8 (MAX 8)
        resolution="1080p",           # "720p", "1080p", "4k"
        person_generation="allow_adult",
        generate_audio=True,
    ),
)

# Poll until done
import time
while not operation.done:
    time.sleep(10)
    operation = client.operations.get(operation)

# Save
if operation.result and operation.result.generated_videos:
    video = operation.result.generated_videos[0]
    with open("/tmp/output.mp4", "wb") as f:
        f.write(video.video.video_bytes)
```

## Image-to-Video (I2V)

```python
operation = client.models.generate_videos(
    model="veo-3.1-generate-001",
    prompt="animate this scene...",
    image=types.Image.from_file(location="/path/to/frame.png"),
    config=types.GenerateVideosConfig(...),
)
```

## Pitfalls

- **Max 8 seconds.** No 10s option in the API. If a brief requires 10s, use the Flow web UI (Omni Flash supports 10s) or chain I2V segments.
- **`operation.done` returns `None`** (not `False`) while running. Use truthy check: `not operation.done`.
- **SDK package is `google-genai`**, NOT `google-generativeai` — different package, incompatible API.
- **Cost is per-second of output**, not per-request. Veo Quality at $0.75/s × 8s = ~$6/clip.
- **API key** stored in the environment. Use the configured Gemini key (check config).

## API vs Flow Web UI

| | Gemini API | Flow Web UI |
|---|---|---|
| Models | Quality, Fast, Lite | Same + Omni Flash |
| Max duration | 8s | 10s (Omni Flash only) |
| Auth | API key | Google login + cookies |
| Automation | Direct SDK | Browser (React contenteditable) |

Prefer the API for automation. Only use Flow UI when Omni Flash 10s is needed or no key is available.

## Related

- `references/flow-camoufox-pitfall.md` — React contenteditable workaround for Flow web UI when API is not an option
