# Kie/Grok reference run notes

## Validated contracts

### Still

- Kie model: `gpt-image-2-text-to-image`.
- Payload used: `input.prompt` + `input.aspect_ratio: "auto"`.
- Measured result: 941×1672 pixels, PNG source plus WebP derivative.
- Observed cost/time: 6 Kie credits, 72 seconds.

### Animation

- Kie model: `grok-imagine/image-to-video`.
- Payload fields: `image_urls`, `prompt`, `mode: "normal"`, `duration: "6"`, `resolution: "720p"`, `aspect_ratio: "9:16"`.
- Measured result: 720×1264 pixels, 24 fps, 6.041667 seconds, H.264 video at about 8.8 Mb/s with stereo AAC audio.
- Observed cost/time: 18 Kie credits, 87 seconds.
- WebM fallback: VP9, 720×1264, 24 fps, no audio when encoded for muted autoplay.

## Upload and recovery

Use Kie’s file-stream upload for a local reference when possible. If an alternate temporary uploader rejects the multipart request, do not regenerate the image; use the provider upload contract instead. Persist the returned URL and task ID.

A local polling collector can lose its connection while the provider task remains `waiting` or `success`. Query `recordInfo` with the saved task ID and retry the same result URL. Never resubmit solely because the local process failed.

## QA pattern

Extract frames at 0 s, 2 s, 4 s and the end. The accepted run retained the same bun, earrings, cream t-shirt, shoulder bag, face and street while showing natural speech, arm movement and walking parallax. Reject a phone-in-phone opening, a first-second transition into the selfie view, bokeh, readable generated signage, or identity drift.

Before delivery, remove provider-attached thumbnail streams:

```text
ffmpeg -i input.mp4 -map 0:v:0 -map 0:a:0? -c copy -movflags +faststart clean.mp4
```

Treat all dimensions and codecs above as observed outputs, not guarantees; verify every new run with `ffprobe`.
