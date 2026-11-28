---
name: reference-ad-video-workflow
description: "Use when creating or reviewing a reference-led cosmetic or beauty video ad that needs fidelity controls, ad production, and structured video analysis through the pipeline or dashboard."
type: workflow
requires: [reference-video-fidelity, ad-video-pipeline, video-analysis-pipeline]
---

# Reference-led ad video workflow

Orchestrate the required skills in this order: reference-video-fidelity → ad-video-pipeline → video-analysis-pipeline. These are loading and handoff stages; production waits for validated analysis. Keep implementation procedures in the sub-skills.

## 1. Establish the fidelity contract

load reference-video-fidelity with skill_read.

Apply it to the original reference and current client brief. Produce a reference packet containing source identifiers, the shot-level acceptance contract, approved adaptation boundaries, audio and caption requirements, unresolved evidence, and approval status.

Handoff to step 2: the reference packet and links to the original media and supporting evidence.

Check before proceeding: the creative authority and current offer are identified; uncertainties are recorded; requirements are sufficiently clear for planning. Missing reference evidence blocks affected creative decisions.

## 2. Plan production and request analysis

load ad-video-pipeline with skill_read.

Use the reference packet to establish the production record, locate or acquire the source media, and map the requested adaptation to the pipeline stages. Prepare an analysis request before finalizing generation prompts.

Handoff to step 3: source media, production/card identifier, client instructions, the fidelity contract, required analysis outputs, and any observed analyzer or dashboard failure.

Check before proceeding: the media belongs to the intended production record, analysis requirements reflect the current brief, and audio requirements remain consistent with step 1. Keep paid submission pending the downstream analysis and approval gates.

## 3. Obtain and verify structured analysis

load video-analysis-pipeline with skill_read.

Use its analysis path; build or troubleshoot the upload, persistence, or dashboard integration only when needed for the task. Reuse an existing analysis only when its source and requirements match the current packet.

Handoff back to production: structured analysis, source and analysis identifiers, saved-record location, dashboard retrieval result where applicable, and unresolved observations or technical failures.

Check before proceeding: analysis completed successfully, describes the intended media, contains the required structure, and can be retrieved from its saved record. An error response or empty saved result does not satisfy this gate. Reconcile observations against the evidence standards from step 1; retain unresolved disagreements rather than treating model output as acceptance.

## 4. Resume production and approval

load ad-video-pipeline with skill_read.

Combine the verified analysis with the fidelity contract to prepare the reviewable adaptation and generation payloads. Follow the sub-skill's review, generation, and assembly stages.

Handoff to release review: approved plan and payloads, approval evidence, generated sources, assembled candidate, and provenance linking each artifact to the current production record.

Check before spending: approval covers the actual prompts and creative direction. Check the first output against the contract before extending production. A changed brief or failed resemblance gate returns to planning; it does not authorize additional paid generation.

## 5. Review and deliver

load reference-video-fidelity with skill_read.

Evaluate the assembled candidate against the acceptance contract and record the release decision with supporting evidence. Return failures to the responsible earlier stage, preserving prior artifacts and invalidating affected downstream approvals.

Once release checks pass, load ad-video-pipeline with skill_read and complete its delivery stage within the user's authorized scope.

Final handoff: delivered artifact link, production and source identifiers, QA record, approval status, and any disclosed limitations. Verify that the delivered file is the reviewed candidate before marking the work complete.
