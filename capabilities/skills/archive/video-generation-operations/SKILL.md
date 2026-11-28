---
name: video-generation-operations
description: Use for AI video generation, workers, and media QA.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [video, generation, workers, references, models, media-qa]
---

# Video Generation Operations

Use this class-level skill for AI video generation, reference-driven shots, provider workers, model selection, self-hosting decisions, and media quality assurance. Treat generation, orchestration, storage, rendering, and review as separate stages with explicit artifacts.

## Always-on rules

- Resolve the exact provider/model, input modality, duration, aspect ratio, resolution, audio, reference assets, and output contract before launching a billable job.
- Keep provider authentication and job state in the approved secret/config path; never print tokens or assume a model label proves the backend.
- Use a durable job record with correlation ID, idempotent state transitions, bounded polling/callback handling, and explicit failure/timeout states.
- Preserve source/reference assets and generated outputs with hashes or stable IDs; a successful submission is not a usable video.
- Independently inspect the result for file integrity, duration, frame rate, visual continuity, audio, text/face consistency, and the requested scene/action.
- Report provider failure, incomplete artifact, and quality failure separately; do not rerun a failed job as if it were a completed comparison.

## Reference-driven generation

- Build a shot brief with subject identity, environment, camera, motion, lighting, timing, continuity anchors, and negative constraints.
- Validate reference assets before submission and preserve the exact asset-to-shot mapping.
- Keep identity, composition, motion, and style controls distinct so a change in one does not silently alter the others.
- For multi-shot work, define continuity invariants and inspect transitions rather than judging isolated still frames.

## Provider and worker orchestration

1. Verify model availability and exact API schema from the live provider contract.
2. Submit through the intended worker/provider and record the returned job identity without exposing credentials.
3. Poll or receive callbacks with bounded retries, signature/replay checks where applicable, and monotonic idempotent state updates.
4. Download the actual artifact, verify size/type/duration, and preserve metadata.
5. Run content and visual QA before delivery; only then mark the job complete.

Keep provider-specific payload builders behind adapters. Do not mix direct API, CLI, and browser-worker timings or infer model quality from a provider-aborted run.

## Model and self-hosting economics

Compare hosted and self-hosted paths using current prices, GPU memory/throughput, queue time, storage/egress, engineering, monitoring, and failure cost. Include setup, idle, and retry costs; a lower per-second inference price is not automatically lower total cost.

Choose self-hosting only when control, privacy, volume, latency, or repeatability pays for provisioning and operations. Validate an actual short generation on the selected GPU/model before committing to a larger deployment.

## Media QA

- Verify the artifact decodes and matches the requested container, codec, dimensions, frame rate, duration, and audio contract.
- Inspect representative frames plus the full timeline for temporal artifacts, identity drift, object morphing, camera discontinuity, incorrect text, and missing actions.
- Listen to audio for sync, clipping, silence, artifacts, and language/content correctness.
- For landing or advertising media, verify crop-safe composition, legibility at target sizes, loop/hero behavior, load budget, and fallback behavior.
- For reference-analysis workflows, cite timestamps and observations and keep extracted evidence separate from creative recommendations.

## Verification

A deliverable is complete only when the exact job route is known, the output is physically present and decodable, required visual/audio checks were run, and the final delivery path was read back. Report all unverified dimensions.
