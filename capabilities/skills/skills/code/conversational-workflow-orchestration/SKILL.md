---
name: conversational-workflow-orchestration
description: Design and test validation-first conversational state machines that collect requirements, summarize a durable brief, obtain explicit approval, and execute deterministic workflow steps in order.
---

# Conversational Workflow Orchestration

Use this skill when an agent must guide a user through choices and constraints before executing a costly, destructive, or asynchronous workflow.

**References:** `references/scena-telegram-pattern.md` contains the Cloudflare Workers + D1 + Telegram implementation pattern; `references/payload-forensics-stale-runs.md` covers payload reconstruction and stale-run contamination when durable state contradicts the live conversation; `references/composable-skills-and-gates.md` covers D1-backed procedural skills, step composition, deterministic Valider/Modifier/Régénérer transitions, artifact tools, and deployment verification; `references/tool-call-fault-containment.md` records the Scena RED→GREEN recipe for malformed arguments and execution exceptions at the ReAct tool boundary.

## Core contract

Separate conversation from execution:

```text
collect → assess missing fields → summarize → validate brief
→ persist prepared project → confirm launch → execute ordered steps
→ pause at validation steps → continue only after approval
```

A prompt is not a state machine. Enforce every transition in code and persistence.

## 1. Define intake readiness

Create an explicit field contract for the workflow class. For creative production, normally include:

- objective and deliverable;
- audience;
- style/tone and creative angle;
- output format and duration;
- variant count and CTA;
- constraints, prohibited elements, legal limits, and an explicit `none` option;
- required source assets.

Infer obvious values from free text before asking questions. Ask only for missing fields. Buttons are accelerators, not the primary brain. Permit summary-stage edits without restarting the intake.

Do not mark a project ready merely because the model says it is ready. Compute readiness from structured fields or a deterministic checklist.

## 2. Use two distinct approval gates

Treat these as different events:

1. **Brief validation** — user agrees with the recap and assumptions. This is non-charging and persists a prepared project.
2. **Launch approval** — user authorizes execution or spend after the durable project exists.

A confirmation control must state exactly what it authorizes. Never label brief validation with a price if no generation occurs on that click.

Approval detection can accept standalone confirmations and concise launch commands, but it must reject planning language. Safety comes from the conjunction:

```text
explicit approval AND prepared durable state AND eligible workflow step
```

Do not rely on exact phrase matching alone, and do not treat attached media as permission.

## 3. Persist workflow identity

Persist the selected workflow identifier on the prepared project. A short later message such as `Je valide` carries no useful routing context, so execution must prefer the project's workflow over a fresh semantic ranking.

Recommended durable states:

```text
project: active → awaiting_validation → active/rendering → review
run: running → waiting_async | awaiting_user → running → completed/review
step: pending → running | awaiting_user → completed | failed
```

### Reconcile stale asynchronous state before prompt assembly

Never select an “active” run from status alone. Before injecting it into the model payload, verify that it belongs to the current active project and that any linked async job is genuinely pending. Ignore or reconcile runs whose job is terminal, failed, archived, or older than the runtime's stale threshold.

Archive/cleanup operations must update the job, workflow step, workflow run, and project coherently. Otherwise a historical `waiting_async` row can become an authoritative prompt instruction in an unrelated conversation.

When debugging a suspicious reply, compare the assembled tenant context, selected project, selected run/step, linked job, and workflow trace in one pass. Treat planner output and assistant prose as intent only: a validation or transition occurred only if the durable mutation or trace event exists.

## 4. Enforce ordered execution

For an active run:

- execute a tool only when run status is `running`;
- require the tool to match `current_step.tool_name`;
- reject every tool while status is `awaiting_user`;
- never advance state after a mismatched tool;
- branch to configured fallback only on failure;
- skip fallback nodes on normal success;
- persist run/step identity on asynchronous jobs.

A no-tool validation step must be explicitly completed before any later production tool can run. Record the approval message and a trace event, choose the next primary step, update project/run status, then reload execution state.

Refresh the workflow execution context on every agent iteration. A static system prompt becomes stale immediately after a synchronous tool advances the step.

### Keep the control plane faithful to the runtime

