---
name: hermes-context-evidence-workflow
description: Use when a Hermes payload or compression investigation needs architectural scoping, live context diagnosis, and verification against persisted session evidence.
type: workflow
requires: [hermes-payload-architecture, hermes-context-management, hermes-session-db]
---

# Hermes Context Evidence Workflow

Apply this chain when context bloat, duplicated injection, missing compression, or suspected history loss requires tracing intended payload composition through runtime behavior to stored evidence. For an isolated architecture question or database lookup, use the relevant sub-skill directly.

Run the steps in the order below. This skill coordinates their outputs; load their procedures and relevant references rather than reproducing them here.

## 1. Establish scope and architectural expectations

load hermes-payload-architecture with skill_read

Use it to identify the affected payload layers and boundaries, define the investigation perimeter, and choose baseline measurements and retention requirements.

Hand to step 2: the current request, runtime/platform/profile/cwd, affected sessions and time range, layer map, baseline measurements, suspected mechanisms, and acceptance criteria for payload size and history safety.

Check before proceeding: measurements describe the actual runtime; fixed payload, dynamic context, provider requests, and persistence are distinguished. If the request covers the whole harness, the scope must cover its shared boundaries rather than only the provider exhibiting the symptom.

## 2. Diagnose observed context behavior

load hermes-context-management with skill_read

Use the architectural handoff to investigate injection sources, live compression behavior, configuration actually loaded by the running process, and relevant failure evidence. Produce a diagnosis and candidate remedy; defer changes that depend on unverified storage assumptions until step 3.

Hand to step 3: session identifiers, relevant timestamps or message anchors, measured contributors, compression events or failures, observed versus expected behavior, and explicit persistence questions needed to confirm or reject the diagnosis.

Check before proceeding: distinguish live compression from offline processing, configuration presence from successful execution, and estimated transcript volume from actual provider payload. Mark unsupported causal claims as hypotheses. Treat dated sub-skill examples as leads to verify against the installed version; current W.Alter contracts govern conflicting operational advice.

## 3. Verify against persisted session evidence

load hermes-session-db with skill_read

Use the handoff to inspect the applicable session database and live schema read-only. Retrieve bounded evidence around the supplied anchors, correlate relevant calls and results, and test the persistence questions. Verify any cross-store comparison against the deployment's current architecture rather than assuming historical services remain active.

Return to the diagnosis: evidence pointers, confirmed or rejected hypotheses, recoverability findings, and unresolved gaps. Separate what was stored, what retrieval exposed, and what the provider received; database presence alone does not establish prompt inclusion.

Check before concluding: evidence belongs to the same profile, session, and time range as the runtime measurements. A missing search hit alone does not prove deletion. If evidence contradicts step 2, revise the diagnosis; if it invalidates the layer map, revisit step 1 before proposing a remedy.

## Completion

Report the supported cause, baseline measurements, traceable evidence pointers, and the smallest remedy within the user's scope. If implementing a remedy is authorized, follow the relevant loaded sub-skill and current W.Alter modification rules, then repeat the affected runtime measurements and persistence checks. Declare success only when the original symptom improves and the agreed history-safety and recovery checks pass; distinguish offline validation, live activation, and answer-quality evaluation. If evidence is insufficient, state the unresolved question and the specific observation needed to resolve it.
