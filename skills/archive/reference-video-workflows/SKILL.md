---
name: reference-video-workflows
description: Use when generating or QA-checking reference video.
tags: [video, references, character, i2v, ugc, reconstruction, qa]
metadata:
  hermes:
    tags: [video, references, character, i2v, ugc, reconstruction, qa]
---

# Reference Video Workflows

Use this umbrella when references, character sheets, existing clips, or brand material must drive a video generation, adaptation, extension, or QA workflow. Keep reference conditioning, timeline frames, durable artifacts, and final media verification as separate contracts.

## Intent and spend gate

Classify the request as new generation, resume/status, review/audit, or edit/assembly before opening a provider. Resolve the project, user-facing variant, provider/model, task ID or project URL, local artifact, and measured state. Reuse a queued or completed task; never regenerate because a local poller failed or because a filename looks like “video 2”. State the spend and approval point before a paid action.

## Reference-to-video pipeline

Treat character sheets and environment boards as identity/design references, not timeline frames. Inventory identity anchors, create a clean cinematic anchor without labels, diagrams, typography, watermarks, extra people, or duplicate anatomy, inspect that anchor before spending video credits, then select the provider-native mode:

- Use reference-to-video for identity continuity through motion.
- Use first-frame I2V when exact opening composition is load-bearing.
- Do not combine mutually exclusive reference and first-frame fields without a current provider contract.

For multi-shot briefs, write timed visible actions and camera changes, preserve continuity anchors, and distinguish requested shot compositions from measured hard transitions. For extensions, preserve the original prompt and add a timed continuation from the final pose; move any old “final” audio instruction to the true end.

## Durable artifact discipline

Materialize source media locally, record metadata and hashes, probe with `ffprobe`, keep source/forensics/plan/assets/review/generation/post/QA artifacts in their stage roles, and use schema-versioned atomic writes. PREGEN approval must cover target, brand, prompts, references, generation specs, and post plan; any fingerprinted input change invalidates approval. An analysis contact sheet is evidence, not automatically a provider input.

## Technical and visual QA

Save the returned file before review. Verify measured width/height/SAR, FPS, frame count, duration, codecs, audio presence and decode. Use a full storyboard and, for extensions, a focused boundary storyboard. Inspect identity, clothing, environment, action cadence, shot variety, generated text/boards/logos/watermarks, anatomy, and audio; report `N shots = N−1 transitions` when relevant. Pad to an exact aspect ratio rather than stretching identity geometry.

## Delivery

Deliver only the verified local artifact with its native media marker. A provider card, thumbnail, URL, task state, or local candidate is not proof of a finished deliverable. Remote delivery requires exact write/readback evidence and must not be inferred from a local render.

Exact historical character, UGC, reference-conditioning, and reconstruction recipes are routed in `references/curator-reference-video-archive-routes.md`.
