---
name: gated-bitwarden-workflow
description: Use when a sensitive browser step requires Monsieur's intervention before continuing with Bitwarden-backed authentication, vault diagnosis, or recovery.
type: workflow
requires: [human-in-the-loop-gate, bitwarden-integration]
---

# Gated Bitwarden Workflow

## When this chain applies

Use this workflow when browser or account work reaches a human security boundary and the immediate continuation needs Bitwarden integration. Standalone vault maintenance without such a boundary belongs directly to bitwarden-integration.

## Ordered orchestration

### 1. Resolve the human boundary

load human-in-the-loop-gate with skill_read.

Provide the target domain, intended account, current browser state, requested operation, and sensitive boundary. Follow the loaded skill to obtain a valid continuation or stop.

Hand forward only the outcome, approved scope, target domain/account metadata, and fresh browser state. Never include secret values.

### 2. Check the handoff

Proceed only if the gate permits continuation and the refreshed page still matches the intended domain, account, and operation. Cancellation, unresolved challenges, expired approval, or ambiguous state block progression. Return to step 1 when a new gate is required; do not interpret human completion as general authorization for credential use or maintenance.

### 3. Continue through Bitwarden

load bitwarden-integration with skill_read.

Pass the validated handoff and select only the procedure needed for the requested continuation: authenticated browsing, credential selection, diagnosis, or recovery. Load references or further skills only as directed by that procedure.

Before acting, check that its selected account and target match the handoff, its prerequisites are satisfied, and the action remains within the authorized scope. If its credential path conflicts with the gate's constraints, stop that path and return to step 1 for an allowed human continuation; loading this skill does not relax the gate.

Hand forward non-secret results: session/account metadata, selected item identifier where relevant, operation status, and verification evidence or remaining blocker.

### 4. Verify and close

Check the result against the original task using the loaded skills' success criteria. Distinguish completed human intervention from successful authentication or repair. Report only verified outcomes and unresolved blockers.

If another sensitive boundary appears, repeat from step 1 before continuing. Carry forward task context, never a previous approval. Stop when the requested outcome is verified or a blocking condition remains; do not retry indefinitely.
