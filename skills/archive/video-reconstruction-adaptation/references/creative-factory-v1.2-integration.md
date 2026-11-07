# Creative Factory v1.2 Integration Notes

This reference records the validated integration pattern for a clean Hermes profile around a `video-agent-v1.2` package. It is deliberately provider- and machine-independent: substitute the active profile root for `$PROFILE_HOME` and the package root for `$PACKAGE_ROOT`.

## Package boundary

The package remains the authority for business logic and contains:

- nine stage skill documents;
- runtime helpers for fetching, media probing, video selection, provider calls, review, validation, and FFmpeg post-production;
- source, target, generation, review, and post schemas;
- defaults and a generic video model registry.

The Hermes integration adds only profile wiring and execution metadata:

- a workflow manifest mapping the nine stages to the nine package skills;
- profile configuration for lazy skill access, toolsets, IMAGE/VIDEO/POST capabilities, DEV/PROD, QA, and PREGEN review;
- a runtime-generated `post_capabilities.json` snapshot;
- a deterministic self-test outside the production runtime package.

Do not create a second orchestrator, merge the nine skills into one prompt, or add a second copy of the package runtime.

## Profile configuration contract

The profile should express these concepts, using the syntax supported by the installed Hermes version:

```yaml
skills:
  external_dirs:
    - $PROFILE_HOME/skills

creative_factory:
  mode: DEV                 # DEV or PROD
  qa_mode: FULL             # FULL or OFF
  workflow_manifest: $PACKAGE_ROOT/config/workflow.yaml
  image:
    capability: IMAGE
    preferred_intent: gpt-image-2
    require_reference_binding: true
  video:
    capability: VIDEO
    selection_mode: AUTO
    model_override_env: VIDEO_MODEL_OVERRIDE
    registry: $PACKAGE_ROOT/config/video_models.json
  post:
    capability: POST
    engine: ffmpeg
    probe_on_job_start: true
    capabilities_snapshot: $PROFILE_HOME/capabilities/post_capabilities.json
    allow_advanced_filtergraph: true
  pregen_review:
    integrated_in: asset-build
    required_in_dev: true
    invalidate_on_change: true
    fingerprint_inputs:
      - target_blueprint
      - brand_context
      - generation_plan
      - materialized_assets
      - prompts
      - reference_maps
      - generation_specs
      - post_plan
```

Keep disabled toolsets explicit and enable only what the stage workflow needs. The profile-level model/provider is independent from the concrete VIDEO registry entry.

## Skill loading contract

At boot, Hermes should see only the profile's compact skill index. The active stage then loads exactly one stage skill and reads only its declared upstream artifacts. Runtime scripts, schemas, and project history stay on disk until the active stage needs them.

The profile-level skill files may be hardlinked or otherwise linked to the package's nine source files. The important invariant is one authoritative content set and exactly nine active functional skills.

## Artifact layout

Use a per-job root such as `$PROFILE_HOME/workspace/jobs/<job_id>/work/`:

```text
source/
  source.json
  source_video.mp4
  metadata.json
forensics/
  source_forensics.json
  frames/
creative-dna/
  creative_dna.json
brand/
  brand_context.json
  references/
plan/
  video_plan.json
assets/
  asset_manifest.json
  materialized/
review/
  review.json
  fingerprint.json
generation/
  generation_specs.json
  receipts/
post/
  post_plan.json
  post_capabilities.json
  rendered/
qa/
  qa_report.json
```

Each stage writes a schema-valid artifact and its hash before the next stage starts. The resume resolver should select the last valid stage, not infer progress from chat messages or directory names alone.

## Source intake rules

- Local files are validated directly.
- Public YouTube, TikTok, Instagram/Reels, and other yt-dlp-supported URLs are downloaded with yt-dlp before analysis.
- Google Drive URLs are first passed through an authenticated Drive adapter; the resulting local file then follows the same validation path as every other source.
- `ffprobe` validates presence, decodability, duration, streams, and technical metadata.
- The analysis input is always the local media file plus its persisted metadata. A page, preview, or URL alone is never treated as the source video.

A source artifact should record the original locator, classification, local materialized path, download method, file hash, probe result, and any access caveat.

## Brand reference binding

The brand artifact should distinguish semantic context from media references. Every visual reference needs a role and provenance, for example:

```json
{
  "role": "product_packaging",
  "source": "brand/reference/packaging-front.png",
  "description": "front-facing package artwork",
  "provider_input": {
    "image_url": "<bound local-or-uploaded-reference>"
  }
}
```

The exact provider field varies by runtime. The invariant is that the final IMAGE/VIDEO generation spec contains a real provider input or an explicit reason why the reference is not used. A filename in a prompt is not a reference binding.

## PREGEN review invariant

`asset-build` emits `PENDING_APPROVAL` in DEV. The review record should contain:

- the current fingerprint;
- the artifact hashes used to compute it;
- prompts and negative prompts;
- materialized asset paths/hashes;
- reference maps and provider inputs;
- generation specs;
- post strategy;
- approval status and approver metadata.

On every later generation attempt, recompute the fingerprint. Any change to a listed input invalidates the approval and returns the job to `PENDING_APPROVAL`.

## IMAGE / VIDEO / POST planning

The plan should select the cheapest stable capability that preserves the required fidelity and control:

- use IMAGE to establish controlled composition, UI, product, logo, packaging, or environment state;
- use VIDEO for human movement, physical manipulation, and temporal continuity;
- use POST for deterministic captions, CTAs, crops, grading, timing, compositing, audio assembly, and other exact operations;
- combine them when a still asset provides control and VIDEO supplies motion.

Resolve the concrete VIDEO model only after reading the current registry and capability snapshot. `VIDEO_MODEL_OVERRIDE` is a test override, not a replacement for the generic capability layer.

## FFmpeg capability snapshot

Generate `post_capabilities.json` from the installed `ffmpeg` and `ffprobe` binaries at job or environment setup. Record:

- binary versions;
- complete discovered filter and encoder names;
- semantic checks for filters used by the current planner;
- required codec availability;
- probe timestamp and runtime metadata.

Keep an advanced filtergraph path available so newly installed FFmpeg features are not blocked by a stale semantic allowlist.

## Deterministic installation test

A no-provider self-test should:

1. parse the workflow manifest and assert the canonical nine-stage sequence;
2. create or use a tiny local fixture and materialize it into the job source directory;
3. run `ffprobe` and a deterministic frame/media probe;
4. create valid source, target, brand, plan, asset, review, generation, post, and QA artifacts;
5. verify reference-map binding fields without calling a provider;
6. prepare PREGEN approval, approve it, mutate one fingerprint input, and assert invalidation;
7. run a small FFmpeg post render and decode the result;
8. assert there are no provider task IDs, generation receipts, or downloaded candidates;
9. reload the job from disk and assert the expected resume stage;
10. repeat structural validation with `QA_MODE=OFF`, proving semantic QA is skipped but structure remains enforced.

A passing test proves installation and resumability. It does not prove provider credentials, quota, or paid generation.

## Known boundary conditions

- A package registry with one current model is still compatible with a generic VIDEO capability; adding a model should update the registry and its capability declaration, not the planner's conceptual vocabulary.
- A FFmpeg runner that accepts `filter_complex` and output arguments can reach the complete installed runtime even if it does not expose a typed helper for every operation.
- The Google Drive adapter and OAuth credentials are separate from the package's public URL/yt-dlp path.
- QA OFF is a debugging mode, not an excuse to skip file, decode, duration, hash, provider-download, or schema checks.
- The production profile should not inherit old project artifacts or old profile state merely to make a test pass.
