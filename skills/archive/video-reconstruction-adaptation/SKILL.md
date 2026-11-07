---
name: video-reconstruction-adaptation
description: Reconstruct reference videos with staged artifacts.
version: 0.1.0
author: Monsieur, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [video, reconstruction, adaptation, brand, ffmpeg, artifacts]
    related_skills: [multi-model-video-pipeline, video-analysis-pipeline]
---

# Video Reconstruction & Adaptation

Use this skill when a reference video must be reverse-engineered, adapted to a brand, planned across IMAGE/VIDEO/POST capabilities, and delivered through a staged Hermes profile. The source package or workflow manifest is the authority; this skill supplies the operating discipline around it, not a second orchestrator or a replacement for the package's stage skills.

## When to Use

- A reference video must be downloaded or materialized locally before analysis.
- A brand must be adapted using text, product facts, positioning, audience, guidelines, and visual references.
- A multi-stage video job needs durable artifacts, approval gates, resumability, and provider-agnostic model selection.
- An installation or upgrade must be verified without making paid image/video calls.

Don't use this as a substitute for a package's individual stage skill, provider-specific API skill, or a generic video editing request that has no reconstruction workflow.

## Prerequisites

- A dedicated Hermes profile and a project/job workspace outside the old profile's state.
- `ffmpeg` and `ffprobe` for probing, frame extraction, rendering, and structural validation.
- `yt-dlp` for public URLs and supported platforms.
- JSON Schema validation and the package's declared Python dependencies.
- A provider credential only when an actual paid IMAGE or VIDEO operation is requested.
- Authenticated Drive access when the source is a private Google Drive file.

For Python installs, use the Hermes/project environment rather than mutating a PEP 668-managed system interpreter. Keep secrets in the profile secret store or environment, never in artifacts or SKILL.md files.

## Canonical Workflow

Run the package's canonical stages exactly once in this order unless a persisted artifact proves that an earlier stage is already valid:

```text
SOURCE INTAKE → SOURCE FORENSICS → CREATIVE DNA → BRAND ADAPT
→ VIDEO PLAN → ASSET BUILD → [DEV PREGEN REVIEW]
→ VIDEO GENERATE → POST PROD → QA DELIVERY
```

The pre-generation review is a gate inside `ASSET BUILD`, not a tenth skill. In DEV, asset-build must emit the assets, prompts, generation specs, reference maps, and post strategy with `PENDING_APPROVAL`; video generation waits for explicit approval.

## Context Discipline

1. Read the workflow manifest first; it is the stage-to-skill index.
2. Load only the skill for the active stage.
3. Read only the upstream artifacts named by that stage's contract.
4. Pass artifact paths and compact JSON summaries, not the whole project tree, all schemas, all scripts, or the conversation history.
5. Treat runtime scripts as executable tools. Do not paste their source into the model context unless debugging requires a targeted excerpt.
6. After every stage, persist a schema-valid artifact and a content hash/fingerprint so the next stage can resume without conversational memory.

A healthy boot has a small skills index and no full stage skill bodies injected simultaneously.

## Source Materialization

1. Normalize the locator and classify it as local file, public URL, or Google Drive.
2. For a local file, verify existence, decodeability, duration, and a content hash.
3. For YouTube, TikTok, Instagram/Reels, and other supported public URLs, use `yt-dlp` to download the media to the job workspace.
4. For Google Drive, use the authenticated Drive adapter first, save the downloaded file locally, then run the same media validation. A Drive page, preview, or remote URL is not an analysis substitute.
5. Probe the local file with `ffprobe`; extract frames or use a native video-capable model according to the active forensics contract.
6. Record source locator, local path, media metadata, hashes, download method, and any access caveat in the source artifact.

Never claim that a source was analyzed when only its web page or URL was inspected.

### Shared Google Drive adapter and secret boundary

When the package is run inside an isolated profile, keep Google Drive authentication shared and outside the profile workspace unless the deployment explicitly requires a separate account. Invoke the shared adapter with its credential home (for the validated Hermes layout, `HERMES_HOME=/root/.hermes`), materialize the file into the per-job `source/` directory, and record only the Drive locator, local path, hash, and adapter status in artifacts. Never copy OAuth tokens or client secrets into the package, job workspace, or stage skills. Verify both authentication and one read-only Drive operation before using a private Drive source; a successful token check alone is not proof that file retrieval works.

