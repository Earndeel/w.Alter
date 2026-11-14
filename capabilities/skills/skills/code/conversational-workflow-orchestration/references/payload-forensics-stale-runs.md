# Payload forensics: stale workflow run contaminating a live turn

Use this reference when the final reply mentions the wrong step, claims a transition that did not occur, or keeps asking for approval after approval was given.

## Forensic principle

If the raw provider request was not persisted, reconstruct the effective payload from the deployed prompt builder and durable state. Do not infer it from the assistant's prose alone.

Trace in this order:

```text
assembled tenant context
→ workflow execution lookup
→ system prompt builder
→ planner-plan injection
→ deterministic tool gate
→ D1 mutation and trace event
```

## Scena case pattern

A current UGC conversation had:

- client runtime state `idle`;
- no configured active project;
- current conversation summary describing a new brief;
- an unrelated historical run still marked `waiting_async`;
- its linked video job already marked `archived_stale`.

The runner selected that old run solely because its status matched the active-status query. The resulting payload contradicted itself: current brief and no active project in one section, then an authoritative historical `Build hook prompt` step in another.

The model attempted to persist the new brief, but the workflow tool gate rejected `record_project_plan` because the historical run was not `running`. A planner plan had already been generated and remained authoritative for the next ReAct iteration, so the model asked for validation of state that had never been saved. The next approval phrase was classified as non-execution approval, and the stale run was not in an approvable status. The assistant finally claimed the validation was recorded although there was no write.

## D1 evidence checklist

Inspect together, not one table at a time:

- `clients`: `state`, `context`, `summary`;
- tenant config: active project ID and generated user/memory context;
- projects: status, workflow ID, updated timestamp;
- workflow runs: status, current step, last tool/job, trigger message;
- workflow step runs: statuses, inputs, outputs, attempts;
- workflow trace events: proof of actual transitions;
- linked image/video/voice jobs: terminal, archived, failed, or pending state;
- agent logs: internal thought, planner plan, final response.

A state claim is proven only by the mutation row or trace event. Agent prose and planner output are not evidence of execution.

## Required invariants

1. An active run must belong to the active/current project, or be explicitly resumed by ID.
2. Active-run lookup must reject stale runs by age and reject runs whose linked async job is terminal, failed, or archived.
3. Archiving an async job must reconcile its run and step in the same maintenance operation.
4. Non-production persistence tools such as project/brief recording must not be blocked by an unrelated stale production run.
5. Brief approval and launch/spend approval require separate classifiers and transitions.
6. Tool-less steps need an explicit deterministic completion mechanism; they must never linger in `waiting_async` because an unrelated tool was recorded against them.
7. Client-facing text may say “recorded”, “approved”, “started”, or “completed” only after the corresponding durable mutation succeeds.

## Regression matrix

- stale `waiting_async` run + archived linked job is ignored or reconciled;
- stale run from project A cannot affect a new conversation for project B;
- project recording remains available during consultation despite unrelated historical runs;
- brief approval persists the prepared project but cannot spend credits;
- launch approval starts execution only from prepared durable state;
- no-tool step approval records a trace event and advances exactly once;
- failed/blocked persistence cannot produce a success-status message;
- payload snapshot/assertion verifies current project, run, step, and job are mutually consistent.
