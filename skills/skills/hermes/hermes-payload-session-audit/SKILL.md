---
name: hermes-payload-session-audit
description: "Use when auditing or redesigning Hermes prompt payloads requires session-history evidence, FTS5 investigation, or stored-token measurements to validate context and budget decisions."
type: workflow
requires: [hermes-payload-architecture, hermes-session-db]
---

# Hermes Payload and Session Audit

Apply this chain when a payload, compaction, caching, or context-selection question needs evidence from persisted Hermes sessions. For standalone payload design or database queries, use the relevant sub-skill directly.

Follow the order below. The sub-skills own implementation procedures; this workflow owns their handoffs and validation gates.

## 1. Frame the payload investigation

Load hermes-payload-architecture with skill_read.

Use it to identify the affected payload boundaries, establish the runtime scope, and define the hypothesis and acceptance criteria before querying session history.

Hand the next step an evidence brief containing:
- The user’s question and proposed explanation or change.
- Runtime, platform, toolsets, working directory, and relevant sessions or time range.
- Payload measurements already available and the missing evidence.
- Required session excerpts, recovery anchors, pairing checks, or stored-text estimates.
- Criteria for evaluating payload savings and retained context quality.

**Handoff check:** Distinguish provider payload measurements from database storage estimates. Confirm that the requested evidence can test the hypothesis; persistence alone cannot establish what reached a provider or benefited from caching. Mark unavailable measurements explicitly.

## 2. Collect session evidence and reconcile the findings

Load hermes-session-db with skill_read.

Use the evidence brief to inspect the applicable databases and retrieve only the evidence needed. Follow the sub-skill’s query and estimation procedures rather than reproducing them here.

Return an evidence package containing:
- Database identity, observed schema, query scope, and collection time.
- Session/message anchors supporting each finding.
- Relevant history and tool-call/result continuity findings.
- Token measurements or estimates with method, inclusion boundaries, and uncertainty.
- Evidence gaps and any disagreement with the payload hypothesis.

**Evidence check:** Verify the live schema and applicable deployment state before relying on dated examples. Keep logical text, physical storage, and provider-input figures separately labeled. Treat missing search hits as inconclusive until search coverage is checked.

Reconcile this package against step 1’s acceptance criteria. If evidence changes the hypothesis, return to step 1 with the specific discrepancy and repeat only the affected investigation. If provider measurements or quality checks remain unavailable, report the limitation instead of declaring validation complete.

## Completion

Deliver the supported diagnosis or proposed change, evidence anchors, comparable measurements, and unresolved limits. Distinguish implementation, live activation, and quality validation. This workflow does not itself authorize production changes.
