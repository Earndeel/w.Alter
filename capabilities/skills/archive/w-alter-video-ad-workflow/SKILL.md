---
name: w-alter-video-ad-workflow
description: "Use when adapting or recreating beauty video ads requires reference fidelity review, the ad-video production pipeline, and video analysis pipeline implementation or troubleshooting."
type: workflow
requires: [reference-video-fidelity, ad-video-pipeline, video-analysis-pipeline]
---

# W.Alter video ad workflow

Use this workflow when a real session needs the three W.Alter skills as one connected process. Execute the stages in the order below. At every stage, load the named sub-skill with `skill_read` before applying it; do not rely on a previous invocation or on a remembered copy.

The workflow applies when the task combines reference-led adaptation or review, beauty-ad production through the generation and delivery pipeline, and implementation or troubleshooting of the video-analysis workflow. If the request covers only one of those concerns, use the relevant sub-skill directly.

## Shared contract

Maintain one working record for the session containing:

- the source reference and its provenance;
- the client brief, approved offer, product, audience, and claims;
- the shot map and adaptation decisions;
- the analysis artifact and its storage location;
- the approved generation payloads and their status;
- generated media, edit, caption, audio, and delivery artifacts;
- unresolved questions, rejected evidence, and approval state.

Keep reference observations, client-approved claims, model-generated material, and technical evidence distinguishable. Do not allow a later stage to silently replace an earlier approved decision. When a stage finds a blocking defect, stop the dependent work, record the defect and affected artifacts, and return to the stage that owns the correction.

## Stage 1: establish reference fidelity and adaptation requirements

Load the sub-skill before doing this stage:

```text
skill_read(name="reference-video-fidelity")
```

Use it to inspect the reference and define the acceptance contract for the adaptation. Produce a handoff package containing:

- verified reference provenance and the authoritative source asset;
- shot order, timing, roles, actions, framing, locations, transitions, overlays, typography, dialogue, music, and other observed audiovisual properties;
- a separation between reference structure and factual or commercial claims;
- the approved adaptation brief, including product, audience, benefits, eligibility language, wardrobe, locations, casting, and identity constraints;
- a per-shot adaptation map that preserves narrative functions and meaningful roles;
- audio and caption requirements, including the intended source of speech and music;
- a fidelity acceptance checklist and explicitly uncertain observations;
- any pre-generation approval required for the storyboard, shot list, or prompts.

Before handing off, check that the source is the original creative reference rather than a derivative clip or screen recording, that claims are approved independently of the reference, and that the opening satisfies the current acquisition brief. Confirm that the proposed shot map is concrete enough to review beside source frames. Do not authorize generation if the reference evidence, brief, audio contract, or approval state is incomplete.

Handoff to Stage 2:

```text
reference_handoff = {
  "source": "authoritative reference and provenance",
  "brief": "approved adaptation brief",
  "shot_map": "ordered per-shot adaptation plan",
  "audio_contract": "approved speech, music, and provenance requirements",
  "acceptance": "fidelity and release criteria",
  "approval_state": "approved, needs revision, or blocked"
}
```

## Stage 2: turn the approved adaptation into production work

Load the sub-skill before doing this stage:

```text
skill_read(name="ad-video-pipeline")
```

Use it to execute the production pipeline against `reference_handoff`. Map the approved reference into the pipeline's source intake, analysis context, prompt and payload preparation, review, generation, synchronization, and delivery stages. Preserve the handoff's shot order, roles, approved claims, audio contract, and review gates in every downstream payload.

The stage must produce:

- a registered source and project context;
- a production-ready shot and prompt package;
- model-specific payloads that respect the approved audio and visual requirements;
- an approval record for payload changes and any paid generation;
- generation job identifiers and provenance;
- downloaded outputs and an edit candidate;
- a delivery candidate with its associated metadata.

