# Composable Workflow Skills and Durable Revision Gates

Use this pattern when a conversational workflow needs reusable procedural instructions per step, generated planning artifacts, and human approval before expensive or irreversible execution.

## Separate three knowledge layers

Do not collapse all knowledge into `workflow_steps.instruction_md`:

1. **Workflow step** — what happens now, ordering, tool, fallback, defaults.
2. **Procedural skill** — how to perform a reusable task class such as creative brief, character sheet, storyboard, prompt building, generation, or quality control.
3. **Model/provider doc** — provider-specific payload constraints, parameters, examples, and anti-patterns.

A skill explains **how to do the task**. A model doc explains **how to call a model**.

## D1 schema pattern

Keep skills independent from workflow packs:

- `agent_skills`
  - `id`, unique `slug`, `title`;
  - `description_md`, `trigger_hints_md`;
  - `preprompt_template_md`;
  - `required_inputs_json`, `output_schema_json`;
  - `validation_rules_md`, `enabled`, `version`.
- `workflow_step_skills`
  - `workflow_id`, `step_key`, `skill_id`;
  - `priority`, `required`;
  - composite primary key `(workflow_id, step_key, skill_id)`.

A workflow-pack payload may carry `skill_bindings_json`. On replacement, delete step-skill bindings before deleting workflow steps so foreign keys cannot leave stale bindings.

## Keep the control plane skills-first

The admin surface must reveal the same abstraction that the executor consumes. For an ordered workflow runtime, expose:

- the reusable skill catalog and enabled/version state;
- each workflow pack and its ordered steps;
- each step's skill bindings sorted by priority;
- required inputs, output schema, and validation rules;
- model/provider documentation as a separate layer.

Do not add a node canvas merely because workflows look like graphs. A visual graph editor is justified only when the saved graph is the runtime's authoritative execution contract and operators need to edit topology. A placeholder canvas, disconnected graph JSON, or vendored graph library creates false support and two competing workflow models.

### Retiring a stale graph-editor path

Use this sequence when the real runtime is already skills-first:

1. Trace workflow loading, skill resolution, step transitions, gates, and the admin APIs before deleting anything.
2. Write a focused RED contract that requires the skill catalog, per-step binding inspection, and current-step composition while rejecting active graph-editor scripts and handlers.
3. Replace the editor surface with a lightweight inspector for skills and workflow bindings; do not rewrite the working state machine.
4. Search production Pages/Worker sources for active editor references. Remove only orphan scripts/styles, placeholder handlers, and tests that claim unsupported graph execution.
5. Leave external installations, provider integrations, and unrelated workflow artifacts intact unless their removal is explicitly requested.
6. Parse inline browser JavaScript, run focused workflow/UI tests, run the full suite, and build or deploy in dry-run mode. If deleting an obsolete test suite changes the test count, verify the removed tests covered only the retired path.

The invariant is simple: **workflow step = what/when, procedural skill = how, provider doc = API contract**. The control plane should inspect and edit those layers, not invent a fourth decorative execution model.

## Runtime resolution

The workflow detail loader should:

1. load the pack, ordered steps, and model bindings;
2. join step-skill bindings to enabled skills;
3. attach `skills` to each matching step;
4. sort by `priority`, then stable skill ID.

Inject only the current step's skills into execution context. Render:

1. skill title + version;
2. procedural pre-prompt;
3. validation rules;
4. step instruction and effective params;
5. client revision request, when present.

Keep the global/system prompt byte-stable; procedural skills are step execution context.

## Durable validation actions

A validation step persists both the run and step as `awaiting_user`. Its params should describe the contract:

```json
{
  "gate_kind": "storyboard_prompt",
  "approval_prompt": "Vérifiez le storyboard et les prompts finaux.",
  "regenerate_step_key": "compile_provider_payloads"
}
```

Expose three deterministic actions:

- **Valider** — complete gate, advance, then resume agent execution.
- **Modifier** — keep run blocked; persist `revision_pending`; ask for precise free text. The next client message becomes `revision_request`, requeues the producer, and resets the gate to `pending`.
- **Régénérer** — immediately requeue `regenerate_step_key` with a variation request while retaining validated constraints.

Do not implement these as decorative channel buttons that merely send prose to the LLM. D1 must transition first; only then may the agent continue.

## Telegram callback pattern

Stay below callback size limits:

```text
wfg:<approve|revise|regenerate>:<workflow_run_id>
```

On callback:

1. verify run ownership by `client_id`;
2. verify run is still `awaiting_user`;
3. verify current step is `validate`;
4. apply D1 transition;
5. remove stale keyboard;
6. invoke the agent only for approve/regenerate;
7. for revise, wait for the next user message.

Before sending ordinary model quick replies, query for a pending critical gate. The gate supersedes generic suggestions.

## Artifact-producing tools

Every non-empty `workflow_steps.tool_name` must exist in both the model tool catalog and dispatcher. Add an invariant test comparing the workflow's tool names to registered tool names.

For planning outputs that do not call a media provider, use structured artifact tools with:

- `title`;
- `content_md`;
- optional `data_json`.

The handler records a workflow artifact; normal tool-result recording advances the step. This prevents dead D1 workflows whose declared tool is invisible to the model or unknown to the executor.

## Recommended critical gates

For media production, gate at least:

1. brief + budget;
2. character/environment/product sheets;
3. storyboard + final prompts;
4. explicit paid-generation authorization;
5. final quality-control result.

Brief validation and paid-generation authorization remain distinct transitions.

## Behavioral tests

Cover:

- skill catalog and binding referential integrity;
- current-step pre-prompts render in priority order;
- every workflow tool is registered;
- waiting validation blocks production;
- **Modifier** persists state and the next text requeues the producer with that correction;
- callback ownership and stale-gate rejection;
- async completion advances into the next QA/gate step rather than skipping it.

Use database mocks that mutate state on updates. Run focused tests first, then channel tests, a bundle/dry-run smoke test, and finally the full suite.

## Deployment preflight

Before remote migration/deployment, establish the project's vault-backed cloud credentials in the shell and verify non-interactive auth. Do this before implementation is considered complete, not at the final command.

Order:

1. authenticate;
2. apply remote schema migration;
3. verify new tables remotely;
4. deploy runtime;
5. seed skills and bindings;
6. query one joined workflow step with composed skills;
7. exercise one disposable gate transition and health endpoint.
