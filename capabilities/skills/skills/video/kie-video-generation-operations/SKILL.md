---
name: kie-video-generation-operations
description: "Verified operational workflow for Kie.ai video generation: live model contracts, paid-task submission, polling, download, cost accounting, media QA, and product-fidelity safeguards. Also covers: kie video generation."
version: 1.1.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [video, generation, kie, qa, polling, pricing, grok, seedance]
---

For the native OpenRouter video-generation route and MiniMax H3, read `references/openrouter-video-generation-h3.md`.

# Kie.ai Video Generation Operations

Use this skill whenever a Kie.ai video generation task must be submitted, polled, downloaded, cost-checked, or quality-verified. It complements provider-specific generation skills and exists to prevent stale model IDs, mismatched payload fields, and false success claims.

## Operating rule: verify the live contract first

Kie.ai exposes several generations of Market models behind a similar task endpoint. Do not infer a model ID or field names from an older skill, a friendly UI label, or a different Kie model family.

1. Inspect the current official Kie model page or current model-specific documentation.
2. Record the exact model ID, endpoint, input field names, duration type/range, aspect-ratio field, resolution options, and audio behavior.
3. If the user names a model version, never silently substitute a generic or legacy model.
4. For a paid request, check the credit balance before submission.
5. Submit exactly one bounded test unless the user explicitly requests variants.

The current Grok 1.5 contract and a reproducible verification recipe live in `references/kie-grok-imagine-video-1-5-live.md`.

## Current Grok Imagine Video 1.5 Preview contract

For a user request that explicitly says **Grok Imagine Video 1.5** on Kie.ai, the live model ID re-verified against the official model page on 2026-07-28 is:

```text
grok-imagine-video-1-5-preview
```

Creation endpoint:

```text
POST https://api.kie.ai/api/v1/jobs/createTask
```

Verified T2V shape:

```json
{
  "model": "grok-imagine-video-1-5-preview",
  "input": {
    "prompt": "A single flowing visual description...",
    "mode": "normal",
    "duration": 15,
    "resolution": "720p",
    "aspect_ratio": "9:16"
  }
}
```

The current official page exposes required `prompt`, `mode` (`normal` or `fun`), and integer `duration` from 1–15 seconds; `resolution`, `aspect_ratio`, and `image_urls` are optional. It allows up to seven reference images and describes native synchronized audio. With exactly one `image_urls` item, omit `aspect_ratio` unless the current page explicitly says the combination is valid, because the source image governs the canvas. Treat older `nsfw_checker` examples as route-specific and do not send that field without current documentation. Likewise, do not substitute generic fields such as `aspect`, `aspectRatio`, or `seconds`.

## Prompt construction for Grok video

Grok performs better with one continuous visual description than with a numbered storyboard for a simple UGC scene.

- Describe what the viewer sees: people, actions, materials, light, environment, expressions, and physical motion.
- Avoid cinematography jargon and camera-parameter instructions.
- A spoken dialogue can be included verbatim when native audio is desired; keep visual instructions separate and concrete.
- If overlays are added later, explicitly prohibit generated subtitles, logos, badges, watermarks, flags, readable text, and UI elements.
- Reserve a clean area in the composition for later subtitles or branding.
- Do not ask text-to-video to reproduce an exact product design. Use image-to-video with a real product/keyframe reference when product fidelity matters.

For a premium multi-shot commercial, do **not** force a numbered storyboard, exact typography, product fidelity, and several visual roles into one long generation. Submit bounded text-free shots, inspect each one, retry only the failed shot, and assemble exact copy/branding deterministically afterward. Simple camera-movement phrases are valid when they describe one continuous shot; avoid competing choreography rather than avoiding camera language entirely. See `references/grok-1-5-multishot-commercial-workflow.md`.

## Paid-task workflow

### 1. Check credits without exposing the secret

Use the `vault-lookup` skill to retrieve the Kie credential in memory. Pass it directly to the HTTP client and never print it, interpolate it into a logged shell command, write it to a file, or include it in a report. Query the Kie credit endpoint and record only the numeric balance and HTTP status.

For a paid test, save the numeric balance before the task.

### 2. Create the task

Use an in-memory HTTP client against `/api/v1/jobs/createTask`. Capture only HTTP status, `code`, `msg`, `taskId`, and `recordId` in the agent transcript. Do not print the API key or dump unnecessary payloads.

### 3. Poll the task

Use the Market endpoint:

```text
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>
```

Handle `waiting`/`queue` as non-terminal, then stop on `success` or `failed`. Poll at a restrained interval (roughly 60 seconds for video) rather than hammering the API. A successful create response is not a completed generation.

### 4. Parse and download immediately

Successful responses may expose the result in `data.resultJson` as JSON text or an object. Prefer `resultUrls[0]`; support `result_url`, `resultUrl`, or `output` as fallbacks. Download the MP4 immediately because temporary result URLs can expire.

**Download pitfall:** Kie result URLs on `tempfile.aiquickdraw.com` can return HTTP 403 to Python `urllib.request.urlretrieve()` even when the URL is live. Confirm with `curl -I`, then download with `curl -fsSL "$URL" -o output.mp4` (or a browser-like HTTP client) before treating the result as expired or regenerating.

### 5. Verify actual output

Run `ffprobe` against the downloaded file and inspect at least:

- duration;
- width and height / requested vertical ratio;
- video codec and frame rate;
- audio codec, sample rate, and channel count;
- file size.

Use `volumedetect` or an equivalent audio check to ensure the native audio track is present and not silent. Extract beginning, middle, and final frames and inspect them visually for generated text, unwanted watermarks, anatomy defects, product hallucination, scene coherence, and available overlay space.

