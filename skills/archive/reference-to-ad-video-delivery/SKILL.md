---
name: reference-to-ad-video-delivery
description: "Use when a video ad must be adapted from a reference, analyzed through the pipeline, regenerated, and delivered with fidelity and release QA."
type: workflow
requires: [reference-video-fidelity, ad-video-pipeline, video-analysis-pipeline]
---

# Reference-to-ad video delivery workflow

Orchestrate the three W.Alter skills in this order when the task involves adapting a reference video into a beauty or cosmetic ad and delivering a verified result:

1. `reference-video-fidelity`
2. `ad-video-pipeline`
3. `video-analysis-pipeline`

Use each sub-skill for its own domain rules and procedures. This workflow defines sequencing, handoffs, and gates; it does not replace or reproduce the sub-skills' detailed instructions.

## Applicability and inputs

Start this chain when the task includes at least two of the following: reference-video adaptation, shot-level fidelity review, structured video analysis, beauty-ad generation, Kling or equivalent model generation, dashboard analysis, or delivery QA.

Collect or identify:

- the original reference video and its source message, sender, and file identity;
- the client's current brief, approved offer, product, audience, claims, script, and audio requirements;
- the target card or project identifier;
- the required output format, duration, aspect ratio, destination, and approval authority.

If the reference or brief is unavailable, record the missing input and continue only with work that does not depend on it. Do not infer approval from an existing generated asset.

## Step 1: establish the reference fidelity contract

Load the first sub-skill before performing reference adaptation or fidelity analysis:

`load reference-video-fidelity with skill_read`

Apply that skill to establish a source-grounded contract covering the reference's shot order, timing, roles, wardrobe, locations, actions, framing, transitions, overlays, typography, audio, and relevant commercial structure. Keep the approved client claims separate from claims observed in the reference.

Produce a handoff package containing:

- source identifiers and provenance;
- a timestamped shot list with source frames or equivalent evidence;
- the client's approved creative and commercial constraints;
- audio provenance and dialogue requirements;
- adaptation decisions, unresolved ambiguities, and rejected interpretations;
- fidelity risks that generation or postproduction must preserve or resolve.

### Gate 1: reference and brief alignment

Before moving on, verify that:

- the source authority is identified;
- the current client brief is distinct from the reference's claims;
- every required shot or narrative function has an adaptation decision;
- identity, role, product, text, and audio constraints are explicit;
- unresolved disagreements are recorded rather than converted into facts;
- any credit-consuming generation is blocked until the required prompt or storyboard approval exists.

If the opening does not support the current acquisition brief, revise the proposed opening and obtain the required approval before generation.

## Step 2: run structured video analysis and expose the result

Load the second sub-skill before starting the analysis and dashboard workflow:

`load video-analysis-pipeline with skill_read`

Use the handoff from Step 1 to select the correct source asset and analysis context. Run the supported direct-video analysis path, preserve the system/user prompt separation, save the structured result under the correct project or card, and expose it through the dashboard or required analysis interface.

The analysis handoff to the next step must include:

- the persisted analysis record and its project/card identifier;
- structured shot timing and scene descriptions;
- composition, camera, subjects, overlays, audio, and transition observations;
- quality, engagement, sales, and overall assessments where produced;
- model, prompt, input-file, retry, and error metadata needed for audit;
- a clear distinction between observed evidence, model interpretation, and unresolved uncertainty.

### Gate 2: analysis integrity and usability

Before building generation payloads, verify that:

- the analyzed file is the intended source and is available to the pipeline;
- the analysis completed without silently saving an error or truncated response;
- the saved record can be retrieved by the intended card/project identifier;
- the shot sequence and timings are usable for prompt construction;
- API failures, rate limits, compression, and retries are retained as operational evidence;
- the dashboard displays the analysis that will actually inform generation.

If the analysis conflicts with timestamped evidence from Step 1, preserve both observations, resolve the conflict against the source media, and update the handoff before continuing.

## Step 3: adapt, generate, review, and deliver the ad

Load the third sub-skill before preparing prompts, submitting generation jobs, or delivering assets:

`load ad-video-pipeline with skill_read`

Pass the complete Step 1 fidelity contract and the validated Step 2 analysis into the ad pipeline. Use them to create the shot adaptation, model-specific payload, audio contract, review package, generation jobs, assembled master, and delivery package according to that sub-skill.

Maintain these handoff requirements throughout the step:

- the approved offer and product replace unsupported reference claims;
- every generated shot maps to a source shot or declared narrative function;
- audio requirements remain consistent from prompt through final mix;
- model payloads, approvals, revisions, job identifiers, and outputs remain traceable;
- generated footage is checked against the reference before later shots are conditioned on it;
- delivery metadata identifies the exact final media file and its provenance.

### Gate 3: approval before paid or irreversible work

Before credit-consuming generation, confirm that the review package contains the source comparison, shot-by-shot adaptation, prompts or payload, audio behavior, duration, aspect ratio, product treatment, and known risks, and that the authorized reviewer approved it. A request to revise does not authorize another paid generation until the revised package is approved.

### Gate 4: final release QA

Before delivery, run the final checks required by the loaded sub-skills and reconcile them with the Step 1 contract:

- reference fidelity at shot, role, action, framing, timing, overlay, and typography levels;
- approved dialogue, word-level caption timing, legibility, safe areas, and absence of unintended generated lettering;
- native-audio provenance, intelligibility, naturalness, lip sync, music balance, edit-boundary quality, and final mix integrity;
- duration, frame count, container and codec behavior, EOF alignment, and playback through the actual delivery path;
- absence of padded tails, duplicated caption hierarchies, concealed geometry defects, unsupported claims, or unresolved source disagreements;
- complete sidecars, hashes, job records, and format-specific QA evidence;
- correct destination, filename, access permissions, and project/card status.

Treat fidelity, transcript/caption accuracy, audio quality, and technical integrity as separate release gates. A technically decodable file or a transcriptically correct file does not pass if it fails the reference contract or approved creative brief.

## Failure and recovery

Stop the chain at the first failed gate and return the failed artifact, evidence, and the smallest required correction to the responsible sub-skill. Preserve rejected masters, raw analyses, source hashes, prompts, sidecars, and process transcripts. Do not hide a fidelity, geometry, audio, caption, or playback defect with an unapproved redesign, and do not claim release approval from a model summary alone.

When a later step reveals an upstream problem, invalidate dependent prompts, jobs, captions, or delivery artifacts as appropriate, retain them as history, repair the upstream handoff, and rerun only the affected downstream stages after approval requirements are satisfied.

## Final workflow output

Return or store one auditable delivery bundle containing:

- the reference fidelity contract;
- the persisted structured analysis and dashboard reference;
- the approved adaptation and generation payload;
- generation and delivery provenance;
- final media and format-specific QA evidence;
- approval status, unresolved limitations, and the destination link or path.
