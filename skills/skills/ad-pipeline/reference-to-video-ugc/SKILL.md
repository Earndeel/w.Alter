---
name: reference-to-video-ugc
description: Convert an approved reference image into walking UGC video.
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux]
metadata:
  hermes:
    category: ad-pipeline
    tags: [ugc, image-to-video, kie, grok, google-flow, omni, reference, video]
    related_skills: [kie-video-generation, kie-image-generation-operations, multi-provider-image-gen]
---

# Reference-to-Video UGC Skill

Convert an approved still image into a believable walking-and-talking UGC video while preserving the subject, wardrobe, location, and visual identity. This skill covers generation, provider upload, asynchronous recovery, frame-level QA, and media delivery; it does not deploy the result or replace a production asset without explicit approval.

## Intent gate: generation request versus artifact QA

Generation, resuming a provider task, and auditing an already-downloaded clip are separate operations. Before touching an existing MP4 or spending credits, resolve the user-facing target rather than inferring it from the nearest filename:

1. Classify the verb and object. “Générer/lancer/attaquer la vidéo 2” means start or recover the specific second requested video; “vérifier/auditer/contrôler le clip B” means inspect an existing artifact. “Continuer” does not authorize silently converting a generation request into QA.
2. Identify the exact asset identity: project/brief, user-facing video number or variant, provider, task ID, prompt, and current status. Treat names such as `clip_b.mp4`, “second half,” and “video 2” as different labels until the brief proves they refer to the same item.
3. Check existing task/project state only to confirm whether the requested video is already generated, queued, or absent. Do not report “video 2 attacked” when you merely inspected a similarly named file; state the actual operation performed.
4. Before any paid submission, give one concise action statement naming the target and whether this is a new generation, task recovery, or QA. If the user’s label cannot be mapped unambiguously to a brief or task, ask one focused clarification before spending credits.
5. After a prior asset review, “continue with the second video” means locate the next user-requested asset from the brief/session state, not automatically open the closest existing output. Preserve the original asset and task ID; never submit a duplicate merely because an old export is present.

See `references/task-intent-and-artifact-resume.md` for the reusable classification and resume checklist.

## When to Use

- An approved portrait or street selfie must become a short testimonial video.
- A user wants the subject to walk, speak, gesture, or react while preserving a reference image.
- A generated result needs objective checks for identity drift, device-in-device framing, bokeh, text artifacts, or actual output quality.
- A provider task or CDN download fails transiently and the original task must be recovered without paying twice.

## Prerequisites

- A clearly adult reference image with a known local path and an intended composition.
- A provider credential stored in the vault; for Kie use `vault get kie/api_key` without printing the key.
- `ffmpeg`/`ffprobe` for frame extraction, stream cleanup, and media inspection.
- A public reference upload accepted by the chosen provider. Prefer the provider’s documented file-upload endpoint; use a temporary third-party upload only when the provider requires it and the image is safe to expose.
- User approval before modifying HTML, replacing an existing asset, deploying Pages, or writing to R2/Workers.

## How to Run

Use the provider-specific skills for exact contracts, then follow this sequence:

1. Inspect and approve the still before animating it. Reject visible device-in-device framing, artificial bokeh, malformed hands, unreadable generated text, or identity defects.
2. Upload the still once and persist the returned public URL beside the task record.
3. Submit one image-to-video task with a saved task ID. Do not submit duplicates while the original is waiting.
4. Poll the documented task-detail endpoint with retry/backoff. On a network exception, resume the same task ID.
5. Download the completed output with retries. A closed CDN connection is a delivery problem, not evidence that the task failed.
6. Extract start, middle, late, and end frames. Only after visual QA, clean the container and create fallbacks.
7. Deliver the actual files with `MEDIA:` paths and report measured dimensions, duration, codecs, audio, and provider credits.

## Quick Reference

### Kie GPT Image 2 still

- Model: `gpt-image-2-text-to-image`.
- Required: `input.prompt`.
- Conservative Kie contract: `input.aspect_ratio: "auto"`; verify returned pixels rather than trusting the prompt or label.
- Keep the original PNG and create a WebP derivative when the image may become a video reference.

### Kie Grok I2V

- Model: `grok-imagine/image-to-video`.
- Input: `image_urls`, `prompt`, `mode: "normal"`, `duration: "6"`, `resolution: "720p"`, `aspect_ratio: "9:16"`.
- Poll: `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>`.
- Create: `POST https://api.kie.ai/api/v1/jobs/createTask`.

For the condensed Kie/Grok contract and recovery notes, see `references/kie-grok-reference-run.md`.

### Google Flow / Omni via authenticated browser

Use this path when the user explicitly wants Google Flow credits or Omni rather than a provider API. The browser session is part of the delivery path; do not treat a visible Flow card as an exported file.

