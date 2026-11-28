# FIRST_FRAME handoff validation — 2×4s 1080p selfie test

## Purpose

Validate the strongest stateless Kie.ai workflow for extending a speaking selfie clip with Gemini Omni: generate clip 1, extract its last frame, pass that image as `image_urls[0]`, and bind it in clip 2 with `[# Sources <FIRST_FRAME>@Image1]`.

## Tested contract

- Model: `gemini-omni-video`
- Duration: `4` seconds per clip
- Resolution: `1080p`
- Aspect ratio: `16:9`
- Clip 2 input: one JPEG in `image_urls`; no `video_list`
- Observed price: 63 credits per clip, 126 credits total
- Output: 1920×1080, 24 fps, H.264/AAC, raw concatenation about 8.04 seconds

## Paired prompt pattern

### Clip 1 ending

Describe the complete scene and speech, then add a deliberate handoff:

> During the final half-second she finishes the sentence, closes her mouth into a gentle smile, stops moving her head and arm, and holds the phone completely steady in one clean neutral pose until the last frame.

### Clip 2 beginning

Start with the native source binding and prohibit the common reset behaviors:

> [# Sources <FIRST_FRAME>@Image1] Image1 is the mandatory exact first frame of this continuation. Begin on Image1 without reframing, zooming, recentering, redesigning, or changing the composition. For the first half-second, preserve the exact still handoff pose and camera position from Image1. Then resume the same continuous selfie recording.

Repeat identity, wardrobe, camera distance, lighting, background geometry, eye line, voice, and intended motion after the hold.

## Observed junction quality

The last frame of clip 1 and first frame of clip 2 preserved:

- the same woman and wardrobe;
- nearly identical framing and arm position;
- the penthouse layout and skyline geometry;
- focal length and golden-hour illumination.

They were not pixel-identical. The model subtly re-rendered mouth shape, eyes, facial expression, and texture. Objective comparison on the two JPEG frames:

- SSIM All: `0.937836`
- PSNR average: `32.732598 dB`

The cut remained perceptible in motion despite strong spatial consistency. Therefore:

1. FIRST_FRAME should be described as high-consistency conditioning, not true extension.
2. Do not call the result seamless without watching the raw junction.
3. Crossfade and optical flow are optional editorial concealment, not evidence that the generation continued exactly.
4. For user-requested evaluation, deliver the raw concat first.

## Operational recovery lesson

A final-frame extraction using `-sseof -0.04` at 24 fps returned exit code 0 but produced no JPEG. The durable extraction pattern is:

```bash
ffmpeg -y -sseof -1 -i clip1.mp4 \
  -frames:v 1 -q:v 1 -update 1 last_frame.jpg

test -s last_frame.jpg
```

Paid pipelines must be resumable. Persist and validate clip 1 before extraction/upload; after a downstream failure, reuse it rather than paying to regenerate it.
