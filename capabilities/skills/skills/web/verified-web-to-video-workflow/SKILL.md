---
name: verified-web-to-video-workflow
description: "Use when a Kie.ai video task requires public-web research followed by verification of current model pricing, availability, provider access, or capabilities before generation, delivery, or an operational recommendation."
type: workflow
requires: [universal-web-extraction-router, research-evidence-verification, kie-video-generation-operations]
---

# Verified Web-to-Video Workflow

## Scope

Apply this workflow when a video request needs the complete chain: public-web discovery or extraction, verification of decision-critical evidence, and Kie.ai generation operations or compatibility planning. Examples include selecting a currently usable video model within budget, checking an H3 capability before preparing a job, or researching factual claims for a generated video.

Do not force this chain onto unrelated web research or a standalone task-status check. A research-only or planning request does not authorize paid generation.

This skill coordinates the handoffs and gates. The sub-skills remain authoritative for extraction methods, evidence standards, and provider operations; do not reproduce their implementations here.

## Shared handoff record

Maintain one compact record throughout the workflow:

- Request: desired deliverable, exact model/version if specified, output requirements, input assets, budget, region, and authorization scope.
- Constraints: hard requirements, preferences, unresolved questions, and research timestamp/timezone.
- Evidence: source URLs, relevant extracted facts, retrieval time, exact pricing units and variant context, extraction limitations, and verification status.
- Decision: selected route/model, reasons, rejected alternatives, blockers, and next permitted action.
- Execution: verified contract reference, approved spend scope, task status, artifact locations, observed cost, and QA verdict when applicable.

Never place credentials or sensitive session material in this record.

## 1. Discover and extract

**Load:** load universal-web-extraction-router with skill_read.

Give this step the user brief and a list of facts needed to make the video decision. Follow the loaded skill to discover and read relevant public sources, prioritizing official model documentation, pricing, capability, and access pages.

**Handoff to step 2:** provide source-linked observations and extracted records, retrieval timestamps, exact model/version labels, pricing and capability context, and any failed or incomplete extraction. Preserve contradictions rather than choosing a convenient value.

**Gate:** verify that the returned material actually addresses the requested model and semantic target. An inaccessible page, empty extraction, search snippet, or tool success flag alone cannot establish a usable contract or current price. Mark missing facts explicitly; do not infer them.

## 2. Verify evidence and feasibility

**Load:** load research-evidence-verification with skill_read.

Give this step the shared request constraints and the source bundle from step 1. Apply the loaded skill's evidence and normalization standards to the claims that determine model selection, affordability, access, and required capabilities.

**Handoff to step 3:** provide an evidence-backed decision packet containing:

- Exact selected provider/model/version and requested generation mode.
- Supported output settings and input requirements, with source references.
- Current price evidence with native billing units, comparison baseline, and explicitly labeled estimates.
- Access and capability findings, evidence levels, unresolved conflicts, and expiry-sensitive assumptions.
- User authorization and spending limits, clearly distinguished from technical feasibility.

**Gate:** proceed toward submission only if hard constraints are supported and unresolved facts cannot materially change compatibility, cost, or permission. If evidence is insufficient, return targeted collection questions to step 1 and repeat verification. If a required capability is unsupported or unverified, report the blocker rather than silently substituting a model or inventing a field.

A planning or comparison request may proceed to step 3 for an operational recommendation, but not for a paid task.

## 3. Execute or produce an operational plan

**Load:** load kie-video-generation-operations with skill_read.

Give this step the verified decision packet and approved execution scope. Follow the loaded skill for current contract validation, applicable H3 compatibility checks, credential handling, paid-task gates, submission, polling, downloads, cost accounting, and output QA.

**Pre-execution gate:** reconcile the live operational contract and cost checks with step 2. If a material model, capability, access, or pricing discrepancy appears, pause submission, return to evidence collection and verification, and obtain renewed approval if the change exceeds the authorized scope. Successful asset upload is not authorization to generate.

**Handoff to delivery:** provide the operational verdict, task identifiers/status where applicable, local artifact locations, measured output properties, actual observed cost when available, and QA results or remaining limitations.

**Completion gate:** distinguish planned, uploaded, submitted, running, failed, downloaded, and QA-verified states. Do not claim delivery merely because task creation succeeded. Do not initiate additional paid attempts or substitute models outside the approved scope.

## Final response contract

Lead with the outcome: verified recommendation, delivered artifact, pending task, or blocker. Include the selected exact model, relevant source-backed cost and access findings, execution status, artifact location if available, QA verdict, and any unresolved limitation. Keep estimated prices separate from observed charges and unverified capabilities separate from supported ones.

When blocked, state the single next verification or authorization action needed. Preserve useful evidence and task identifiers so work can resume without duplicate submissions.
