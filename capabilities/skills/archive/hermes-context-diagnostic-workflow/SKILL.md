---
name: hermes-context-diagnostic-workflow
description: Use when Hermes context bloat, duplicated injection, or missing compression requires tracing prompt architecture through runtime behavior to persisted session evidence.
type: workflow
requires: [hermes-payload-architecture, hermes-context-management, hermes-session-db]
---

# Hermes Context Diagnostic Workflow

Use this chain for investigations that need architectural attribution, live compression diagnosis, and verification against session history. For an isolated schema question or a single configuration lookup, use the relevant sub-skill directly.

Run the steps in order. Keep one evidence ledger containing the symptom, runtime/profile, session identifier, observation window, measurements, evidence pointers, hypotheses, and unresolved questions. Load implementation details from the sub-skills rather than reproducing them here. Treat their dated examples as hypotheses to verify against the current deployment; current instance rules take precedence.

## 1. Establish the payload boundaries

load hermes-payload-architecture with skill_read.

Apply it to identify which payload layers and runtime boundaries could explain the reported symptom. Establish a baseline for the affected runtime and distinguish provider-visible payload from persisted history. Define what evidence would confirm or reject each suspected cause and what successful remediation must preserve.

Handoff to step 2: the scoped layer map, baseline measurements with collection conditions, ranked hypotheses, relevant session pointers, and preservation criteria.

Check before proceeding: measurements correspond to the affected platform, profile, toolsets, and cwd; each hypothesis names a boundary that can be observed. Mark unavailable measurements explicitly. Do not attribute a provider-payload problem solely from database size.

## 2. Diagnose the live context behavior

load hermes-context-management with skill_read.

Use the architectural handoff to select the relevant diagnostic branch. Compare the running process and observed compression or injection behavior with the baseline. Separate configuration on disk from configuration loaded by the process, and distinguish a collection failure from a product failure. Keep this pass diagnostic unless changes are already within the requested scope.

Handoff to step 3: observed runtime behavior, supporting log or request pointers, candidate causes, and precise persistence questions. Include the session IDs, time ranges, message anchors, and expected evidence needed to test each question.

Check before proceeding: the evidence concerns the live session mechanism under investigation; documented defaults alone do not establish runtime behavior. Any suspected loss, pruning, or duplication must identify whether it concerns the provider request, resumed history, or stored records.

## 3. Verify against persisted session evidence

load hermes-session-db with skill_read.

Use the persistence questions from step 2 to inspect the actual database schema and query the identified sessions read-only. Correlate stored records with runtime observations using message anchors, timestamps, and tool-call identifiers. Verify which records are present and recoverable without assuming that every stored field entered the provider request. Verify current memory-layer roles before using historical Hindsight or Qdrant comparisons.

Handoff to synthesis: evidence pointers for each tested hypothesis, discrepancies between persisted and provider-visible history, confirmed findings, rejected explanations, and remaining uncertainties.

Check before concluding: queries targeted the correct profile and session, relevant call/result relationships were checked, and search misses were distinguished from absent records. Database contents alone cannot prove the exact payload sent to a provider.

## Close the investigation

Reconcile all three handoffs into a causal explanation linking the affected payload boundary, observed runtime behavior, and persisted evidence. If evidence contradicts an earlier hypothesis, return to that step with the specific discrepancy and repeat only the affected checks.

For authorized fixes, use the relevant sub-skill's procedure and validate against the original baseline and preservation criteria. Report implementation, live activation, payload effects, and retention quality separately. Finish with the finding, evidence pointers, validation results, and any unresolved limitation; do not claim success from token reduction alone.
