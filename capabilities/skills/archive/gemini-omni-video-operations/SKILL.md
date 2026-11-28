---
name: gemini-omni-video-operations
description: Use for Gemini Omni video generation and extension.
tags: [gemini, omni, video, kie, extension, qa]
metadata:
  hermes:
    tags: [gemini, omni, video, kie, extension, qa]
---

# Gemini Omni Video Operations

Use this class-level workflow for Gemini Omni Flash generation and stateless extension through Kie.ai or a directly supported Google route.

## Current contract gate

Verify the current model ID and provider endpoint before each paid task. For Kie, the known task flow is `POST /api/v1/jobs/createTask` followed by `GET /api/v1/jobs/recordInfo?taskId=...`; do not use the legacy `getTaskDetail` path without live evidence. Preserve the exact duration, aspect ratio, resolution, input mode, and credit estimate from the current catalog.

## Extension semantics

Kie's `video_list` is contextual reference, not frame-perfect continuation. Google Flow's stateful Interactions API uses `previous_interaction_id`, which Kie REST does not expose. The `[# Sources <FIRST_FRAME>@Image1]` pattern with a last-frame image is a useful approximation, but the model can re-render facial detail, eyes, mouth, texture, or pose.

Design both prompts together: finish clip one in a stable neutral handoff, begin clip two on the supplied image without reframing, hold the pose briefly, and preserve identity, wardrobe, camera, lighting, background, voice, and eye line. Concatenate and inspect the raw junction before calling it seamless; crossfade or optical flow hides a cut but does not prove continuity.

## Safety and recovery

Input speech/audio can trigger a Google safety block in video-edit mode; use image conditioning when that is the intended safe path. Do not silently claim extension in regions where video editing is unavailable. Extract the last frame from a one-second tail, verify it is non-empty, persist clip one before downstream work, and reuse its task/artifact after extraction or upload failure rather than paying twice.

## QA

Verify terminal task state, returned URL, downloaded MP4, measured dimensions/FPS/duration/codecs/audio, full decode, and a visual review of both clips and their junction. Treat pricing tables as dated observations and keep provider comparisons separate from the generation result.

Exact historical Kie, FIRST_FRAME, pricing, and recovery recipes are routed in `references/curator-gemini-omni-archive-routes.md`.
