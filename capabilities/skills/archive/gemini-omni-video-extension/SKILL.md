---
name: gemini-omni-video-extension
description: Extend Gemini Omni video via Kie.ai using FIRST_FRAME.
version: 1.0.0
author: W.Alter
category: creative
metadata:
  hermes:
    tags: [video, gemini-omni, kie, extension]
---

# Gemini Omni Video Extension via Kie.ai

## Fundamental Limitation

Gemini Omni CANNOT do frame-perfect extension via Kie.ai — the Google Interactions API (`previous_interaction_id`) used by Flow internally is not exposed. Kie.ai documents `image_urls` only as generic multimodal image inputs; it exposes no `first_frame_url`, generation mode, or other field that binds an image as frame 0. The prompt token `[# Sources <FIRST_FRAME>@Image1]` is therefore only an instruction applied to a reference image, not an API-level first-frame constraint. Observed output confirms this: the first generated frame is re-rendered rather than copied pixel-exactly.

## Reference-Based Approximation (Kie.ai — Not True First Frame)

1. **Generate Clip 1** (4–10s, any resolution)
2. **Extract last frame**:
   ```bash
   ffmpeg -y -sseof -1 -i clip1.mp4 -vframes 1 -q:v 2 -update 1 last_frame.jpg
   ```
3. **Upload to catbox.moe** (reliable free upload):
   ```python
   requests.post("https://catbox.moe/user/api.php",
       data={"reqtype": "fileupload"},
       files={"fileToUpload": ("frame.jpg", img, "image/jpeg")})
   ```
4. **Generate Clip 2** with FIRST_FRAME tag:
   ```json
   {
     "model": "gemini-omni-video",
     "input": {
       "prompt": "[# Sources <FIRST_FRAME>@Image1] Continue this exact shot...",
       "image_urls": ["PUBLIC_URL"],
       "duration": "4",
       "aspect_ratio": "16:9",
       "resolution": "1080p"
     }
   }
   ```
5. **Concatenate raw first and inspect the actual junction.** Do not add a crossfade or optical-flow morph unless the user explicitly asks for post-processing. Those techniques can hide a cut but do not prove that FIRST_FRAME continuity worked.

## Prompt design for a clean handoff

The prompts on both sides of the junction must be designed together. Injecting an arbitrary last frame from a clip that ends mid-speech or mid-motion predictably produces a visible reset.

- **Clip 1 ending:** reserve roughly the final 0.5 seconds for a stable handoff. The subject finishes the sentence, closes their mouth, stops head/arm motion, and holds the phone and expression steady until the last frame.
- **Clip 2 beginning:** use `[# Sources <FIRST_FRAME>@Image1]`, explicitly identify Image1 as the mandatory first frame, forbid reframing/recentering/redesign, hold the exact pose for roughly 0.5 seconds, then resume speech and motion.
- Keep identity, wardrobe, camera distance, focal length, lighting, background geometry, voice, and eye line explicit in both prompts.
- Prefer a neutral closed-mouth handoff. A speaking mouth, blink, large gesture, or moving handheld camera gives the model more state to re-synthesize and therefore a more visible cut.
- Use only `image_urls` for this workflow. Do not add `video_list` unless the user explicitly asks for edit mode and accepts its separate flat-rate pricing.

FIRST_FRAME is still conditioning, not a pixel-preserving continuation primitive. Even with paired prompts, Gemini may re-render facial details or expression on frame 1 of clip 2. Measure and report the junction honestly; never call it seamless merely because the subject and room are consistent.

## Robust last-frame extraction

Avoid seeking exactly one frame from EOF (for example `-sseof -0.04` at 24 fps): timestamp rounding can return success while producing no image. Use a one-second tail and overwrite until the final decoded frame, then verify the file exists and is non-empty:

```bash
ffmpeg -y -sseof -1 -i clip1.mp4 \
  -frames:v 1 -q:v 1 -update 1 last_frame.jpg

test -s last_frame.jpg
```

When implementing this in a paid pipeline, make each stage resumable: if clip 1 was already generated and validated, reuse it after an extraction/upload failure rather than submitting and charging a duplicate generation.

## API Reference

- **Create**: `POST /api/v1/jobs/createTask`
- **Poll**: `GET /api/v1/jobs/recordInfo?taskId=X` (state: waiting/success/fail)
- **Result**: `resultJson.resultUrls[0]`

## Costs

- Generation (no input): 63 credits per 4s 1080p clip
- With video_list: 168 credits (flat rate, no duration control, safety risk on audio)
- With image_urls only: 63 credits

## When NOT to Use Gemini Omni

- **Seedance 2.0**: Native `first_frame_url` + `last_frame_url` for frame-perfect bridging
- **Google Interactions API directly**: True stateful extension with `previous_interaction_id` (bypass Kie.ai)

## Session evidence

See `references/first-frame-handoff-validation.md` for the paired-prompt recipe, measured 2×4s/1080p junction (SSIM/PSNR), raw-concat QA rule, and resumable extraction recovery.

## Pitfalls

1. Audio on input video triggers Google Safety block — stick to image_urls
2. `[# Sources <FIRST_FRAME>@Image1]` works; plain `<FIRST_FRAME>` may not
3. Catbox.moe reliable; 0x0.st often returns 503
4. Kie.ai `/api/v1/file/upload` returns 404
5. MP4 URLs as image_urls = 500 error