Only after these checks may the result be reported as generated and delivered.

## Live pricing catalog discovery (Kie.ai)

Before comparing or quoting video prices, query Kie.ai's public pricing catalog rather than relying on a cached skill table or a model landing page:

```text
POST https://api.kie.ai/client/v1/model-pricing/page
```

Use a browser-shaped `User-Agent`, JSON body `{"pageNum": 1, "pageSize": 100, "modelDescription": "", "interfaceType": "Video"}`, and paginate through `data.pages` (the API rejects `pageSize > 100`). The endpoint does not require the generation credential. Filter the complete result set by `modelDescription` and `provider`, then retain `creditPrice`, `creditUnit`, `usdPrice`, `falPrice`, `discountRate`, and `anchor` as evidence.

For a comparison, preserve the billing semantics returned by Kie: distinguish `per second`, `per video`, and `per image`; distinguish resolution and `no video input`/`with video input`; and only normalize to a clip total when the duration is explicitly present or the rate is genuinely per-second. Report both credits and Kie's displayed USD price. Do not compare a 2K H3 rate to a 720p rate without stating the resolution mismatch. The reproducible request and the 2026-07-31 snapshot are documented in `references/kie-live-pricing-catalog.md`.

## Adapter / LoRA capability verification for H3

Do not infer LoRA support from the phrase **open weights**, from a `reference-to-video` route, or from a provider accepting reference images. These are different capabilities:

- **Reference conditioning**: the provider uses supplied images/video/audio at inference time; it does not load a user-trained adapter.
- **LoRA / adapter inference**: the request must explicitly expose an adapter/LoRA identifier or URL, a scale/weight, and a documented compatible model or adapter-training workflow.
- **Fine-tuning**: training an adapter is a separate service and does not imply that the generation endpoint can consume it.

For MiniMax H3, inspect the provider-specific schema before recommending a LoRA workflow. The Kie H3 text-to-video, image-to-video, and reference-to-video contracts expose prompt, frames, `reference_image_urls`, `reference_video_urls`, `reference_audio_urls`, duration, resolution, and aspect ratio, but no documented `lora`, `adapter`, fine-tuning, or adapter-weight fields. OpenRouter's H3 video catalog exposes `input_references` and the listed passthrough parameters, but no LoRA/adapter injection field. Therefore classify H3 LoRA support on these hosted routes as **not exposed / unverified**, not as supported; never invent a `lora_url` field or silently substitute a different Hailuo model.

If LoRA is a hard requirement, use a self-hosted or GPU endpoint that explicitly supports the published H3 weights plus PEFT/LoRA loading, and verify the adapter format, target modules, VRAM/runtime, and licensing separately. For the session-specific field inventory and official URLs, see `references/h3-lora-provider-compatibility.md`.

## Cost accounting

Model price tables are mutable. Check the balance after the task and calculate `before - after`. The live Grok 1.5 page indicated approximately 1.6 credits/second at 480p and 3 credits/second at 720p; a 15-second 720p verification consumed 45 credits. Treat the observed delta as authoritative for the current account and route.

## Upload egress and paid-task boundary

A successful credential check against `api.kie.ai` does not prove that the binary upload edge is reachable from the current network. If the main API accepts an authenticated harmless probe but `POST https://kieai.redpandaai.co/api/file-stream-upload` returns `HTTP 403` with edge error `1010`, keep the official endpoint and diagnose egress before rotating credentials or changing payload fields. A validated workaround for an Oracle-hosted agent is a temporary SSH SOCKS5 tunnel through an authorized Mac: set `KIE_SOCKS_PROXY=socks5h://127.0.0.1:<port>` (or `KIE_HTTP_PROXY`) and use a multipart client with SOCKS support such as `requests[socks]`; keep the Kie key in the Linux vault/profile environment and never copy it to the Mac. The wrapper must wait for the proxy, run the provider command, and clean up the tunnel after the command; do not use `exec` if the shell's exit trap owns cleanup. Record the upload receipt separately from the generation task.

Treat asset upload and paid video submission as two gates. Verify upload with `HTTP 200`/provider `code=200`, then stop unless the approved workflow state and the user's current instruction authorize `createTask`; an upload success must never be reported as a generated video.

See `references/kie-upload-egress.md` for the reproducible diagnostic and wrapper pattern.

## Failure handling

- `HTTP 200` on task creation means accepted, not finished.
- If the response is successful but has no obvious result URL, inspect `resultJson` before declaring failure.
- If a model ID or field is rejected, re-check the current model page and correct the contract; do not silently fall back to another model.
- If a visual output is plausible but the product is generic, classify it as a style test, not a product-faithful ad.
- If the audio exists but its exact language/dialogue has not been transcribed, report only that the track is present/non-silent and leave semantic audio validation explicit.

## Related references

- `references/kie-grok-imagine-video-1-5-live.md` — live model contract, payload, polling, cost and QA evidence.
- `references/grok-1-5-multishot-commercial-workflow.md` — forensic reference analysis, bounded shot generation, deterministic typography/audio, retry strategy, concat normalization, and release QA for short vertical ads.
- `references/grok-i2v-release-qa.md` — reference-driven Grok 1.5 I2V: public asset upload, exact payload, credit measurement, restrained polling, preview-stream removal, duration normalization, and storyboard QA.

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **kie-video-generation** — The full Kie.ai video API reference: endpoints (legacy and Market), every supported model (Seedance 2.0 / Fast, Kling, Hailuo, Wan, Sora2, Grok Imagine), payload formats, pricing comparisons, and the Kie chat-model notes. Read it for a model or payload this procedure does not cover.
  Read `references/merged-kie-video-generation/kie-video-generation.md` (+ 12 supporting files in that folder).