For provider secrets, resolve the key from the vault/secret store into the isolated profile's secret-bearing environment with restrictive permissions (validated pattern: profile `.env`, `0600`, `KIE_API_KEY` sourced from `vault get kie/api_key`). Verify the binding by comparing in-process values or hashes without printing the secret. Do not place the value in job artifacts, prompts, reference maps, logs, or workspace files. A provider key being available does not authorize a paid generation call.

## Brand as Multimodal Adaptation Context

Build one structured brand context, not merely a directory listing. Include the relevant subset of:

- positioning, product, audience, instructions, product facts, and guidelines;
- logos, screenshots, UI, packaging, products, visual references, and existing ads;
- role, provenance, local path or URL, dimensions, and intended use for every image.

When an image helps the adaptation, bind it into the actual multimodal provider input or reference map. A filename, prompt mention, or placeholder path is not evidence that a model received the image. Keep brand context separate from the source forensic artifact so a changed guideline or reference invalidates downstream approval.

## VIDEO PLAN: IMAGE / VIDEO / POST

`VIDEO PLAN` is the production brain. For every reproducible element, choose `IMAGE`, `VIDEO`, `POST`, or a combination using the capabilities detected at planning time:

| Element | Preferred capability | Reason |
|---|---|---|
| Physically manipulated UI or printed logo | IMAGE + VIDEO | Materialize the visual, then preserve motion and interaction. |
| Human movement | VIDEO | Motion and temporal continuity are the hard part. |
| Environment change | IMAGE + VIDEO | Control the key visual, then animate the transition. |
| Dynamic subtitles or deterministic CTA | POST | Text timing and layout should remain exact. |
| Crop, zoom, color, mix, or simple transition | POST | Deterministic, cheap, and repeatable. |

Do not hardcode a vendor or model into the concept layer. Use the generic `VIDEO` capability, consult the current model registry and capability snapshot, then apply `VIDEO_MODEL_OVERRIDE` only for an explicit test. Record the selected provider/model, references, duration, cost estimate when available, and fallback rationale in the generation plan.

## Asset Build and PREGEN Fingerprint

Before approval, persist:

- target blueprint;
- relevant brand context;
- generation plan;
- materialized assets;
- prompts;
- reference maps and actual provider bindings;
- generation specs;
- post plan.

The review fingerprint must cover all of those inputs. Approval is valid only if the current fingerprint matches the approved fingerprint. If any input changes, return to `PENDING_APPROVAL`; never silently reuse an approval from a previous plan.

Generation receipts, provider task IDs, and downloaded candidates belong under the job's persisted state. A self-test must assert that no provider receipt exists when generation is intentionally skipped.

## Controlled First-Project Smoke Test

For a first real project, distinguish installation verification from a deliberately bounded media smoke test. Keep `CREATIVE_FACTORY_MODE=DEV`, set `QA_MODE=OFF` only for manual inspection, and allow at most the explicitly requested IMAGE materialization with a real provider input/reference binding. Persist the source forensics, Creative DNA, target blueprint, provider-ready prompts/specs, reference maps, storyboards/sheets, and post plan, then prepare `PENDING_APPROVAL` and stop. Do not call VIDEO GENERATE, POST PROD, or DELIVERY before human approval; a model registry lookup or video generation spec is not a provider submission.

The smoke handoff must prove `current_stage=PREGEN_REVIEW`, `video_generation_blocked=true`, `video_calls=0`, and no generated video candidate beyond the copied source. When no external brand pack is supplied, record that assumption explicitly instead of inventing target-brand facts. For the exact vault/Drive preflight and artifact checklist, see `references/creative-factory-smoke-test.md`.

## Structural migration guardrails

When evolving an existing video pipeline, treat persisted artifacts and paths as contracts. Keep one canonical copy of each functional stage skill, move executable runtime/config/schema code out of the job-data directory, and update imports, loaders, subprocess paths, documentation and tests before deleting the legacy tree.