1. Open or create the Flow project in the authenticated Camoufox session and verify the live account tier/credit balance before any paid action.
2. Import the approved reference through Flow’s UI. If the browser bridge has no filechooser operation, open the media dialog, target `input[type=file]` in page context, construct a `File` from the local bytes, assign it through `DataTransfer`, dispatch `change`, and verify the image appears in Flow’s collection and in the prompt. Never send session cookies to an external uploader just to avoid this step.
3. In `Paramètres`, verify the live model label (Omni may be displayed as `Omni Flash`), portrait `9:16`, and the requested duration. Put `exactly 10 seconds` in the prompt as well; the prompt is not a substitute for checking the generated media.
4. Treat the generation confirmation as authoritative for spend and count. In one verified run, selecting x2 still produced a confirmation for `cette vidéo (1)` at 15 credits. Do not assume x2 means two videos: read the dialog, accept one paid generation, then submit the second distinct variant only when the first request’s cost/count is understood. Record the displayed cost; it is dynamic.
5. Use one continuous UGC action per prompt, with identity anchors from the reference, a differentiated camera treatment for each variant, and explicit exclusions for subtitles, captions, watermarks, logos, device-in-device framing, extra people, and unverified product claims.
6. A message such as “scheduled … in the queue due to high demand” is an accepted queued state, not a failed generation. Persist the project URL and inspect the Flow collection before retrying. A client-side exception after submission also requires a project reload and collection check before resubmission; duplicate clicks can bill twice.
7. Export through the authenticated browser context or Flow’s native download. Direct `curl`/plain `requests` to `media.getMediaUrlRedirect` can return 401, and page-side `fetch` can be blocked by CORS even while the video element plays. Do not deliver a URL/card as a local file: download the actual MP4 and run `ffprobe` for duration, dimensions, codecs, audio, and size.

For the concrete Flow/Camoufox labels, failure transcripts, and export recovery notes, see `references/google-flow-omni-camoufox.md`.

### Prompt pattern

Describe one continuous visible action, not a storyboard or a list of shots:

> The same clearly adult woman from the reference walks naturally forward along the same real city sidewalk while speaking directly to the viewer in a relaxed UGC testimonial. She keeps one arm extended with the phone just outside the frame, makes one or two small conversational gestures, blinks and breathes, and her hair and clothing move gently with her steps. Storefronts, parked cars and pedestrians shift naturally behind her; keep the street readable and sharp. Preserve the exact face, hairstyle, earrings, clothing, bag, daylight and street. No bokeh, dreamy background blur, phone body, second device, cuts, captions, logos or watermark.

## Procedure

### 1. Define the visual contract

State what the viewer must see: a direct smartphone selfie, a woman walking forward, visible speaking and small gestures, a readable street, and no artificial lens blur. Do not leave `selfie` unexplained; it can be interpreted as a hand holding a phone that displays another person. If the phone body must be visible, say so deliberately; otherwise keep it outside the frame and allow only a natural forearm edge.

Preserve durable identity anchors from the still: face shape, hair arrangement, earrings, clothing, bag, skin texture, daylight direction, sidewalk, buildings, parked cars, and background sharpness. Keep the prompt as one flowing paragraph with physical action verbs.

### 2. Generate and inspect the still

For GPT Image 2 on Kie, use the exact text-to-image slug and documented fields only. Verify actual dimensions with an image reader. A vertical prompt does not guarantee a precise 9:16 canvas; treat the downloaded pixels as authoritative. Inspect the full image for face/anatomy, background focus, visible devices, readable signs, watermarks, and logos before using it as a reference.

### 3. Upload and submit I2V

Use the provider’s upload contract, save the returned URL, and submit exactly one task. Persist the provider, model, task ID, reference URL, prompt, requested resolution, and requested duration before polling. Do not overwrite the current production asset while the new result is under review.

### 4. Recover without duplicate billing

If polling returns `RemoteDisconnected`, HTTP 5xx, timeout, or another transient transport error, wait and query the same task ID again. If the collector exits, create a recovery script containing only the known task ID; never rerun the submission script blindly. If the output URL download closes the connection, retry the same URL with backoff. A task reaching `success` remains recoverable through the task-detail endpoint.

### 5. Clean and package the result

Use `ffprobe` to record the primary video stream, audio stream, dimensions, frame rate, duration, bitrate, and file size. Some provider MP4s include an attached MJPEG thumbnail as a second video stream; produce a clean MP4 by mapping only `0:v:0` and `0:a:0?`, then use `+faststart`. Encode a separate VP9 WebM fallback without audio when the page uses muted autoplay. Do not silently resize or crop a non-conforming result; report it or ask for approval.

## Pitfalls

- **Selfie ambiguity:** “selfie” alone can produce a phone-within-phone composition. Describe the direct front-camera view and explicitly exclude the phone body.
- **Transition artifact:** If the first second shows a hand holding a screen before switching to the direct view, reject it or trim only after confirming the remaining direct view is stable.
- **Bokeh drift:** Reference images or prompts that mention cinematic optics can make the street artificially blurry. Repeat `no bokeh`, `no shallow-focus blur`, and `keep the street readable`.
- **Model-label optimism:** `720p` is a request, not a measured result. Report `ffprobe` dimensions. One verified Grok run returned 720×1264 at 24 fps, not 720×1280.
- **Transient failures:** A polling or CDN failure is not a failed generation. Recover the task; do not spend credits on a duplicate.
- **Protected production path:** Generation and QA are separate from integration. Do not edit the landing, replace the old media, deploy Pages, or push remote changes without explicit approval.
- **Audio assumptions:** Confirm whether the MP4 contains AAC audio; a WebM fallback created with `-an` will not.

## Verification

A run is complete only when all of the following are true:

- The reference image was visually accepted before animation.
- The I2V task reached a terminal success state and the actual output was downloaded.
- Start, middle, late, and end frames preserve the subject and show coherent walking/speaking movement.
- No device-in-device opening, face/anatomy glitch, identity drift, artificial bokeh, generated text, logo, or watermark is visible.
- Clean MP4 and fallback WebM files exist with non-zero size.
- `ffprobe` values are recorded and reported; no requested resolution is presented as fact without pixel verification.
- Production files were left untouched until the user explicitly approves the preview.

Observed baseline for the Kie/Grok path: GPT Image 2 still at 941×1672; Grok I2V at 720×1264, 24 fps, 6.04 s, H.264/AAC MP4 plus VP9 WebM. These are measured examples, not guaranteed defaults.
