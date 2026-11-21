---
name: kie-video-evidence-to-delivery
description: "Use when a Kie.ai video task requires web discovery, verification of current pricing or provider access, and an operational handoff to generation and output QA, including H3 compatibility checks."
type: workflow
requires: [walter-browse-orchestrator, research-evidence-verification, kie-video-generation-operations]
---

# Kie video: evidence to delivery

Use this workflow when current web evidence must inform a Kie video-generation decision or execution. Follow the sequence below; stop at the research verdict when generation is outside the user's request. The required skills own their detailed procedures, schemas, and references; load them rather than reproducing their instructions here.

## 1. Discover sources and current options

load walter-browse-orchestrator with skill_read.

Use its web entry point to locate current official sources relevant to the requested model, pricing, account access, and capabilities. Carry the user's exact model/version, input materials, output requirements, budget, and intended action into discovery.

Hand off a source packet: URLs, retrieval timestamps, relevant extracted evidence, candidate model/provider identities, and unresolved questions. Keep account/session context as metadata without credentials.

Check before proceeding: each source must identify which model, route, and configuration it describes. Search snippets and inaccessible pages remain leads. Missing source content returns to discovery rather than becoming an assumed fact.

## 2. Verify the decision evidence

load research-evidence-verification with skill_read.

Evaluate the source packet against the user's constraints using that skill's evidence and normalization procedures. Establish the comparison baseline when comparing options, and assess provider access separately from price.

Hand off a decision packet: selected exact model/version and provider route; requested duration, ratio, resolution, audio and input mode; timestamped pricing evidence with billing units; access status; capability evidence; evidence classifications; conflicts and remaining blockers. Include H3 reference-conditioning or adapter requirements when relevant.

Check before proceeding: the selected offer must match the intended execution configuration, and critical price, access, or capability conflicts must be resolved or explicitly retained as blockers. Return targeted gaps to step 1. A research-only request ends with the evidence verdict; a recommendation does not authorize spending.

## 3. Execute the selected route and verify delivery

load kie-video-generation-operations with skill_read.

Use the decision packet to select the relevant operational procedure and references. Revalidate the live model contract against the selected configuration before submission. For H3, load its applicable compatibility reference through this skill and reconcile the actual provider schema with the required capabilities.

Check the execution handoff: current user authorization covers the intended paid action, the operational credit check supports the bounded run, required assets are ready, and the live contract matches the verified model and configuration. Asset-upload success alone does not authorize generation. If contract or pricing validation changes the decision, return to step 2; do not silently substitute a model or route.

Follow the operational skill for submission, polling, download, cost accounting, and media QA. Preserve task identifiers and execution state across interruptions so resuming the workflow does not create a duplicate paid task. Keep retries within the authorized scope.

Hand off the downloaded artifact, task status, observed cost, QA findings, and unresolved limitations. Report delivery only after the operational completion and QA gates pass; otherwise report the precise pending or failed stage.

## Completion record

Connect the result to the decision: selected model and configuration, supporting evidence and check time, execution status, artifact location when available, measured cost, and QA verdict. Keep research conclusions, accepted tasks, completed generations, and verified deliverables distinguishable. If blocked, state the smallest next check or action needed to continue.
