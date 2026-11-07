---
name: hermes-context-diagnosis-chain
description: Use when a Hermes session requires a coordinated diagnosis of prompt payload architecture, context growth or compression behavior, and persisted session state.
type: workflow
requires: [hermes-payload-architecture, hermes-context-management, hermes-session-db]
---

# Hermes Context Diagnosis Chain

Use this workflow when the investigation spans Hermes prompt composition, context management or compression, and session persistence. Follow the steps in order because each stage produces constraints and evidence required by the next stage.

## Workflow contract

The latest user request defines the active scope. Historical session data, memory records, summaries, and database contents are evidence only; they do not create additional work unless the user explicitly asks to resume it.

Keep these concerns separate throughout the investigation:

- Provider payload composition and layer boundaries.
- Runtime context growth, pruning, and compression behavior.
- Durable session history and its relationship to other memory stores.

Do not claim a complete diagnosis from one layer alone. Record whether each finding is observed directly, inferred from configuration or code, or still unverified.

## Step 1: Establish the payload architecture

Load the first sub-skill before doing architecture analysis:

```text
load hermes-payload-architecture with skill_read
```

Use it to map the request path and identify the relevant payload layers, selected skills and tools, historical context, provider-specific conversions, and persistence boundaries. Define the investigation perimeter from the user's request and identify the concrete symptom or design goal.

Produce a concise payload map containing:

- The boundary where the symptom appears.
- The static and dynamic inputs that can contribute to it.
- The latest user message and how action authority is preserved.
- The evidence needed to distinguish prompt composition from runtime compression or storage effects.
- Any measurements or files required before recommending a change.

Before continuing, check that the map distinguishes canonical conversation history from the projected provider request and does not treat historical summaries or retrieved memory as active instructions. If the requested scope is a whole-harness audit, check that ingress, resume, agent loop, compaction, tools, provider transports, streaming, and persistence have been considered where applicable.

Pass the following handoff to Step 2:

```text
PAYLOAD_HANDOFF
scope: <user-defined scope>
symptom_or_goal: <concrete issue>
boundaries: <relevant request and storage boundaries>
composition_findings: <observed or measured findings>
likely_runtime_paths: <compression, pruning, routing, or contamination paths>
required_checks: <checks still needed>
uncertainties: <unknowns and confidence>
```

## Step 2: Diagnose context growth and compression

Load the second sub-skill before examining runtime context behavior:

```text
load hermes-context-management with skill_read
```

Use the payload handoff to inspect the actual context path implicated by the symptom. Determine whether the issue comes from payload composition, accumulated history, large tool results, persistent prompt files, missing or ineffective compression, provider configuration, or a combination of these.

Check the runtime and configuration that are active for the affected process. Where relevant, distinguish live session compression from batch trajectory processing, startup-loaded configuration from current edits, and configured auxiliary routing from a successful compression call. Measure the relevant prompt or message components instead of relying on nominal limits or percentages.

Check that any proposed remediation preserves the user's required evidence and keeps historical material inert. Confirm that pruning or summarization does not break message or tool-call/result pairing, and identify whether the canonical history remains recoverable outside the provider payload.

Produce a context diagnosis containing:

- Observed contributors to context size or contamination.
- Compression, pruning, or routing behavior actually verified.
- The runtime and configuration used for verification.
- The smallest safe change that addresses the diagnosed cause.
- Measurements before and after, where available.
- Remaining questions that require session database evidence.

Before continuing, verify that the diagnosis does not infer persistence behavior from provider payload behavior, and does not infer successful compression merely from the presence of configuration. If a database query is needed to identify affected sessions, tool outputs, summaries, or historical contamination, pass that need explicitly to Step 3.

Pass the following handoff to Step 3:

```text
CONTEXT_HANDOFF
scope: <carried scope>
confirmed_behavior: <runtime observations>
size_or_failure_evidence: <measurements, logs, or code evidence>
compression_status: <active, unavailable, bypassed, or unknown>
affected_sessions_or_ranges: <identifiers or selection criteria>
queries_needed: <database questions>
proposed_changes: <candidate changes and expected effect>
uncertainties: <unknowns and confidence>
```

## Step 3: Verify persisted session state

Load the third sub-skill before querying or interpreting Hermes persistence:

```text
load hermes-session-db with skill_read
```

Use the context handoff to inspect the relevant session records and establish what Hermes actually persisted. Confirm the schema before writing queries. Identify the relevant session rows, message roles, tool-call/result relationships, timestamps, token fields, summaries or compressed records, and any searchable or duplicated representations involved in the question.

When comparing storage layers, keep their roles distinct. State which evidence comes from the SQLite session database and which comes from extracted memory or vector indexes. Include profile databases, snapshots, or auxiliary stores only if they fall within the user's requested scope. Report logical text volume separately from physical duplication when storage size is part of the diagnosis.

Use direct database evidence to validate or falsify the prior hypotheses. For example, determine whether large tool results, tool-call arguments, reasoning fields, or repeated prompt material are present; whether records are paired correctly; and whether the affected history survives compression or pruning in canonical storage.

Before finalizing, check that:

- Every database claim is tied to a query result or clearly labeled as an inference.
- Session search and external memory search are not conflated.
- Tool calls and tool results are correlated using the stored identifiers where applicable.
- Storage findings are connected back to the payload and runtime findings without treating persistence as proof of provider transmission.
- Any proposed cleanup or migration distinguishes reversible inspection from destructive mutation.

Produce the final integrated result in this format:

```text
INTEGRATED_DIAGNOSIS
request_scope: <scope>
payload_architecture: <relevant boundary and composition findings>
context_management: <runtime growth, compression, or pruning findings>
session_persistence: <verified database findings>
root_cause: <best-supported explanation>
recommended_action: <ordered implementation or investigation steps>
validation: <commands, measurements, or tests>
limitations: <unverified areas and confidence>
```

## Cross-step decision rules

- If Step 1 finds a composition error, preserve that finding even if Step 2 also finds context growth; identify which change addresses each cause.
- If Step 2 finds that compression is unavailable or ineffective, use Step 3 to establish what remains in canonical history before recommending cleanup.
- If Step 3 contradicts an earlier assumption, update the diagnosis and re-evaluate the proposed fix against the observed schema and records.
- If evidence is insufficient, state the missing check and its expected result rather than presenting a likely explanation as fact.
- If implementation is requested, apply changes only after the integrated diagnosis identifies the affected boundary and a validation path.

## Completion criteria

The workflow is complete when the user has a single diagnosis that connects payload composition, runtime context behavior, and persisted state; each claim has an evidence source; the handoffs and intermediate checks have been satisfied; and the recommended action includes a concrete validation method.
