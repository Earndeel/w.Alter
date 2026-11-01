# Scena Telegram + D1 reference pattern

This reference maps the class-level workflow-orchestration rules onto the Scena Cloudflare Worker codebase.

## Relevant surfaces

- `workers/api/src/index.ts` — Telegram guided intake, inline keyboards, recap, summary edits.
- `workers/api/src/agent.ts` — planner/executor prompts, tool blocking, project-plan persistence, workflow context refresh.
- `workers/api/src/workflow_runner.ts` — prepared-project gate, workflow-run creation, ordered transitions, async reconnection.
- `tests/telegram-ui.test.mjs` — intake and recap behavior.
- `tests/agent-communication.test.mjs` — approval/tool behavior and durable project recording.
- `tests/workflow-runner.test.mjs` — run creation, ordering, fallback, validation, async advancement.
- `tests/worker-regressions.test.mjs` — existing image/video generation commands remain compatible.

## Intake fields and Telegram stages

Scena's creative intake should support:

```text
objective → media → style → format → audience → angle
→ duration(video only) → count → CTA → constraints → summary
```

Free text can fill multiple fields. The next stage is always the first missing required field. For audience and constraints, accept natural text; for style/angle/duration/count/CTA, inline buttons remain useful accelerators.

The summary button should be `✅ Valider le brief`, not a generation-price confirmation. Show the estimated total cost in the recap and state that no credit is debited during brief validation.

After the button:

1. mark the guided intake confirmed;
2. ask the agent to call `record_project_plan` with `status=awaiting_validation`;
3. persist the selected `workflow_id` on the project;
4. ask for a separate launch confirmation;
5. create the run only on that later confirmation.

## Runner rules

`prepareWorkflowExecution(...)` should:

1. resume an existing active run first;
2. if it is `awaiting_user` and approval is explicit, complete the current no-tool step and reload;
3. otherwise load the active project, including `awaiting_validation`;
4. prefer `project.workflow_id` over the freshly ranked workflow;
5. remain in consultation if the project is absent, not prepared, or approval is absent;
6. create `workflow_runs` only when project status is `awaiting_validation` and approval exists.

An image URL must never be an alternate direct-execution signal.

`isWorkflowToolAllowed(...)` should return true only when:

```text
mode == workflow
AND run.status == running
AND currentStep.tool_name is non-empty
AND requestedTool == currentStep.tool_name
```

Consultation tools such as `record_project_plan` remain available before a run exists. Production tools for a selected workflow are blocked until the run exists.

## Approval semantics

Useful accepted forms:

- `Je valide`
- `Je valide le cadrage`
- `Ok lance`
- `Ok lance 5 angles du même produit`

Planning language must not authorize spend:

- `lance le cadrage`
- `prépare le plan`
- `conseille-moi`
- `j'ai une idée`

Normalize accents and punctuation, bound command length, detect a launch verb, and exclude planning vocabulary. The durable project gate remains mandatory even when text looks like approval.

## D1 mock pitfall

Transition tests must mutate the in-memory row when mocked SQL executes. Match SQL robustly; over-specific string matching can cause the mock to return no active run, making `prepareWorkflowExecution(...)` stay in consultation and falsely suggesting approval advancement failed.

For `UPDATE workflow_step_runs`, the bind order is:

```text
status, attempt_count, input_json, output_json, error_md, step_key, workflow_run_id
```

For `UPDATE workflow_runs`, mirror the production bind order and update the state object that subsequent `first()` calls return.

## Verification bundle

```bash
node --experimental-strip-types --test \
  tests/agent-communication.test.mjs \
  tests/workflow-runner.test.mjs \
  tests/telegram-ui.test.mjs

node --experimental-strip-types --test tests/worker-regressions.test.mjs

cd workers/api && npx wrangler deploy --dry-run
```

Run `npm test` afterward. If unrelated portal/admin HTML tests were already failing and those files were not touched, report them separately rather than weakening workflow tests to make the global count green.