When the runtime already executes ordered steps with serialized skill bindings, expose that contract directly: catalog reusable skills, inspect each step's ordered bindings, and show input/output plus validation rules. Do not bolt on a canvas or graph-editor library unless the runtime actually persists and executes that exact graph and users genuinely need free-form topology editing.

Treat a placeholder visual editor as architecture drift, not harmless UI. To retire one safely, first trace the real workflow/skill loader and execution path, add a RED contract for the skills-first surface, remove only active editor references and orphan assets/tests, then verify browser-script syntax, focused behavior, the full suite, and a deployment dry run. Preserve the deterministic state machine, durable gates, provider documentation, and any external installation outside the repository unless its removal was explicitly requested. See `references/composable-skills-and-gates.md` for the detailed migration checklist.

### Contain tool-call faults at the orchestration boundary

Treat model-emitted tool calls as untrusted input and isolate failures per call:

- parse arguments exactly once before dispatch; accept only a JSON object, never arrays or scalars;
- convert malformed arguments into a correlated tool observation such as `state: invalid_tool_arguments` instead of throwing out of the turn;
- wrap each tool execution in its own exception boundary and return `state: tool_execution_failed` with a clipped error message, no stack, raw payload, credential, or secret;
- emit exactly one result for every tool-call ID so the next model turn receives an aligned transcript;
- make error logging best-effort: a logging outage must not replace or hide the original tool failure;
- continue the reasoning loop for recoverable synchronous failures, while avoiding automatic retries of costly or externally mutating tools until idempotency is proven.

A failed call must not advance `lastToolState`, complete a workflow step, debit credits, create a webhook expectation, or be classified as pending merely because its tool name is normally asynchronous. Decide whether an async operation is pending from the successful submission result, not from the requested function name alone. If the workflow defines a fallback, feed the structured failure into that transition deliberately.

Test this boundary RED→GREEN with at least: malformed JSON arguments, a persistence/provider exception thrown inside a tool, a failed asynchronous submission, preserved durable state, and a subsequent model turn that can explain or correct the failure.

## 5. Make the recap operational

The recap should show:

- selected values;
- limits and assumptions;
- ordered workflow stages;
- estimated total cost, including variant multiplier;
- what the next confirmation will do;
- what remains editable.

The user should be able to correct format, audience, angle, duration, count, CTA, and constraints from the recap.

## 6. Behavioral test matrix

Write tests before implementation for:

- missing fields prevent brief validation;
- media attachment without approval remains consultation;
- approval without a prepared project cannot create a run;
- prepared project plus approval starts at step one;
- planning language is not launch approval;
- concise explicit production command is launch approval;
- wrong tool and tools during `awaiting_user` are blocked;
- approval advances a no-tool validation step before later tools;
- sync success advances to next primary step;
- failure follows fallback;
- async completion reconnects and advances;
- generated jobs retain project/run/step metadata;
- recap total cost includes quantity and brief validation is non-charging.

Use realistic database mocks that mutate state on `UPDATE`; a mock that returns stale rows can falsely suggest the production transition is broken.

## Pitfalls

- **Prompt-only gating:** the model can ignore it. Add deterministic checks before tool execution.
- **Run creation from attached media:** context is mistaken for consent.
- **Fresh workflow selection on `Go`:** short confirmations route to the wrong workflow.
- **One ambiguous confirmation:** brief approval accidentally spends credits.
- **Static execution prompt:** the agent keeps acting on the previous step.
- **Tool result advances the wrong step:** recording success without checking tool identity corrupts the run.
- **Exact-string approval only:** legitimate concise commands fail, encouraging brittle workarounds.
- **Overbroad approval prefix:** `go prepare the plan` becomes spend authorization. Exclude planning vocabulary and require prepared state.

## Verification sequence

1. Establish and verify the project's non-interactive deployment credentials before remote work begins.
2. Run intake/approval unit tests.
3. Run workflow-runner transition tests.
4. Run agent/tool regressions, including the invariant that every declared workflow tool is registered.
5. Run channel/UI tests.
6. Run provider-generation regressions.
7. Build or deploy in dry-run mode.
8. Run the full suite and classify unrelated pre-existing failures separately.
9. Apply the remote schema migration, deploy, seed, query one joined workflow step, and exercise a disposable gate transition before claiming production completion.
