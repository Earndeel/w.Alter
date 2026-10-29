---
name: hermes-context-diagnosis-workflow
description: Use when diagnosing Hermes payload bloat, missing compression, or duplicated injection requires tracing prompt architecture through live context behavior to persisted session evidence.
type: workflow
requires: [hermes-payload-architecture, hermes-context-management, hermes-session-db]
---

# Hermes Context Diagnosis Workflow

Use this chain when a Hermes context problem spans payload composition, runtime compression, and session persistence. For an isolated schema question or a single known configuration issue, load only the relevant sub-skill instead.

This skill coordinates the investigation. The sub-skills own the procedures, commands, and implementation details; read them at the indicated steps rather than reproducing them here.

## 1. Establish the payload architecture

load hermes-payload-architecture with skill_read.

Apply it to map the affected request boundaries and identify which payload layers could explain the symptom. Establish the investigation scope, affected runtime/profile/session, and a representative request or time interval. Separate observations from hypotheses.

Hand to step 2 a compact architecture brief containing:
- The symptom and expected behavior.
- Runtime, platform, provider/model, enabled toolsets, and cwd where known.
- A baseline by relevant payload layer, with measurement sources.
- Suspected contributors and the evidence needed to distinguish them.

**Check before proceeding:** Measurements must describe the affected execution environment. Mark missing measurements explicitly; do not substitute a nominal prompt estimate for an observed provider request. Keep a whole-harness investigation broader than the provider where the symptom appeared.

## 2. Diagnose live context behavior

load hermes-context-management with skill_read.

Use the architecture brief to select the relevant diagnostics. Examine the effective runtime configuration, compression behavior, injection sources, and logs for the representative interval. Treat dated examples and configuration names as hypotheses until checked against the installed version.

Hand to step 3 an evidence request containing:
- Observed behavior versus expected behavior at the suspected boundary.
- Relevant session identifiers, timestamps, and available message anchors.
- Hypotheses about what was retained, summarized, omitted, or duplicated.
- Specific persistence or search questions that could confirm or refute each hypothesis.

**Check before proceeding:** Configuration presence does not establish runtime activation. Distinguish collection failures from product failures, and distinguish live compression from unrelated processing. Do not infer database loss from a smaller provider payload. Leave unresolved causes open pending persisted evidence.

## 3. Verify persisted session evidence

load hermes-session-db with skill_read.

Resolve the affected profile's actual database and inspect its current schema before applying the sub-skill's query patterns. Use read-only inspection to answer the evidence request, correlating session/message identifiers and tool-call relationships where relevant. Check search behavior separately from whether the underlying records exist.

Return an evidence packet containing bounded findings, recoverable record pointers, and a confirmed/refuted/unresolved status for each hypothesis. Distinguish session persistence, provider-visible context, and derived memory/search layers. Verify which services are currently active before using historical architecture diagrams.

**Check before concluding:** Persisted records alone do not establish what the provider received. Reconcile them with the request and runtime evidence from steps 1–2. If evidence conflicts, return the specific discrepancy to the relevant earlier step; avoid repeating the entire chain without a new question.

## Completion and remediation

Produce one diagnosis linking symptom, responsible boundary, supporting evidence, and remaining uncertainty. Recommend the smallest justified correction using the responsible sub-skill's procedure. This workflow does not itself authorize database edits, service restarts, or deployment.

For an authorized change, repeat the affected measurements under comparable conditions and check context retention and recovery alongside payload savings. Report implementation, live activation, and quality validation separately. If required evidence is unavailable, finish with the bounded finding and exact missing evidence rather than claiming a verified cause.
