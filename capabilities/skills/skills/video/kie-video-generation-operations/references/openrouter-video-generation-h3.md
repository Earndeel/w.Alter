# OpenRouter native video generation — MiniMax H3

Verified 2026-08-02 against OpenRouter's Video Models API and one completed paid job. This is a provider-specific reference for the class-level video-generation workflow.

## Live contract

Use the video-specific catalog, not the chat catalog:

```text
GET https://openrouter.ai/api/v1/videos/models
GET https://openrouter.ai/api/v1/models?output_modalities=video
```

Verified entry:

```text
id: minimax/hailuo-3
canonical_slug: minimax/hailuo-03-20260730
name: MiniMax: H3
supported_resolutions: [2K]
supported_aspect_ratios: [21:9, 16:9, 4:3, 1:1, 3:4, 9:16]
supported_durations: 5..15 seconds
generate_audio: true
pricing_skus: duration_seconds=0.13, reference_images=0.04
```

The ordinary `GET /api/v1/models` list is not sufficient evidence for video output and may show MiniMax chat/video-input models instead. Never silently substitute `minimax/minimax-m3`, Hailuo 2.3, or another provider for a request naming H3.

## Submit and poll

Retrieve `openrouter/api_key` via the vault skill without printing it. Check `GET https://openrouter.ai/api/v1/credits` before the paid call. Submit to `POST https://openrouter.ai/api/v1/videos`:

```json
{
  "model": "minimax/hailuo-3",
  "prompt": "<exact approved prompt>",
  "duration": 15,
  "resolution": "2K",
  "aspect_ratio": "16:9",
  "generate_audio": true,
  "input_references": [
    {"type": "image_url", "image_url": {"url": "https://public.example/ref-1.png"}},
    {"type": "image_url", "image_url": {"url": "https://public.example/ref-2.png"}},
    {"type": "image_url", "image_url": {"url": "https://public.example/ref-3.png"}}
  ]
}
```

Check reference URLs first and keep UI attachment markers (`@image:` / screenshot markers) out of the prompt. The API returns HTTP 202 with a job ID and `polling_url`; poll `GET /api/v1/videos/<job_id>` every 30–60 seconds. Do not resubmit while status is `pending`: the verified 2K H3 job stayed pending for roughly ten minutes before completing.

A completed result contains `generation_id`, `unsigned_urls`, and `usage.cost`. Download the MP4 immediately and preserve the raw file separately from any normalized deliverable.

## Traceability when the dashboard looks empty

OpenRouter's Chat activity view is not the authoritative log for the video API. Prove the request with:

```text
GET https://openrouter.ai/api/v1/generation?id=<generation_id>
```

Record only non-secret fields: `model`, `api_type: video`, `origin: api`, `provider_name`, HTTP status, `total_cost`, and `cancelled`. Compare `/api/v1/credits` before/after as an independent account-level check. A verified job returned upstream model `minimax/hailuo-03-20260730`, provider `Minimax`, `api_type=video`, `origin=api`, HTTP 200, and total cost `1.9305` USD.

## Media QA

Do not report completion from HTTP 202 alone. Run `ffprobe`, full decode, audio-level analysis, and a 1-fps storyboard on the actual downloaded file. A verified H3 output measured 2560×1440, 24 fps, H.264, AAC stereo, and 15.083 seconds before normalization. If the brief requires exactly 15.000 seconds, trim both streams explicitly and map audio:

```bash
ffmpeg -hide_banner -loglevel error -i input.mp4 \
  -filter_complex "[0:v:0]trim=duration=15,setpts=PTS-STARTPTS[v];[0:a:0]atrim=duration=15,asetpts=PTS-STARTPTS[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart output.mp4
```

Require measured `format.duration == 15.000000`, 2560×1440, expected frame count at 24 fps, an audio stream, and clean `ffmpeg -f null -` decoding. Use scene detection only as supporting evidence; inspect the storyboard for identity, clothing, environment, action progression, final pose, anatomy, extra people, text, watermarks, and reference-sheet residue.
