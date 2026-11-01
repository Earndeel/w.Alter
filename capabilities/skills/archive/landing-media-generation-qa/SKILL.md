---
name: landing-media-generation-qa
description: Generate and QA campaign media for web surfaces and ads.
version: 1.1.1
author: W.Alter
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [landing-page, image-generation, video-generation, kie, qa, web-performance]
    category: creative
    related_skills: [landing-page-product-images, kie-video-generation, headless-screenshot-qa, video-postproduction]
---

# AI Landing Media Pipeline Skill

Use this skill when a landing page needs generated images, short videos, or both, and the assets must be integrated into a real static or frontend codebase. It covers provider-contract verification, asynchronous generation, media validation, browser fallbacks, and responsive visual QA; it does not replace the landing page’s design system or deployment approval.

## When to Use

- Generate a coherent image set for an existing landing page.
- Produce exact-size multi-brand static ads from a client thread, reference image, and voice-note refinements.
- Animate generated images into short hero/gallery loops.
- Replace static frames with video while retaining a reliable poster fallback.
- Validate generated files before exposing them through a public asset directory.
- Diagnose a provider task that reports success but returns the wrong or unusable media URL.
- Remove a fixed visible provider watermark from a user-owned/generated video while preserving scene-generated text and logos; see `references/video-watermark-removal.md`.

## Prerequisites

- Follow the repository’s local conventions and the relevant frontend/design skill.
- Confirm the exact provider model slug and payload contract from current provider documentation; never infer a slug from a marketing label.
- Retrieve API credentials through the configured credential store, never by printing secrets or committing them.
- Inspect the existing page with `read_file` and `search_files` before changing image/video references.
- Have `ffprobe` available for media verification. Use `ffmpeg` only for an explicit, reviewable transcode or fallback conversion.
- For local video browser QA, use the `headless-screenshot-qa` workflow or a static server that supports byte-range requests.

## How to Run

1. Identify the target routes, current media slots, aspect ratios, and public asset directory.
2. Verify the provider model and create-task schema from its official documentation.
3. Choose the composition mode before generation: default to text-free photographic layers for deterministic layout, or use an exact copy/brand whitelist when the user explicitly requests a native final composite.
4. Poll or receive callbacks, then parse the provider’s documented result field exactly.
5. Download outputs into a non-public staging directory first.
6. Validate dimensions, duration, streams, codecs, file size, and visual quality.
7. Convert/compress for web delivery only after validation; preserve an original when practical.
8. Integrate with a poster and at least one browser-compatible video fallback.
9. Run desktop/mobile Playwright checks, inspect screenshots with `vision_analyze`, and run the project’s relevant tests.
10. Remove task manifests and temporary provider URLs from the public asset directory; leave production untouched until explicit approval.

For authenticated Google Flow generation, reference-media upload, state verification, native export, watermark cleanup, and two-clip continuity, follow `references/google-flow-browser-generation.md`.

For GPT Image 2 identity references plus Nous Portal FLUX 3 keyframe UGC, follow `references/nous-flux3-ugc-keyframes.md`.

## Quick Reference

### Kie.ai Grok 1.5 Preview

- Image generation: `grok-imagine/text-to-image`.
- Image-to-video: `grok-imagine-video-1-5-preview`.
- Create: `POST https://api.kie.ai/api/v1/jobs/createTask`.
- Market polling: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>`.
- Verified video input shape: `image_urls`, `prompt`, `aspect_ratio`, `resolution`, `duration`.
- Working web preset: `9:16`, `480p`, `6` seconds. Provider output may still be approximately `400×736`; verify rather than assuming.

### Result parsing

```python
status = get_json(task_detail_url)
result = json.loads(status["data"]["resultJson"])
asset_url = result["resultUrls"][0]
```

Do not recursively collect every URL in a task response. Input URLs are often present in `data.param`; a generic URL walker can download the source image and mistake it for the generated video.

### HTML fallback pattern

```html
<video autoplay loop muted playsinline preload="metadata"
       poster="/assets/media/grok/grok-beauty.webp">
  <source src="/assets/media/grok/grok-beauty.webm" type="video/webm">
  <source src="/assets/media/grok/grok-beauty.mp4" type="video/mp4">
  <img src="/assets/media/grok/grok-beauty.webp" alt="Campagne beauté éditoriale">
