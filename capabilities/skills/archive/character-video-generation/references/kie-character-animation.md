# Kie.ai character animation — verified details

## Seedance 2 Mini

Official model ID:

```text
bytedance/seedance-2-mini
```

Verified Reference-to-Video request shape:

```json
{
  "model": "bytedance/seedance-2-mini",
  "input": {
    "prompt": "The person moves at natural real-life speed...",
    "reference_image_urls": ["https://public.example/reference.png"],
    "resolution": "480p",
    "aspect_ratio": "9:16",
    "duration": 4,
    "generate_audio": false
  }
}
```

Observed behavior:

- Native 4-second generation is accepted.
- `resolution: "480p"` produced a vertical 496×864 file at 24 fps; report measured dimensions rather than relabeling it as literal 480 pixels.
- Reference mode uses `reference_image_urls` as an array.
- First-frame mode uses `first_frame_url`; do not combine it with reference fields.
- For character identity and dentition, use Reference-to-Video rather than First-Frame I2V unless exact frame-zero composition is the primary goal.

## Grok Imagine Video 1.5 Preview

For image-conditioned generation with `grok-imagine-video-1-5-preview`, use plural image input:

```json
"image_urls": ["https://public.example/reference.png"]
```

Do not use singular `image_url`. The request may be accepted while the upstream model ignores the image and generates an unrelated person from frame zero. Always compare source and frame 0 before delivery.

## Timing lesson

A ten-second prompt containing only a blink, a breath, and a small head adjustment can produce stretched, slow-looking movement despite explicit negative wording. Prefer native short duration and enough actions to fill it. Check cadence visually; 24 fps describes frame rate, not action speed.

## Verification checklist

- Confirm returned task model equals requested model.
- Probe file dimensions, frame rate, and exact duration.
- Compare source with frame 0 for first-frame requests.
- Build a contact sheet at one-second or evenly spaced intervals.
- Inspect face and teeth continuity plus actual movement cadence.
