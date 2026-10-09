# Lossless semantic decomposition audit

Use this reference when converting a monolithic reference-video reconstruction skill into a Hermes profile with an orchestrator and stage workers.

## Core rule

The profile may split execution, but it must not split away meaning. The authoritative skill remains the semantic source of truth; stage files and artifacts are only valid when they preserve the information needed by the next provider-facing decision.

A larger directory is not evidence of greater coverage. Count semantic instructions and executable contracts separately from Python files, JSON schemas, and smoke-test code.

## Coverage matrix

Before running a real job, map every authoritative responsibility to an active skill section, artifact field, deterministic adapter, and verification step:

| Responsibility | Required evidence before generation |
|---|---|
| Source decomposition | immutable technical metadata, verified cuts, original-frame candidates |
| Local visual forensics | shot-level subject, environment, camera, photography, motion, confidence |
| Global creative DNA | archetype, hook, beats, audience relationship, visual/edit/audio/text grammar, invariants |
| Dialogue intelligence | exact lines where available, speaker/subject mapping, timing, delivery, mouth visibility, reproduction policy |
| Overlay/audio policy | OCR/overlay intervals and deterministic-vs-generated classification |
| Override/target blueprint | explicit preserve/replace/reinterpret/remove/add decisions and provenance |
| Generation planning | exact fractional source duration, provider-valid duration, internal cuts, source-content end, padding hold, post-trim |
| Source references | 4 or 6 original storyboard states plus reusable character/environment evidence |
| Asset materialization | actual reference-conditioned image calls, bound input hashes, output files, receipts, asset QA |
| Provider compilation | semantic aliases mapped to actual provider inputs, authority hierarchy, chronological state/action timeline, exclusions |
| Generation/QA | provider job/file IDs, downloaded MP4, technical probe, multidimensional QA, targeted repair lineage |
| Post/delivery | deterministic trim/concat/overlay/audio plan, final QA, stable delivery receipt |

If any row has only prose or a placeholder path, the corresponding stage is not complete.

## Artifact-level checks

1. **Prompt completeness** — A short prompt is acceptable only when a structured generation spec carries the omitted details. Each unit must still preserve source-content duration, provider duration, hard-cut timestamps, source-end padding, state/action intervals, reference authority, dialogue policy, and no-text/UI constraints.
2. **Reference binding** — A filename mentioned in a prompt is not an image binding. Verify that the actual source board or selected image bytes were submitted, then record input hashes, output hash, provider/model, mode, and `binding_verified=true`.
3. **Materialization gate** — Do not mark ASSETS or planning complete with `PROMPT_ONLY` storyboard/character/environment assets when the authoritative workflow requires reference-conditioned materialization. Block with a precise status instead of continuing with source boards or review maps as if they were clean provider assets.
4. **Source-board separation** — Analysis contact sheets and original-frame source boards may retain labels/overlays for provenance; final generation assets must be cleaned or deterministically cropped after asset QA. Never silently send a labeled source board as the final photographic authority.
5. **Provider preflight** — Resolve the real provider/model/contract before generation. A configured default with no backend, unresolved model, or unverified duration/reference contract is a blocker, not a low-quality generation mode.
6. **Quality claims** — A deterministic media smoke test proves plumbing only. Do not claim visual quality, A/B superiority, or a completed reconstruction without a real downloaded MP4 and technical plus visual QA. If the run is provider-blocked, report the diagnosis as architectural evidence, not as a measured output score.
7. **Comparability** — Faithful reconstruction and brand adaptation are different experiments. Record target mode, identity policy, supplied exact assets, UI availability, and provider/model before attributing a quality difference to orchestration.

## Typical regression pattern

A monolithic worker produces detailed provider prompts with `OUTPUT`, `REFERENCE AUTHORITY`, `TIMELINE`, `DIALOGUE`, and `CONSTRAINTS`. A decomposed worker later emits one-sentence prompts, omits `internal_cuts` and `reference_map`, and validates only JSON shape. This is a semantic regression even when all smoke tests pass.

The repair direction is to restore one canonical semantic authority and use stage boundaries only for execution, resumability, and validation. Do not solve the regression by adding more narrow skills that repeat the same missing logic.
