# Structural Migration Contracts — Creative Factory v1.3

This reference records the validated migration pattern for an existing Hermes video-reconstruction profile. It is a reusable checklist, not a second orchestrator.

## Target layout

Keep job data under `workspace/jobs/` only. Put executable modules in `runtime/`, business/config manifests in `workflow/`, and authoritative JSON schemas in `schemas/`. Keep exactly nine canonical stage skills under `skills/<stage>/SKILL.md`; delete the legacy duplicate skill tree only after comparing both copies and preserving the newest rules (notably brand minimal-diff rules).

Before deleting the legacy tree, search the whole profile for old runtime/schema/skill paths. Update imports, direct-script fallbacks, subprocess commands, YAML/JSON references, tests, wrappers and documentation. Historical strings in an event/session database are not runtime dependencies and should not be rewritten merely to make a text search clean.

## Artifact contract pattern

Use one central validator/writer. A producer emits an object, validates it, applies only deterministic compatibility normalization when explicitly allowed, validates again, hashes the serialized file and persists it atomically. Every authoritative artifact carries `schema_version`; consumers reject a non-canonical version unless the caller explicitly requests a deterministic migration.

Canonical naming examples:

- `generation_units`, not `units`;
- `rationale`, not `reason`;
- `IMAGE_TO_VIDEO`, `IMAGE_TO_POST`, `VIDEO_TO_POST`, `IMAGE_TO_VIDEO_TO_POST`, not Unicode arrow route aliases;
- `pre_generation_review.artifacts[].role` is required;
- target blueprint uses `authority`, `format`, `shots`, `audio`, exclusions and approval flags;
- final delivery uses `result.json` with `status`, local/remote deliverables, Google Drive/Sheets records, verification and completion timestamp.

Legacy normalization may map aliases, add a canonical version and record `migrated_from_schema_version`. It must not silently invent a creative decision or treat an old artifact as authoritative without a migration/recalculation decision.

## Deterministic source forensics

1. Probe with FFprobe: duration, dimensions, aspect ratio, FPS, available frame count, codecs, audio presence, timestamps and rotation.
2. Detect shot candidates with FFmpeg and persist `shots` containing `shot_id`, `start`, `end` and `duration`.
3. Sample chronologically at the workflow's fixed base FPS (Creative Factory v1.3: 5 fps). Do not duplicate frames to meet a quota; derive source frame indices where possible.
4. Chunk each shot into contact sheets of at most 25 frames. Use a compact grid with no forced empty 5×5 area.
5. Resize each thumbnail by exact aspect-ratio scaling so its short side is 300 px. Put a uniform label band below the image; never burn timestamps over source pixels.
6. Persist a per-board manifest mapping board cell, sample index, source frame, timestamp and shot. Use explicit local dense resampling only after an ambiguity and a reason/window/dense FPS are recorded.

The VLM reads these boards for analysis and QA. It does not choose the base sampling rate.

## Analysis/reference boundary

Declare asset roles. `ANALYSIS_CONTACT_SHEET` and `SOURCE_FRAME` are evidence roles; individual generation inputs should be `STORYBOARD_PANEL`, `FIRST_FRAME`, `LAST_FRAME`, `CHARACTER_REFERENCE`, `ENVIRONMENT_REFERENCE`, `PRODUCT_REFERENCE`, `VIDEO_REFERENCE` or `STYLE_REFERENCE`. A provider adapter must reject an analysis contact sheet, and must verify local reference existence plus the expected hash before passing it onward. Never select an input by directory recency or by “last PNG”. Preserve storyboard panels individually even when an overview board is created for human/VLM review.

## Google delivery transaction

Wrap the existing canonical Hermes Google backend rather than creating a second credential store. At QA/Delivery start, probe the required `drive_read`, `drive_write`, `sheets_read` and `sheets_write` capabilities and fail early with a localizable error. For a mission requiring remote delivery:

1. confirm the local deliverable exists and hash it;
2. write/upload through the adapter;
3. read back the remote Drive object/result;
4. write RESULT to the sheet;
5. read back RESULT and verify the returned URL/ID/value;
6. write FINISHED=true;
7. read back FINISHED and RESULT together;
8. persist `result.json` only with `status=FINISHED` after all checks pass.

If Google is unavailable, persist a non-finished local result with the capability failure and leave FINISHED false. A fake adapter is appropriate for deterministic unit tests; do not create arbitrary production Drive/Sheets rows just to exercise the test harness without an approved destination.

## Test matrix

The migration's minimum regression suite should cover:

- compile/import all moved Python modules;
- existing no-provider self-test;
- validation of real artifacts for source manifest, media probe, shots, video IR, Creative DNA, target blueprint, generation plan, pre-generation review, post plan, QA result and RESULT;
- invalid canonical artifact is blocked;
- legacy artifact is rejected without explicit migration and normalized only with migration;
- a short shot produces fewer than 25 samples/one compact board;
- a >5-second shot produces exact 5-fps samples;
- >25 samples paginate with no loss/duplication;
- geometry proves labels sit below images;
- analysis contact sheet cannot be selected as generation reference;
- Google fake adapter completes write → readback → RESULT → FINISHED and failure path remains not finished.

Record actual pass/fail output. Never replace an unexecuted provider or remote transaction with invented success data.

## Known migration boundary

Do not broaden the change into a new model registry, scoring engine, provider router, memory system or creative workflow. The migration is complete when the nine skills remain intact, the old executable/schema tree is gone, contracts are synchronized, the deterministic forensics artifacts are authoritative, and delivery cannot claim FINISHED before remote verification.
