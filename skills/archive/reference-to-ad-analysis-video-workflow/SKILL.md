---
name: reference-to-ad-analysis-video-workflow
description: "Use when a video project requires reference fidelity review, beauty ad recreation, and the supporting video analysis or dashboard workflow in sequence."
type: workflow
requires: [reference-video-fidelity, ad-video-pipeline, video-analysis-pipeline]
---

# Reference-to-ad analysis workflow

Use this workflow when the work spans all three stages below. Keep the stages in this order and preserve their artifacts between stages.

## Execution contract

1. Load `reference-video-fidelity` with `skill_read` before beginning the reference stage.
2. Load `ad-video-pipeline` with `skill_read` before beginning the recreation stage.
3. Load `video-analysis-pipeline` with `skill_read` before beginning the analysis and dashboard stage.

At every stage, use the loaded sub-skill as the authority for its detailed procedures, required files, tools, and acceptance criteria. This workflow coordinates the handoffs and gates; it does not replace the sub-skills.

Run the stages only when the request involves the complete chain. If a request covers only one or two stages, use the directly relevant sub-skill instead of forcing the entire workflow.

## Stage 1 — establish the reference contract

Load `reference-video-fidelity` with `skill_read`.

Identify the authoritative source video and the client brief separately. Produce a reference package containing:

- source identity and provenance;
- a timestamped shot list with shot order, duration, framing, subjects, actions, locations, transitions, overlays, and typography;
- separate observations for dialogue, music, ambience, and other audio;
- approved commercial claims and adaptation constraints;
- known uncertainties or disagreements that require later verification;
- a fidelity checklist for the recreated master.

Use native video, timestamped frames, and independent audio or transcript evidence where the sub-skill requires them. Keep source observations distinct from proposed creative changes.

Before leaving this stage, check that the source file or an explicitly documented substitute is available, the shot structure is usable, claims are separated from visual imitation, and unresolved fidelity questions are recorded. Do not authorize generation while the opening, shot mapping, or source authority remains unclear.

**Handoff to Stage 2:** pass the reference package, client brief, approved claims, audio contract, fidelity checklist, source media identifiers or hashes, and all unresolved questions. The next stage must use these artifacts as inputs rather than reconstructing the reference from memory.

## Stage 2 — adapt and produce the beauty ad

Load `ad-video-pipeline` with `skill_read`.

Convert the reference package into an implementation plan for the target beauty or cosmetic ad. The plan should map each source beat to an adapted shot, identify product and identity references, define the requested spoken wording and audio provenance, and specify the intended generation model and delivery path.

Before any credit-consuming generation or submission:

- reconcile the audio requirement with every speaking shot;
- confirm the target product, audience, claims, aspect ratio, and duration;
- compare the proposed shot plan and prompts with the Stage 1 fidelity checklist;
- identify where an action, role, or camera position must be adapted rather than copied literally;
- obtain the required human approval for the proposed payload or revised creative direction.

After approval, run the ad pipeline using the sub-skill's analysis, payload, generation, review, and delivery procedures. Preserve prompt versions, payloads, source references, generation identifiers, native audio provenance, and output media together. Do not treat a generated clip as evidence that it matches the reference; compare it against the reference package before conditioning subsequent work on it.

Before handing off, perform a production gate covering visual fidelity, shot order, claims, product identity, dialogue, lip sync, audio provenance, captions or overlays, duration, encoding, and delivery readiness. Record rejected takes and concrete deviations instead of silently replacing them.

**Handoff to Stage 3:** pass the approved or rejected media, final and intermediate file paths, complete media filenames, hashes, generation and delivery metadata, the reference package, the shot-level comparison results, transcript or ASR sidecars, caption requirements, and any dashboard or analysis task that must be implemented or debugged.

## Stage 3 — analyze and operationalize the workflow

Load `video-analysis-pipeline` with `skill_read`.

Use the Stage 2 media and metadata to run or repair the video-analysis workflow. Determine whether the task is an analysis run, an implementation change, a dashboard change, or troubleshooting. Preserve the distinction between evaluating the creative and changing the analysis system.

For an analysis run, verify the input media and metadata, route the video through the configured multimodal analysis path, save structured results with their model and timing metadata, and expose the result through the supported dashboard or API. Keep system instructions separate from user media content, preserve retry and timeout behavior, and retain failures as diagnosable records.

For implementation or troubleshooting, trace the request through the upload, model call, persistence, API response, and UI display layers. Check file size and media encoding constraints, model response parsing, database identity and update behavior, endpoint status handling, and dashboard rendering. Reuse the existing project conventions and configuration discovered through the loaded sub-skill.

The final Stage 3 gate must confirm that:

- the exact intended media was analyzed;
- the result is associated with the correct project or card;
- structured analysis is saved without overwriting unrelated evidence;
- errors, retries, and unsupported media conditions remain visible;
- the dashboard or API displays the saved result correctly;
- the analysis can be compared back to the Stage 1 fidelity contract and Stage 2 production gate.

## Cross-stage failure handling

Stop the chain at the first failed gate. Preserve the current artifacts, evidence, and failure reason, then return to the owning sub-skill for correction. A later stage may inspect an earlier failure, but it must not promote an unapproved payload, unverified media, or incomplete analysis to the next handoff.

When a creative direction changes, regenerate the affected reference package, payload, or analysis inputs as appropriate and invalidate conflicting downstream artifacts while retaining them as history. Keep source observations, generation decisions, final QA, and dashboard analysis separately attributable.

## Completion record

Finish with one machine-readable or clearly structured record containing:

- the source and output media identifiers;
- the artifacts produced at each stage;
- approval and rejection decisions;
- checks performed and their results;
- unresolved uncertainties;
- generation, audio, caption, and analysis provenance;
- final delivery or dashboard locations;
- the next action if any gate remains open.
