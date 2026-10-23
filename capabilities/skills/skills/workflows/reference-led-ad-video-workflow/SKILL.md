---
name: reference-led-ad-video-workflow
description: "Use when creating or revising a reference-led cosmetic or beauty video ad that requires fidelity review, ad production, and structured video analysis through the pipeline dashboard."
type: workflow
requires: [reference-video-fidelity, ad-video-pipeline, video-analysis-pipeline]
---

# Reference-led ad video workflow

Orchestrate the three required skills in order. They own their detailed procedures; read them rather than reproducing their implementation here. Loading order is not permission to generate before analysis is verified.

## 1. Establish the fidelity contract

load reference-video-fidelity with skill_read

Apply it to establish the authoritative reference, current client brief, approved adaptations, audio requirements, and acceptance criteria.

Hand off a reference dossier: source identifiers and media, timestamped shot map and supporting evidence, approved offer and dialogue, adaptation constraints, unresolved observations, and approval status.

Check before proceeding: the source is authoritative, the brief is current, and assumptions or disagreements are explicitly marked. Missing evidence must remain an open issue rather than becoming a production instruction.

## 2. Plan production and identify analysis needs

load ad-video-pipeline with skill_read

Use the dossier to initialize or resume the production record and prepare the analysis request. Identify which reference or candidate video needs analysis and which production decisions depend on it. Defer paid generation until step 3 has returned verified evidence and the production proposal has approval.

Hand off an analysis request containing the production/card identifier, exact media and its provenance, relevant brief constraints, required structured outputs, and questions that analysis must resolve. Carry forward the fidelity contract and audio contract without silently changing them.

Check before proceeding: the selected media matches the dossier, the record is unambiguous, and existing analyses are identified so stale results cannot be mistaken for this request.

## 3. Run or repair structured analysis

load video-analysis-pipeline with skill_read

Apply its procedures to analyze the requested video, persist the result, and make it available in the dashboard. If the analysis path is broken, repair and verify that path before treating its output as production evidence.

Hand back the structured analysis, exact analysis-record identifier, analyzed-media identity, prompt/configuration provenance, dashboard retrieval result, and any errors or uncertainties.

Check the handoff: the result is substantive analysis rather than a saved provider error; persistence and dashboard retrieval refer to the same media and record. Reconcile its observations against the evidence required by reference-video-fidelity. Keep unresolved contradictions visible and block decisions that depend on them.

## 4. Resume approved production

load ad-video-pipeline with skill_read

Consume the verified analysis and fidelity dossier to prepare the reviewable production proposal. Record approval against the actual storyboard and prompts before generation. Carry accepted takes, source provenance, edit decisions, and the candidate master into the release review.

Check between production stages using reference-video-fidelity: validate the initial take before expanding production, and return material deviations to preproduction. A rejection or changed direction does not authorize another paid run.

## 5. Gate release and deliver

load reference-video-fidelity with skill_read

Review the candidate against the original dossier and retain the evidence and disposition for every acceptance gate. Failed gates return to the responsible earlier step; changes invalidate affected downstream approvals and analyses.

load ad-video-pipeline with skill_read

Deliver only the accepted master through its delivery procedure, within the authorized sharing scope. Hand off the delivered-file identity, Drive link, production-record status, and final QA evidence. Verify that the delivered file is the reviewed master before marking the workflow complete.
