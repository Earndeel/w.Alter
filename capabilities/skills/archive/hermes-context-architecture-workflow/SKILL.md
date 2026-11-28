---
name: hermes-context-architecture-workflow
description: Use when diagnosing or redesigning Hermes prompt payloads, context growth or compression, and session database persistence as one connected investigation.
type: workflow
requires: [hermes-payload-architecture, hermes-context-management, hermes-session-db]
---

# Hermes Context Architecture Workflow

Use this workflow when a Hermes investigation spans prompt composition, context management, and persisted session history. Execute the steps in order because each step produces the scope and evidence needed by the next one.

## Workflow contract

The workflow has three ordered stages:

1. Establish the intended payload architecture and the boundaries of the problem.
2. Diagnose runtime context growth, compression, pruning, and injection behavior within those boundaries.
3. Verify persisted evidence and correlate the runtime diagnosis with SQLite session history and external memory layers.

At every stage, load the corresponding sub-skill with `skill_read` before applying it:

```text
load hermes-payload-architecture with skill_read
load hermes-context-management with skill_read
load hermes-session-db with skill_read
```

Do not substitute a later stage for an earlier one. If a stage cannot establish its required handoff, record the gap and continue only with conclusions that the available evidence supports.

## Step 1: Define the payload architecture

Load `hermes-payload-architecture` with `skill_read`.

Use it to classify the reported problem across the relevant payload layers and system boundaries. Establish:

- Whether the issue concerns the static prefix, selected dynamic context, evidence, raw recent history, latest-user-message authority, or more than one layer.
- Which inputs are supposed to be cacheable, selected, recoverable by pointer, or excluded from the provider request.
- Whether historical summaries and persistent memory are descriptive references or are accidentally acting as task triggers.
- Which skills, tools, memory cards, and history segments should be selected for the current intent.
- Whether the investigation covers the whole harness or only one provider/request path.

Produce a `payload architecture handoff` containing:

- The suspected layer or boundary.
- The expected behavior at that layer.
- The observed symptom and its trigger.
- The measurements or artifacts required to distinguish prompt bloat, bad selection, compression loss, transport duplication, and persistence growth.
- Any relevant runtime dimensions: platform, cwd, enabled tools, provider family, model, and session.

### Step 1 checks

Before proceeding, verify that:

- The latest user message is identified as the active action source.
- Historical context is treated as reference material unless explicitly resumed.
- Static, dynamic, evidence, raw-tail, and persistence concerns are not being mixed into one unexplained token total.
- Provider-specific observations are labeled as such when the requested scope is broader than that provider.
- The proposed measurements match the running gateway or session configuration rather than nominal defaults.

If these checks fail, refine the architecture handoff before diagnosing compression or querying storage.

## Step 2: Diagnose context management

Load `hermes-context-management` with `skill_read`.

Pass the `payload architecture handoff` to this stage. Use it to inspect the runtime path that builds, compresses, prunes, and sends context. Determine whether the observed behavior comes from:

- Oversized tool or file outputs.
- Repeated skill, memory, project-context, or system-prompt injection.
- Failed, skipped, or misconfigured live compression.
- Incorrect threshold or model-specific compression behavior.
- Lossy pruning without recoverable evidence.
- Invalid provider message or tool-call/result pairing.
- A cached system prompt that has not reflected changed persistent files or configuration.

Collect measurements that separate fixed prompt cost, dynamic history, tool schemas and results, cache reuse, compression output, and persistence footprint. When evaluating a proposed change, preserve enough recent raw context and evidence pointers to test answer quality and recovery.

Produce a `context management handoff` containing:

- The confirmed or rejected runtime cause.
- The exact stage where size, duplication, omission, or stale state appears.
- Relevant configuration and process-restart requirements.
- Before/after payload or token measurements when a change is proposed.
- Any session IDs, message ranges, compression artifacts, logs, state references, or provider request captures needed for storage verification.
- Open questions that require checking canonical session history rather than reconstructed provider payloads.

### Step 2 checks

Before proceeding, verify that:

- Live session compression is distinguished from batch trajectory compression.
- Compression availability is proven by an actual auxiliary call or clear runtime evidence, not configuration alone.
- Pruning preserves provider message alternation and tool-call/result pairing.
- Historical summaries are inert and do not contain active-task wording that can create work.
- Selected skills and tool schemas are measured as part of the appropriate payload budget.
- Changes to persistent prompt files or startup configuration are not assumed to affect an already cached session.

If runtime evidence is inconclusive, mark the cause as unconfirmed and hand the uncertainty to the database stage instead of treating a plausible explanation as fact.

## Step 3: Verify session persistence and memory-layer boundaries

Load `hermes-session-db` with `skill_read`.

Pass the `context management handoff` to this stage. Use the session database as the canonical source for persisted conversation evidence. Query the relevant Hermes SQLite database and, when needed, compare it with Hindsight and Qdrant as separate layers.

Verify:

- Which sessions and message ranges contain the reported behavior.
- The roles, sizes, timestamps, and tool-call/result relationships in the affected range.
- Whether raw tool results, tool-call JSON, reasoning fields, summaries, or other message data are actually persisted.
- Whether `session_search` evidence comes from SQLite FTS rather than Hindsight or Qdrant.
- Whether extracted durable memory and semantic indexes contain derived information rather than verbatim session history.
- Whether database growth, snapshots, indexes, or auxiliary databases are being included in the requested storage estimate.

Use direct schema inspection and targeted queries when documentation or prior assumptions conflict with the live database. Preserve the distinction between logical text volume and physical storage volume, and label token estimates as approximate unless the target tokenizer was used.

Produce a `verified findings handoff` containing:

- Query scope and database paths.
- Confirmed rows, fields, relationships, and size measurements.
- Correlation or contradiction with the runtime context diagnosis.
- Clear separation of SQLite session history, Hindsight durable memory, and Qdrant indexing.
- Remaining limitations, missing observations, and confidence for each conclusion.

### Step 3 checks

Before completing the workflow, verify that:

- Tool calls and tool results are joined through their recorded correlation fields where applicable.
- A claim about persistence is based on direct schema or row evidence.
- FTS mirrors, snapshots, and vector indexes are not double-counted in logical-text estimates.
- Database evidence is not mistaken for the provider payload actually sent on a particular turn.
- Any remediation recommendation maps back to the payload layer and runtime stage that produced the symptom.

## Final report shape

Return the findings in this order:

1. The active symptom and its payload boundary.
2. The expected architecture from Step 1.
3. The runtime cause or bounded set of causes from Step 2.
4. The persistence evidence and memory-layer correlation from Step 3.
5. Measurements, confidence, and unresolved limitations.
6. Remediation ordered by impact: inert historical rendering and authority rules, selective retrieval, bounded schemas and layers, reliable compression and pruning, then storage or retention changes.

Do not claim that a fix is active because code, configuration, or offline replay exists. Distinguish implementation, activation in the running service, and measured quality or payload impact.