Before each irreversible or credit-consuming action, verify that the relevant payload is approved, the audio source is resolved, the product and claim substitutions are correct, the model and duration limits are valid, and the source-to-output shot mapping is intact. After every generation, compare the result with the corresponding reference material and the approved shot map before using it as conditioning or as a delivery component. Keep rejected takes and their reasons available for audit.

If the production stage requires analysis tooling, implementation changes, database work, dashboard behavior, upload handling, or troubleshooting of the analysis path, pass the concrete implementation context to Stage 3. If no such work is required, still record the production artifacts and continue the final checks defined below.

Handoff to Stage 3:

```text
pipeline_handoff = {
  "reference_handoff": "the approved Stage 1 package",
  "project_context": "card, source, product, and brief identifiers",
  "analysis_request": "video and structured-analysis requirements",
  "payloads": "approved model payloads and versions",
  "media": "source, generated takes, edit candidate, and provenance",
  "implementation_scope": "files, endpoints, database, or dashboard work if needed",
  "blocking_findings": "open production defects or unresolved decisions"
}
```

## Stage 3: implement, run, or troubleshoot video analysis

Load the sub-skill before doing this stage:

```text
skill_read(name="video-analysis-pipeline")
```

Use it to handle the analysis portion of `pipeline_handoff`. Choose the smallest applicable operation: run analysis on the source or candidate video, repair the upload or model-routing path, persist structured results, expose them through the dashboard, or diagnose a failed analysis. Keep the analysis input, prompt configuration, provider response, stored record, and rendered dashboard result traceable to the same project and media version.

The stage must return:

- the analyzed media identifier and hash or equivalent version marker;
- the structured analysis result and persistence location;
- the model, prompt, request, retry, and timing evidence needed to interpret it;
- any implementation changes made to upload, analysis, storage, API, or UI behavior;
- a clear status for the analysis: complete, incomplete, failed, or blocked;
- discrepancies between model output and observed media that require Stage 1 or Stage 2 review.

Check that the analysis receives the intended video, that system instructions and user media are passed through their correct channels, that oversized inputs follow the supported preparation path, that transient provider failures are handled according to the sub-skill, and that stored results belong to the correct project record. Verify the dashboard or API using the real endpoint and stored result when those surfaces are part of the task. Do not treat a successful provider response as proof of reference fidelity, caption correctness, audio provenance, or release readiness.

Handoff to final integration:

```text
analysis_handoff = {
  "media_version": "exact analyzed asset",
  "analysis": "structured result and storage reference",
  "technical_evidence": "request, response, persistence, and UI/API checks",
  "discrepancies": "observed conflicts or uncertainty",
  "status": "complete, incomplete, failed, or blocked"
}
```

## Cross-stage integration and release gate

Reconcile `analysis_handoff` with the original `reference_handoff` and `pipeline_handoff`. Resolve conflicts against the strongest available evidence: source provenance and timestamped media observations for reference questions, approved brief and review records for claims, and native files, hashes, decoded media, and actual endpoint behavior for technical questions.

Run these gates before declaring completion:

1. The delivered or reviewed asset maps to the approved shot structure and preserves meaningful actions, roles, framing, transitions, and overlay intent.
2. Product claims and eligibility language match the approved brief.
3. Dialogue, native audio, music, captions, word timing, typography, safe areas, and visible text satisfy the applicable acceptance criteria.
4. The final media is technically decodable, durationally correct, and accompanied by provenance and analysis evidence.
5. The analysis result is attached to the correct project and media version and is visible through the intended storage or dashboard surface.
6. Every rejection, uncertainty, regenerated take, changed prompt, and approval decision remains traceable.
7. Any blocking discrepancy is either resolved by the owning stage or explicitly reported as blocked; it is never converted into an approval by omission.

For a failed gate, identify the owning stage, invalidate dependent artifacts where necessary, and reload that stage's sub-skill with `skill_read` before revising the work. After a revision, rerun the checks from that stage forward. Finish with a compact record of the accepted artifact, validation evidence, unresolved limitations, and the next required approval if any.