</video>
```

Use the same `width`, `height`, and `object-fit: cover` rules for `img` and `video`. Keep the poster as a valid first-paint and unsupported-video fallback.

## UGC testimonial guardrails

Resolve the requested camera grammar before writing prompts. “A woman walking, holding the phone at arm’s length and talking” means a **visible-device walking testimonial** by default: a third-person shot sees the woman walking with the smartphone visibly extended in her hand while she talks toward it. A **direct front-camera selfie POV** is different: the viewer sees her directly and the phone body is off-screen; use it only when the brief explicitly asks for front-camera POV, “selfie face caméra”, or no visible phone.

Never mix these grammars between the keyframe and I2V prompt. A phone-in-hand reference combined with “the viewer sees the phone camera view” or “never show the phone” can make Grok jump from a phone-in-hand shot to direct face-camera footage. For the visible-device mode, require the same third-person camera position, visible phone, natural walking rhythm, one continuous take, no second phone, and no phone-within-phone composition. For POV mode, explicitly forbid the device in both prompts. Validate the keyframe before spending credits on I2V. See `references/ugc-walking-testimonial.md` for the camera-grammar and temporal-QA checklist, and `references/kie-grok-1-5-preview.md` for the provider-specific guardrail.

## Procedure

### 1. Inspect the existing surface

Read the landing HTML and shared CSS. Locate every current `<img>`, `<video>`, CSS `url(...)`, and responsive rule. Preserve the existing semantic `alt` text and route behavior. Determine whether the hero uses fixed portrait frames, a gallery card, a background image, or a real content video.

### 2. Plan a coherent asset batch

Choose a small number of roles rather than unrelated prompts: for example, beauty close-up, fashion product, and food/social action. Match the page’s visual language, composition, and aspect ratio. In deterministic-copy mode, prompt the model to avoid generated typography, fake logos, watermarks, and text. In native-final-composite mode, provide the exact approved copy and brand whitelist, forbid every legacy or unrelated brand/text element, and plan full-resolution line-by-line QA. When the brief says **no CTA, logo, or writing**, treat that as a full-pipeline constraint: do not reserve CTA space, do not add typography or branding in post-production, and classify a visible provider watermark as a logo that must be removed and re-verified. If exact product fidelity matters, use image-to-image with the real product reference instead of text-to-image.

For multi-brand static ads derived from a live client thread, first normalize image and voice-note evidence, classify each material decision as locked/tentative/superseded, and resolve logos by verified brand entity rather than acronym search. Then choose the composition mode explicitly: deterministic copy is the default, while native model-rendered logos and typography are valid when the user requests that integrated look. QA both the set and every full-resolution export, treat “redo the whole thing” as a fresh composition rather than a cosmetic edit, and keep external delivery behind approval of the exact batch. Follow `references/branded-static-ad-production.md` for the complete workflow, revision semantics, and delivery boundary.

### 2b. Prepare a supplied brand asset deterministically

When the user provides an approved raster logo and asks for it to be integrated, treat the image as the source of truth rather than as a prompt for a new generative logo. Load it with vision first, inspect its dimensions and useful regions, derive a background mask, and create purpose-specific transparent assets: full lockup, symbol/mark, wordmark, horizontal lockup, and favicon. Preserve the original pixels, proportions, brand colors, character glyphs, and decorative rules; avoid AI regeneration when text or Chinese characters must remain exact.

Use a pixel-derived tight bounding box with intentional padding, then visually inspect every crop. Pay particular attention to bleed from adjacent regions (for example, the bottom of an icon leaking into a wordmark crop). If the layout needs a horizontal lockup that the master does not provide, recompose it from the exact approved mark and wordmark crops instead of redrawing the logo. Integrate the target-specific asset where it belongs: horizontal lockup in a desktop brand rail, mark on compact/mobile surfaces, and a square mark for the favicon. Keep `alt` text meaningful and verify the actual public asset URLs after deployment. Follow `references/supplied-brand-asset-prep.md` for the deterministic crop, transparency, recomposition, and QA recipe.

### 2c. Lock the source → target language contract

Treat a correction such as **English → Mandarin** as a product contract, not as a cosmetic label change. Update learner-facing copy, translations/meanings, prompts, search affordances, metadata, and automated selectors consistently; make the pair explicit in the product UI. Do not infer the source language from the operator’s conversation language, and rerun the live interaction smoke test after changing the contract.

### 3. Verify the provider contract

Use `web_search` or `web_extract` for current official docs when the model slug or field names are uncertain. Record the exact model ID, create endpoint, input keys, task-detail endpoint, result field, duration/resolution enums, and URL retention behavior in a reference file if the workflow is likely to recur.

For Kie Market models, prefer `recordInfo` when `getTaskDetail` is not the documented endpoint. If the image task returns a public temporary result URL, feed it directly into the video task. If a file-upload endpoint returns Cloudflare `403 Error 1010 browser_signature_banned`, stop retrying that same route; use the already-public provider result URL or an explicitly approved public storage path.

### 4. Generate and poll asynchronously

Submit independent image tasks as a batch where possible. Poll each task with a bounded timeout and retain the task ID for diagnosis. Treat `state: success` as a prerequisite, not proof that the downloaded file is the requested modality. Parse the documented nested result JSON before downloading.

### 5. Validate media before integration

Use `ffprobe` on every video. Require a non-zero video stream, dimensions, and a real duration; a one-frame file or an image URL saved with an `.mp4` suffix is invalid. Check that the expected aspect ratio is close enough for the page. For a mismatch, prefer CSS framing with `object-fit: cover` or ask for review before destructive cropping.

Inspect generated stills and representative video frames with `vision_analyze`. Reject visible text, logos, watermarks, broken anatomy, malformed product geometry, or a composition that clashes with the page. Do not claim that a provider output is good merely because its API task succeeded.

### 6. Prepare browser delivery

For web video, retain a widely supported MP4/H.264 version and generate a WebM/VP9 fallback when the target browser matrix includes Chromium builds without H.264 decoding. Keep the poster image. Use `autoplay`, `muted`, `loop`, and `playsinline`; do not add audio to decorative loops unless the user explicitly requests it. Avoid loading multiple huge duplicates of the same video above the fold.

### 7. Integrate narrowly

Edit existing HTML with `patch`, not a wholesale rewrite. Add shared CSS selectors for `img` and `video`, and keep source order/alt fallback valid. Do not expose provider manifests, task IDs, presigned URLs, API keys, or temporary source URLs under the public asset directory. Keep generated assets reasonably small and report their actual sizes.

### 8. Verify the real landing

Use the project’s prescribed test command. Run a Playwright matrix at desktop and mobile widths and assert:

- no horizontal overflow;
- no console/page errors;
- all generated images have non-zero natural dimensions;
- videos reach `readyState >= 2` and have a duration above the intended threshold;
- posters and fallbacks resolve;
- no unrelated route contract regresses.

Use `vision_analyze` on the hero, mobile page, and gallery slices. If headless Chromium cannot decode H.264, distinguish codec support from a page error by checking `canPlayType`; test the WebM fallback or validate the MP4 with `ffprobe` rather than adding a misleading application workaround.

## Complete video-ad review addendum

### Operation identity gate

QA is not generation. Before opening the nearest local MP4, map the user’s request to the exact campaign brief, user-facing video number/variant, provider task or project, and current state. If the user says “launch/attack video 2”, do not substitute an audit of `clip_b` or “second half” merely because that file exists; first locate or recover the requested generation. If you only inspected an existing artifact, report that plainly and do not imply that a new video was launched. For the reusable classification/resume checklist, see `reference-to-video-ugc/references/task-intent-and-artifact-resume.md`.

For a finished ad, do not stop at a successful transcode or a model's generic scene description. Run a two-layer review: (1) `ffprobe`/FFmpeg for streams, duration, frame count, black/freeze detection, scene cuts, and loudness; (2) visual QA over the full timeline with an AI video-capable model plus contact sheets and high-resolution end-card crops. Compare original and edited bottom-right crops at several moving-background timestamps to verify watermark removal rather than trusting a single frame. Treat fixed provider watermarks, scene-generated logos, and campaign/legal text as separate classes.

Add a third, subjective audio release gate for any ad with narration or music: audition the encoded master at the opening, under speech, in pauses, and at the ending. ASR, LUFS, true peak, and silence metrics cannot detect a hollow phase-cancelled bed or narration that feels rushed. If the bed comes from center cancellation, replace it with a clean source or remove it; if the voice is too fast, shorten/regenerate the narration and retime picture/subtitles instead of stacking more time compression. Follow `video-postproduction/references/short-form-ad-audio-revision.md` for the correction and exact-duration checks.

Always inspect the final 1–3 seconds independently: generated typography may be visually clean yet contain nonsense, wrong brand names, or unverified certification claims. Transcribe only legible text with uncertainty markers, verify the requested brand is actually present, and reject the asset when the end-card is unreadable, legally ambiguous, or too brief to scan. If a model is instructed to return JSON but wraps it in Markdown fences, strip the fence only after saving the raw response, then parse and validate the normalized JSON; never report a prose-only model result as structured fact.

After every detected hard cut, inspect the first 0.20–0.25 seconds at native frame cadence (24/25/30 fps), not only a 0.5-second contact sheet. AI-generated edits can contain a short morphing or malformed hand/body transition immediately after the cut; scene-level sampling may classify the surrounding shot as coherent and miss the defective opening frames. When found, trim through the first stable frame and re-check audio/video sync.

See `references/complete-video-ad-review.md` for the reusable checklist and evidence pattern.

## Pitfalls

- **Ambiguous brand asset:** acronym or filename search can return a polished logo for the wrong organization. Resolve the brand entity first, use its official asset or Wikidata `P154`, then verify the rendered pixels.
- **Invisible fine print:** text can fit the DOM yet disappear against a pale photographic region. Inspect a full-resolution crop, fix contrast, and re-render.
- **Wrong result URL:** a recursive URL parser selects the input `image_urls` instead of `data.resultJson.resultUrls[0]`. Parse the nested field exactly.
- **Success with one frame:** Kie can return a successful task whose selected URL is an image. Require real duration and a video stream with `ffprobe`.
- **Repeated blocked upload:** Cloudflare browser-signature bans are not fixed by retrying the same endpoint. Reuse a public provider result URL or use approved storage.
- **Codec-only QA failure:** a headless runner may lack H.264/AAC decoding while production browsers support it. Provide WebM for Chromium and keep MP4 for Safari/iOS.
- **Silent ratio distortion:** provider output can be near, but not exactly, the requested ratio. Do not silently crop; use a CSS frame or obtain review.
- **Public staging leakage:** task manifests and temporary URLs expire or expose provider internals. Keep them outside the page’s public directory.
- **Asset bloat:** generating at 2K/4K for a web hero can dominate page weight. Verify file sizes and compress only after visual review.
- **Overwriting the page:** large HTML rewrites risk destroying unrelated work. Read, patch narrowly, then run `git diff --check`.
- **Skipping visual review:** a green API response is not a green creative. Inspect actual pixels and the integrated page.

## Verification

A successful run ends with real evidence, not a prose-only claim:

- provider task IDs and exact result URLs recorded privately during the run;
- `ffprobe` output proving duration, streams, dimensions, and codecs;
- generated images opened and visually inspected;
- Playwright desktop/mobile report with overflow, console, page-error, and media readiness checks;
- relevant project tests executed, with unrelated failures named honestly;
- `git diff --check` clean for the edited files;
- production deployment still pending explicit user approval.

Detailed Kie-specific response examples, the observed 6.04-second/400×736 behavior, and the 9.6-credit empirical cost are in `references/kie-grok-1-5-preview.md`.
