---
name: kie-provider-operations
description: Use for Kie.ai image, video, and LLM provider operations.
tags: [kie, provider, image, video, llm, api, qa]
metadata:
  hermes:
    tags: [kie, provider, image, video, llm, api, qa]
---

# Kie.ai Provider Operations

Use this umbrella for Kie.ai provider setup, image/video generation, media upload, tool-use, polling, cost checks, and artifact QA. Kie exposes several protocol and Market-model families behind similar URLs; verify the current contract instead of trusting a friendly label or an older recipe.

## Provider and credential rules

1. Resolve the credential from the configured secret source without printing it, because logs and transcripts must remain non-sensitive.
2. Verify the exact endpoint, model slug, request schema, and billing unit from the current provider catalog, because fields and model generations are not interchangeable.
3. Keep Claude/Anthropic Messages, GPT/OpenAI Responses, and Market media task contracts separate, because a successful request in one family does not validate another.
4. Preserve provider and task metadata with each artifact, because HTTP success alone does not prove the requested model ran.

## Image and media operations

For image generation/editing, upload local references once, reuse their public URLs, build one prompt per intended composition, poll each task independently, handle moderation as a distinct failure, and verify the downloaded artifact before delivery. The Kie file upload host differs from the generation API and uploaded files have limited retention; download anything that must persist.

Clarify ByteDance naming before acting: Seedance is the video family and Seedream is the image family. For Market models, use `recordInfo` polling; `getTaskDetail` is a legacy path that can return 404.

## Video operations

Inspect the live model contract, submit once, persist the task ID, poll the same ID until terminal state, parse the returned result JSON, download the raw file, and record credits/cost. Do not resubmit because a poller or local connection failed. Run `ffprobe`, full decode, audio checks, and visual storyboard QA; report measured dimensions, FPS, duration, audio, and model identity rather than provider labels.

For OpenRouter-native video references retained in the archive, use its dedicated video catalog and 202 responses/job IDs; do not substitute a chat model or infer clip cost from token SKUs alone.

## Verification

Separate catalog existence, local authentication, task completion, downloaded-file validity, and visual/product fidelity. Keep raw provider output separate from normalized deliverables. A task marked successful but missing the requested reference, duration, audio, or dimensions is not a successful delivery.

Exact historical provider, image, media-upload, and video recipes are routed in `references/curator-kie-archive-routes.md`.
