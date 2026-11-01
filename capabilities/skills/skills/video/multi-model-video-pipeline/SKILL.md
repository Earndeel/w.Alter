---
name: multi-model-video-pipeline
description: "Build a multi-model video generation pipeline with model abstraction, LLM payload generation, video extension (I2V chaining), and post-processing. Also covers: multi model video gen."
triggers:
  - "video generation pipeline"
  - "multi model video"
  - "kling fal.ai payload"
  - "video extension I2V"
  - "extend video beyond 15 seconds"
---

# Multi-Model Video Pipeline (Updated 2026-05-25)

## Architecture
```
models/{model_id}/
  config.json   ← {"name": "...", "endpoint": "fal-ai/..."}
  prompt.md     ← LLM preprompt (instructions + rules)
  schema.md     ← API reference (params, types, constraints)
```

The LLM receives: system prompt (prompt.md) + user message (analysis + comments + schema.md). It outputs the JSON payload conforming to the model's API.

## Provider Catalog (May 2026)

| Provider | Model | Max Duration | Cost (8s 720p) | Latency | Audio | I2V | Reference Style |
|----------|-------|-------------|-----------------|---------|-------|-----|-----------------|
| Kie.ai | Seedance 2.0 Fast | 15s | ~$0.40 | ~30-60s | No | Yes | Yes |
| Kie.ai | Seedance 2.0 | 15s | ~$0.52 | ~40-80s | No | Yes | Yes |
| Kie.ai | Grok Imagine | 6s | ~$0.30 | ~20-40s | No | Yes | No |
| Google (direct) | Veo 3.1 Lite | 8s | ~$0.40 | ~54s | Yes | Yes | No |
| Google (direct) | Veo 3.1 Fast | 8s | ~$0.64 | ~40-60s | Yes | Yes | No |

**Veo 3.1 Lite** uses Gemini API directly (`google-genai` SDK), not PiAPI/Kie.ai. See `scena-video-factory` skill `references/gemini-veo-integration.md` for the full integration pattern (polling, download, Scena provider routing plan).

## DB Schema
Generic columns alongside legacy kling_* columns:
```sql
ALTER TABLE video_analysis ADD COLUMN model_id TEXT DEFAULT 'kling_v3';
ALTER TABLE video_analysis ADD COLUMN model_payloads TEXT;
ALTER TABLE video_analysis ADD COLUMN job_status TEXT;
ALTER TABLE video_analysis ADD COLUMN job_request_id TEXT;
ALTER TABLE video_analysis ADD COLUMN job_result TEXT;
ALTER TABLE video_analysis ADD COLUMN job_error TEXT;
```
Always read from generic columns first, fall back to kling_* for backward compat.

## Video Extension (>15s)
Models like Kling max at 15s. Extension strategy:
1. Generate first N seconds (T2V)
2. Extract last frame via ffmpeg: `ffmpeg -ss {duration-0.5} -i video.mp4 -frames:v 1 -q:v 2 lastframe.jpg`
3. Upload frame to Fal.ai to get URL
4. Generate next segment as I2V with last frame as `image_url`
5. Repeat until target duration
6. Concat with ffmpeg concat demuxer

### Pitfall: I2V endpoint derivation
Convert T2V endpoint to I2V: `text-to-video` → `image-to-video`. Not all models support both.

## Agent Pipeline (4 stages)
1. **Analyse** (Gemini 3.1 Pro) → StructuredNeed JSON
2. **Planification** (Gemini 3.1 Pro) → ActionPlan with steps + costs
3. **Génération** → LLM payload → Fal.ai submit → result
4. **Fignolage** → ffmpeg subtitles, filters, TTS, lipsync

## Post-Processing Tools
- `burn_subtitles()` — generate SRT, ffmpeg subtitles filter
- `apply_filter()` — color grade, speed, crop, fade, blur
- `generate_tts()` — Edge TTS (free), extensible to ElevenLabs
- `lipsync()` — audio replace (placeholder for Wav2Lip integration)
- `concat_clips()` — ffmpeg concat demuxer

### FFmpeg Filter Cookbook
See `references/ffmpeg-filters.md` for verified filter chains (iphone lowlight look, auto-exposure pulsing). Both tested on ARM64 with performance benchmarks.

## Credit System
- Each model has cost_per_second in shared/pricing.json
- Apply margin multiplier (default 1.5x)
- Convert USD to credits (1 credit = $0.01)
- Charge before generation, fail if insufficient balance
- Track in both central DB and per-client DB

## Webhook/CORS for Cross-Origin Landing → API
Frontend on `scena.walter-ai.cloud` calling `api.walter-ai.cloud` requires CORS:
```python
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        return '', 204
```

## Client Auto-Provisioning Flow
1. Clerk auth on landing page → calls `/api/signup`
2. Backend finds existing client by email OR clerk_id in notes
3. If new: assign bot from pool + create client env + start dashboard
4. If existing: return current bot/dashboard/credits info
5. Dashboard tunnel auto-created, URL stored in client config.json

## Pitfall: Model ID = Directory Name
Don't store `id` inside config.json — derive it from the folder name:
```python
cfg['id'] = os.path.basename(model_dir)  # id = directory name
```

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **multi-model-video-gen** — The earlier parameterised multi-model video generator via Fal.ai with Higgsfield MCP as an alternative.
  Read `references/merged-multi-model-video-gen/multi-model-video-gen.md` (+ 1 supporting file in that folder).
