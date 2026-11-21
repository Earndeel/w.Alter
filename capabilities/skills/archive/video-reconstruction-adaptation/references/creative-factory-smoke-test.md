# Creative Factory v1.2 — first-project smoke test

This reference captures a tested first-project pattern for an isolated `creative-factory` profile. It is a runbook around the package's canonical stages, not a replacement orchestrator and not a tenth skill.

## Goal and hard stop

Use a real local reference video to exercise:

```text
SOURCE INTAKE → SOURCE FORENSICS → CREATIVE DNA → BRAND ADAPT
→ VIDEO PLAN → ASSET BUILD → PREGEN REVIEW
```

Keep `CREATIVE_FACTORY_MODE=DEV` and temporarily set `QA_MODE=OFF` for manual inspection. `QA_MODE=OFF` skips semantic QA/auto-repair only; structural checks, schema validation, hashes, decode checks, and the DEV PREGEN gate remain mandatory. Do not call the video provider before the human approves the PREGEN artifact.

The smoke test may perform exactly the explicitly requested IMAGE materialization (for example, one GPT Image 2 storyboard frame with a bound source-frame reference). That does not authorize VIDEO GENERATE, POST PROD, or DELIVERY.

## Secret and Drive preflight

1. Resolve the video provider key from the vault into the isolated profile's secret-bearing environment. The validated pattern was:
   - vault service: `kie/api_key`;
   - profile env: `$PROFILE_HOME/.env`;
   - permissions: `0600`;
   - runtime variable: `KIE_API_KEY`.
2. Verify presence and exact vault-to-profile binding in-process, reporting only boolean/length/hash metadata. Never print the value.
3. Verify the shared Google Drive adapter twice before using private Drive sources:
   - authentication check with the shared adapter's setup command;
   - one real read-only Drive operation such as a bounded `trashed = false` search.
4. Keep the adapter's credential home (validated layout: `HERMES_HOME=/root/.hermes`) distinct from the profile workspace. Do not copy OAuth tokens or client secrets into the job, package, or skills. Record the dependency and non-secret check result in a small profile/job documentation artifact.

## Source and forensics recipe

1. Use `runtime/fetch.py` to copy the local input into `jobs/<mission_id>/work/source/` and write `source_manifest.json`.
2. Run `runtime/media.py probe` and `runtime/media.py cuts` against the materialized file. Check that the manifest hash matches the local file.
3. Extract an overview contact sheet and a six-frame dense contact sheet for each measured shot. Six frames is a useful manual-review minimum for short vertical UGC shots; use timestamped frame manifests so the contact sheet is not the only evidence.
4. Record `video_ir`, dialogue/caption evidence, audio facts, shot boundaries, frame candidates, confidence, and uncertainty. Visible captions are not an audio ASR transcript unless ASR was actually run.
5. When re-extracting a full-resolution reference frame, the package CLI flag is `--out` (not `--output`).

## Planning and binding

Produce durable artifacts before generation:

- Creative DNA and source visual invariants;
- brand inventory/context and an explicit no-external-brand assumption when no target brand pack was supplied;
- target blueprint;
- provider-neutral generation plan plus per-unit prompts/specs;
- storyboards, character/environment sheets, materialized asset manifest;
- reference maps with real local-image provider inputs;
- post plan and the installed FFmpeg capability snapshot.

For IMAGE, a filename mentioned in a prompt is insufficient. Call the configured image tool with the actual local source frame (or uploaded URL) in its image/reference input, save the returned image into the job assets, and record the provider, model, input binding, raw output, cropped inspection output, and hashes. Preserve the raw provider output when a deterministic crop/pad is needed for the target aspect ratio.

For VIDEO, keep generation specs provider-ready but set explicit `submitted: false` / `generation_allowed: false` until approval. A model registry entry can be selected for planning without making a Kie.ai request.

## PREGEN gate

Call the package review preparer with the complete input list, including target/brand context, plans, prompts, reference maps, generation specs, post plan, materialized assets, and image receipts. The expected first-project state is:

```text
status = PENDING_APPROVAL
current_stage = PREGEN_REVIEW
video_generation_blocked = true
```

Validate the review schema, but do not call `review.py decide`. A validation result reporting `PREGEN_GATE_BLOCKED: status=PENDING_APPROVAL` is the expected proof that the gate is closed, not a failed smoke test. The self-test may separately approve its own fixture to test invalidation; never confuse that approval with the real project's pending gate.

## Final assertions before handoff

- `CREATIVE_FACTORY_MODE=DEV` and `QA_MODE=OFF` are persisted in the profile/runtime environment.
- The source hash, shot count, contact sheets, and required planning artifacts exist.
- The image receipt proves one real reference-bound IMAGE call, if requested.
- `provider_calls.video == 0`, `provider_calls.post == 0`, and there is no generated MP4 beyond the copied source.
- The review artifact is pending approval and explicitly lists the artifacts the human must inspect.
- Source, target, generation-plan, post-plan, and review schemas pass; structural validation remains active.

Validated evidence from one smoke run: a 20-second 9:16 source produced 9 measured shots, 6 frames per shot, 5 provider-ready video units, one reference-bound GPT Image 2 storyboard, and a 43-artifact PREGEN review with zero VIDEO submissions. Treat those numbers as evidence for that run, not universal defaults.
