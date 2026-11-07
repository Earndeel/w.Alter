---
name: gemini-omni-video-generation
description: Gemini Omni Flash video generation and extension via Kie.ai.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [video, gemini-omni, kie.ai, extension, pipeline]
    related_skills: [kie-gemini-mastery, model-value-analysis, video-postproduction]
---

# Gemini Omni Video Generation & Extension

Gemini Omni Flash (`gemini-omni-flash-preview`) is Google's multimodal video model. It generates up to 10s clips with native audio, supports image/video references, and conversational editing via the Interactions API. Kie.ai exposes it under model ID `gemini-omni-video`.

## When to Use

- Generating short video clips (< 10s) with Gemini Omni Flash via Kie.ai, Google API, or Fal.ai
- Extending videos beyond the 10-second cap using the FIRST_FRAME + crossfade pipeline
- Comparing Gemini Omni pricing across providers
- Debugging video generation failures (safety filters, credit issues, parameter errors)

## API Reference (Kie.ai)

### Create task
```
POST https://api.kie.ai/api/v1/jobs/createTask
Authorization: Bearer <KIE_API_KEY>
Content-Type: application/json

{
    "model": "gemini-omni-video",
    "input": {
        "prompt": "...",            // required
        "duration": "4",            // 4, 6, 8, or 10 — required
        "aspect_ratio": "16:9",     // 16:9 or 9:16 — required
        "resolution": "1080p",      // 720p, 1080p, or 4k — optional, defaults to 720p
        "image_urls": ["https://..."],   // optional, up to 7 minus other slot usage
        "video_list": [{ "url": "...", "start": 0, "ends": 4 }], // optional, costs 2 slots
        "character_ids": ["..."],   // optional, 1 slot each, max 3
        "audio_ids": ["..."]        // optional, max 1
    }
}
```

**Slot budget:** `(images × 1) + (videos × 2) + (character_ids × 1) ≤ 7`

### Poll status
```
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>
Authorization: Bearer <KIE_API_KEY>
```

Key response fields: `state` (waiting|success|fail), `resultJson` → `resultUrls[]`, `creditsConsumed`, `costTime`, `failCode`, `failMsg`. Poll every 10 seconds.

## Pricing

1 Kie credit ≈ $0.005. All prices below are for generation mode (no video input).

| Duration | 720p/1080p | $/s effective | 4K |
|----------|-----------|---------------|-----|
| 4s | 63 cr ($0.315) | $0.079/s | 147 cr ($0.735) |
| 6s | 84 cr ($0.42) | $0.070/s | 168 cr ($0.84) |
| 8s | 105 cr ($0.525) | $0.066/s | 189 cr ($0.945) |
| 10s | 126 cr ($0.63) | $0.063/s | 210 cr ($1.05) |

Longer clips have a lower per-second rate (fixed setup cost absorbed).

**With video input (edit mode):** flat 168 cr ($0.84) for 720p/1080p, 252 cr ($1.26) for 4K. Duration auto-determined by model. **Not recommended for extension** — see pitfalls.

**Bulk top-ups:** +10% bonus credits → effective cost ~90% of listed.

## Provider Price Comparison (720p, 10s clip)

| Provider | $/s | 10s cost | vs Google API |
|----------|-----|----------|---------------|
| **Kie.ai** | $0.063/s | $0.63 | −37% |
| Google API | $0.10/s | $1.01 | reference |
| Fal.ai | $0.13/s | $1.30 | +30% |

Google bills at $17.50/1M tokens, fixed 5,792 tokens/s of 720p video ($0.1014/s). Fal.ai bills at $21.875/1M output tokens ($0.13/s). Both charge separately for input tokens.

## Video Extension Pipeline

Gemini Omni Flash hard-caps at 10s per generation. Google explicitly lists "Video extension" as not supported. The stateless FIRST_FRAME pipeline can improve spatial consistency, but it is not true extension and must not be described as near-seamless without inspecting the raw junction.

### Step 1: Generate Clip 1 with a planned handoff
Generate clip 1 with its creative prompt, but reserve the final ~0.5 seconds for a neutral stable handoff: finish speech, close the mouth, stop head/arm motion, and hold the camera steady. Save and validate the video before any downstream step so extraction/upload failures can resume without paying to regenerate it.

