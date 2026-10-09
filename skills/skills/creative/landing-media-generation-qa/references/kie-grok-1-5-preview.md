# Kie Grok Imagine Video 1.5 Preview

Session-derived operational reference for landing-page media generation. Keep provider task manifests and temporary result URLs out of public assets.

## Exact contract

- Image model used for source visuals: `grok-imagine/text-to-image`.
- Video model: `grok-imagine-video-1-5-preview`.
- Create endpoint: `POST https://api.kie.ai/api/v1/jobs/createTask`.
- Poll endpoint for this Market model: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>`.
- Verified input keys: `image_urls`, `prompt`, `aspect_ratio`, `resolution`, `duration`.
- Working landing preset: `aspect_ratio: "9:16"`, `resolution: "480p"`, `duration: 6`.

Official documentation consulted during the workflow: `https://docs.kie.ai/market/grok-imagine/text-to-image`, `https://docs.kie.ai/market/grok-imagine/text-to-video`, and `https://docs.kie.ai/file-upload-api/upload-file-base-64`.

## Correct result parsing

A successful status response contains nested JSON:

```json
{
  "code": 200,
  "data": {
    "state": "success",
    "resultJson": "{\"resultUrls\":[\"https://.../generated_video.mp4\"]}"
  }
}
```

Parse `data.resultJson`, then read `resultUrls[0]`. Do not recursively scan all response URLs: `data.param` contains the input `image_urls`, so a generic URL finder can save the source JPG under an `.mp4` filename. The provider still reports `state: success`; only media inspection exposes the mistake.

## Image source and upload fallback

When the prior image task returns a public temporary Kie URL, feed that URL directly into `image_urls`; no upload is needed. If Kie file upload returns Cloudflare `403 Error 1010 browser_signature_banned`, do not retry that same endpoint. Use the public Kie image URL or an explicitly approved public storage/CDN path instead. Do not deploy a temporary page solely to bypass a blocked upload without approval.

## Validation commands

After downloading the exact result URL, run `ffprobe` and require:

- duration greater than one second, preferably close to the requested six seconds;
- a video stream with non-zero dimensions;
- a browser-compatible codec;
- non-empty, reasonable file size.

A one-frame file or an image URL saved as `.mp4` is invalid even when the API state is `success`.

Observed Kie output for the 1.5 Preview was H.264/AAC, approximately 6.04 seconds at 400×736. This is close to, but not mathematically equal to, 9:16. Use a 9:16 CSS frame with `object-fit: cover`; do not silently destructively crop the source without visual review.

## Web delivery pattern

Use a poster and two codecs where the browser matrix needs it:

```html
<video autoplay loop muted playsinline preload="metadata"
       poster="/assets/media/grok/grok-beauty.webp">
  <source src="/assets/media/grok/grok-beauty.webm" type="video/webm">
  <source src="/assets/media/grok/grok-beauty.mp4" type="video/mp4">
  <img src="/assets/media/grok/grok-beauty.webp" alt="Campagne beauté éditoriale">
</video>
```

Use WebM VP9 before MP4 when the QA Chromium build has no H.264/AAC decoder; keep MP4 H.264/AAC for Safari/iOS and common production browsers. Apply identical `width`, `height`, and `object-fit: cover` rules to image and video selectors. Decorative loops should stay muted and audio-free unless explicitly requested.

## UGC selfie guardrails

"Selfie" is ambiguous for image/video models: a first attempt can produce a phone held in another hand or a phone screen displayed inside the scene. For a direct testimonial, specify that the viewer sees the creator directly through the front-facing camera and explicitly forbid any visible phone, screen, device, hand, fingers, mirror, or filming equipment. Use shoulders-up framing, direct eye contact, natural skin, slight handheld movement, one continuous take, and forbid captions, logos, watermarks, and beauty-filter distortion.

Generate and inspect the keyframe before paying for I2V. If it shows a device or phone-within-phone composition, regenerate the keyframe with those negative constraints before submitting the video task. The final frame should read as a creator speaking to the viewer, not as a product shot of a phone.

## Visual and responsive QA

1. Inspect generated images and extracted representative video frames with `vision_analyze`; reject text, logos, watermarks, malformed product geometry, broken anatomy, or a style mismatch.
2. Serve the page with a Range-capable local static server when testing video metadata; simple servers may not satisfy Chromium’s byte-range loading.
3. In Playwright, check desktop and mobile: no horizontal overflow, no console/page errors, generated images with non-zero natural dimensions, and every video at `readyState >= 2` with duration above five seconds.
4. If `canPlayType` is empty for H.264 in the runner, test the WebM source and validate MP4 with `ffprobe`; do not add an application workaround for a codec absent only from the runner.
5. Remove the task manifest and temporary provider URLs from the public asset directory before deployment.

## Empirical cost

The two 6-second 480p video tasks consumed 9.6 Kie credits each in this run. Treat this as an observation, not a price guarantee; check current account balance/pricing before future batches.