Use a central artifact writer with this sequence: generate → schema validate → deterministic normalization only for explicit legacy aliases → validate again → hash → atomic persist. Require an explicit schema version; reject legacy artifacts by default and migrate only when the mapping is trivial and recorded.

For source forensics, let ffprobe/ffmpeg determine media facts, shot boundaries and chronological base sampling. Use a fixed base rate from the workflow contract, paginate contact sheets at a fixed maximum, preserve thumbnail aspect ratio, and put timestamp/frame labels in a separate band below each image. Mark contact sheets as analysis-only; generation consumers must select role-labelled, hashed individual references and must never take the last PNG or a composite board by default.

For remote delivery, reuse the canonical service adapter. Probe all required capabilities at job start, perform write → remote readback → RESULT write → RESULT readback → FINISHED write/readback, and persist FINISHED only after remote verification succeeds. A local deliverable is not a finished remote mission.

See `references/structural-migration-contracts.md` for the validated contract map, compatibility rules and test matrix.

## POST Capability Discovery

At job start, probe the installed FFmpeg rather than relying on a hardcoded capability list. Persist a `post_capabilities.json` snapshot containing the FFmpeg version, available filters, available encoders, and semantic capability checks used by planning.

Keep the POST capability extensible: trim, split, concat, insertion, scale, crop, pad, rotation, FPS conversion, interpolation, remapping, speed, audio assembly, dialogue, music, SFX, sync, loudness, EQ, compression, ducking, mixing, subtitles, ASS, overlays, compositing, alpha, masks, chromakey, PiP, transitions, fades, blur, denoise, LUTs, correction, grading, and other runtime-supported filters should remain reachable through the package's FFmpeg runner or advanced filtergraph path.

## QA Modes

- `QA_MODE=FULL`: run configured semantic QA and automatic repair after structural checks.
- `QA_MODE=OFF`: skip costly semantic QA and auto-repair for manual debugging.

In both modes, structural checks remain mandatory:

- required files exist;
- media decodes;
- duration is valid;
- hashes and fingerprints are coherent;
- provider output was actually downloaded before it is called a candidate;
- required artifacts validate against their schemas.

QA OFF never disables the DEV PREGEN gate.

## Dedicated Profile Isolation

Create a new profile with its own config, auth, skills, sessions, memory, state, and workspace. Keep exactly the package's nine functional stage skills. If Hermes needs a profile-level skill directory, link the package skill files into it rather than creating a second competing implementation. Do not clone the old video profile's `state.db`, projects, artifacts, or credentials merely for convenience.

The package root guide and integration manifest are documentation/index files, not additional functional skills. A deterministic test helper may live outside the runtime package, but it must never become the production orchestrator.

## Verification

Use a deterministic local fixture and no paid provider calls. The minimum acceptance sequence is:

1. Parse the workflow manifest and assert all nine stages and their order.
2. Materialize a local video and validate it with `ffprobe`.
3. Produce source-forensics metadata and a valid video plan.
4. Build generation specs with real reference-map bindings and a PREGEN fingerprint.
5. Exercise approval plus invalidation after mutating one fingerprint input.
6. Render a small POST output through the installed FFmpeg.
7. Assert no video/image provider receipt was created.
8. Re-open the job from persisted artifacts and assert the correct resume stage.
9. Run the same structural checks with `QA_MODE=OFF` and confirm semantic QA is skipped while structure remains enforced.

For the v1.2 integration evidence and artifact contract, see `references/creative-factory-v1.2-integration.md`. For the validated first-project smoke sequence (vault binding, shared Drive verification, six-frame forensics, one reference-bound IMAGE call, and a hard stop at PREGEN), see `references/creative-factory-smoke-test.md`.

## Pitfalls

- Loading all nine skills and every schema at boot defeats lazy context management.
- An URL classification result is not a downloaded source.
- A prompt containing a path is not a materialized asset or a bound reference.
- A provider-specific model name in `VIDEO PLAN` makes future model replacement needlessly expensive.
- An approval hash that omits brand inputs, reference maps, or post strategy is incomplete.
- QA OFF must not become "no validation".
- A successful provider submission is not a delivered candidate until the output is downloaded and decoded.
- Copying the previous profile's state makes resumability ambiguous and destroys the value of an isolated test profile.
