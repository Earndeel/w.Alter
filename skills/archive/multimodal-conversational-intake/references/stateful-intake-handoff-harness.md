# Stateful intake and deterministic planner handoff

## Reusable pattern

Use this pattern when one conversational model gathers a creative brief and a second model plans execution.

### Durable brief snapshot

Persist one mergeable JSON snapshot instead of relying on chat history or Markdown alone:

```json
{
  "version": 1,
  "known_fields": {},
  "inferred_fields": {},
  "evidence": [],
  "missing_decisions": [],
  "readiness": "exploring | framing | planning_ready"
}
```

Typical fields cover objective, deliverable type, product, audience, channel, creative direction, hook, CTA, aspect ratio, duration, quantity, success criteria, constraints, and exclusions.

Merge rules:

- confirmed facts override and remove the matching inference;
- new evidence appends and deduplicates rather than replacing prior media context;
- the latest `missing_decisions` list is authoritative;
- readiness is recomputed by deterministic code from production-critical fields;
- a model-provided `planning_ready` value is only a request, never authority;
- changing a validated brief invalidates its stale plan.

Persist the snapshot in a dedicated JSON column and ship the database migration before the Worker/code version that reads it.

### Separate tools by responsibility

Use three distinct transitions:

1. `update_creative_brief` merges facts, inferences, evidence, and unresolved decisions. It neither plans nor generates.
2. `record_project_plan` is accepted only after the deterministic readiness gate and invokes the planner once.
3. Production tools remain behind a separate explicit execution approval.

Do not force the intake tool on greetings, objections, or questions that add no project information.

### Deterministic planner gate

Immediately before planner invocation:

1. reload the active brief snapshot from the authoritative store;
2. recompute required fields and unresolved decisions;
3. if incomplete, return a synthetic `brief_not_ready` tool observation and do not call the planner or change project status;
4. if complete, pass the serialized snapshot to the planner;
5. promote the project to `awaiting_validation` only after a valid planner result is persisted;
6. on planner failure, return `planner_unavailable`, preserve the brief, and leave status unchanged.

Reloading at the handoff is important: an intake update and planner request can occur in the same multi-tool turn, while the context assembled before that turn is already stale.

### Natural visible conversation

The system prompt should constrain only visible behavior and tool policy:

- answer the client's point first;
- default to 1–2 short sentences;
- ask at most one highest-impact question;
- do not recap the brief unless validation or an explicit recap request requires it;
- buttons/choice payloads are optional and used only when discrete choices genuinely reduce effort;
- never request or expose chain-of-thought, internal JSON, or a visible reasoning block;
- infer low-impact defaults, but preserve them as inferences until confirmed.

Provider reasoning controls can remain enabled internally; visible chain-of-thought formatting is not a substitute for an agent loop.

### Active-project continuity

A short answer such as `plutôt 15 secondes` must inherit the active project snapshot. Attach active-project context by default for plausible continuations, but suppress it for clear small talk and explicit new-project intent. Otherwise the agent appears to forget the question it asked one turn earlier.

## Behavioral regression matrix

Test the assembled runtime behavior, not just source strings:

- tool schema separates known facts, inferences, evidence, missing decisions, and readiness;
- the Worker rejects a model's premature `planning_ready` claim;
- durable updates merge rather than overwrite prior evidence;
- a short natural reply receives the active structured brief;
- the real outbound prompt requires concise replies and contains no visible-thought contract or mandatory choices;
- a hostile early `record_project_plan` call produces zero planner calls;
- a complete snapshot invokes the planner exactly once;
- invalid planner output never promotes project status;
- execution remains blocked without its own approval;
- focused tests, adjacent workflow tests, database migration validation, and Worker dry-run all pass before deployment.

## Common mistakes

- Trusting a prompt-level gate without rechecking in code.
- Storing only free-form Markdown, forcing later models to reconstruct state.
- Reusing context assembled before an earlier tool in the same turn.
- Treating brief completeness as execution approval.
- Restoring eager planner behavior merely to satisfy an obsolete mock call sequence.