### Step 2: Extract last frame + upload
```bash
ffmpeg -y -sseof -1 -i clip1.mp4 -frames:v 1 -q:v 1 -update 1 last_frame.jpg
test -s last_frame.jpg
# Upload to public URL — catbox.moe is free and reliable:
curl -F "fileToUpload=@last_frame.jpg" https://catbox.moe/user/api.php
# Returns: https://files.catbox.moe/XXXXX.jpg
```

### Step 3: Generate Clip 2 with a FIRST_FRAME prompt instruction
Pass the extracted frame as `image_urls[0]` and refer to it with `[# Sources <FIRST_FRAME>@Image1]`. Important: Kie.ai documents `image_urls` only as generic multimodal references and exposes no API-level first-frame field or mode. This syntax asks the model to imitate the reference at the start; it does not force frame 0 to equal the uploaded image:

```json
{
    "model": "gemini-omni-video",
    "input": {
        "prompt": "[# Sources <FIRST_FRAME>@Image1] Continue this exact shot from where it left off — same person, same lighting, same background, same camera angle. The transition must be invisible. Use Image1 as the exact starting frame.",
        "duration": "10",
        "aspect_ratio": "16:9",
        "resolution": "1080p",
        "image_urls": ["https://files.catbox.moe/XXXXX.jpg"]
    }
}
```

This costs 63 cr (standard generation rate) — cheaper than `video_list` mode (168 cr) and provides better continuity.

### Step 4: inspect the raw junction first

Concatenate the clips without a transition and inspect the last frame of clip 1 against the first frame of clip 2. A crossfade or optical-flow morph is optional post-production only when explicitly requested; it can conceal a reset but cannot make the generation frame-exact.

Design both prompts around the handoff: clip 1 should hold a neutral closed-mouth pose and steady camera for its final ~0.5 seconds; clip 2 should preserve Image1 and that pose for its first ~0.5 seconds before resuming speech or movement. Keep the paired prompts explicit about identity, wardrobe, focal length, eye line, lighting, background geometry, and camera distance.

### Continuity quality by method

| Method | Clip 2 cost | Typical result | Frame-exact? |
|--------|-------------|----------------|--------------|
| `video_list` alone | 168 cr flat-rate | Context may persist while room composition changes | No |
| `[# Sources <FIRST_FRAME>@Image1]` | Standard duration rate | Strong spatial/identity consistency; face and expression may be re-rendered | No |
| FIRST_FRAME + crossfade/optical flow | Generation + local post | May conceal a cut; can also introduce morphing artifacts | No |

A measured 2×4s 1080p selfie test using paired handoff prompts preserved framing, wardrobe, room, skyline, and lighting, but still produced a perceptible facial/expression reset (junction SSIM 0.937836; PSNR 32.73 dB). Load `gemini-omni-video-extension` for the detailed paired-prompt recipe, robust final-frame extraction, resumable paid-task handling, and session evidence.

Cost accounting must use the duration table above. Examples: two 4-second 1080p clips cost 126 credits total; two 10-second 1080p clips cost 252 credits total.

### Why Flow's "prolonger" works better
Google Flow uses the Interactions API with `previous_interaction_id` — a stateful mode where the model has the full previous clip in memory. This enables true extension (transforming the existing video). Kie.ai's stateless API cannot replicate this. The FIRST_FRAME pipeline is the best available approximation.

## Pitfalls

1. **Audio safety filter on `video_list`:** Clips with speech used as `video_list` input often trigger "The uploaded audio was flagged by Google safety review" (failCode 400). Credits are refunded (0 consumed). Use FIRST_FRAME with `image_urls` instead.
2. **Credit exhaustion (402):** Each 4s 1080p clip is 63 cr. Budget accordingly — a full extension test (clip1 + clip2) costs 126 cr ($0.63).
3. **Duration and `aspect_ratio` are REQUIRED** — omitting returns 422: "Aspect ratio only supports [16:9, 9:16]".
4. **No true extend endpoint exists** — there is no native "extend" or "prolonger" via Kie.ai. The pipeline above is the only proven method.
5. **FIRST_FRAME syntax matters:** `[# Sources <FIRST_FRAME>@Image1]` works reliably. Using only `<FIRST_FRAME>` embedded in prose text may be ignored.
6. **10-second hard cap:** The model refuses durations above 10s. No workaround — generate multiple clips and stitch.
7. **No Batch discount, no free tier:** Unlike other Gemini models, Omni Flash offers only Standard pricing with no Batch API and no free tier.
8. **Google uses your content for training** even on the paid tier for `gemini-omni-flash-preview` (unlike most paid Gemini models). Do not feed sensitive/unreleased footage.
