# Production payload validation — 2026-07-04

This reference captures the reusable technique and representative metrics from a real Hermes provider-payload validation after tool-result slimming work.

## Scenario

A real Hermes run was required after patching prompt-history slimming. The validation had to include several heavy tool results and capture the actual provider payload sent after render-layer transformations.

Workload used:
- 3 `skill_view`-shaped results, including a duplicate `hermes-agent` skill load
- 2 heavy `execute_code`-shaped results
- 2 heavy `terminal`-shaped results
- raw records persisted in `state.db`
- two consecutive real provider turns through `AIAgent.run_conversation(...)`
- provider: `openai-codex`
- model: `gpt-5.5`

## Artifact pattern

The validation script wrote artifacts under:

`/tmp/hermes_prod_payload_validation/<run_id>/`

Expected files:
- `before_payload_messages_raw.json` — raw unslimmed transcript view
- `provider_payload_run1.json` — actual request dump copied from Hermes
- `provider_payload_run2.json` — second actual request dump for cache comparison
- `validation_report.json` — summarized metrics and checks

Request dumps may originate from:
- `/root/.hermes/sessions/request_dump_<session>_*.json`
- `/root/.hermes/logs/request_dump_<session>_*.json`

## Payload normalization

For Codex Responses payloads:
- `request.body.instructions` = logical `system`
- `request.body.input[].type == function_call` = logical assistant tool call
- `request.body.input[].type == function_call_output` = logical `tool`
- `request.body.input[].role` = use provided role

Without this mapping, metrics incorrectly show `role=?` or miss tool output entirely.

## Observed before metrics

Raw unslimmed transcript:
- total estimate: 64,543 tokens
- role=tool: 90.20%
- tool chars: 232,879
- tool messages: 7
- raw tool results >4000 chars: 7
- full `skill_view` contents present: 3
- digests: 0
- state refs: 0

Top raw bloat sources:
- `skill_view hermes-agent`: 57,545 chars, twice
- `execute_code`: 29,139 chars, twice
- `terminal`: 21,169 chars, twice
- `skill_view hermes-context-management`: 17,173 chars

## Observed production payload run 2

Actual provider request after slimming:
- total prompt tokens: 33,994
- cached tokens: 31,744
- non-cached tokens: 2,250
- cache hit: 93.38%
- estimated cost delta: 0.0 USD; status `included`
- role percentages:
  - system: 93.41%
  - assistant: 2.23%
  - user: 0.14%
  - tool: 4.22%
- tool messages: 7
- tool chars: 3,864
- raw tool results >4000 chars: 0
- `[TOOL RESULT DIGEST]`: 7
- `state_ref`: 8
- full `skill_view` contents present: 0
- duplicate skill load deduped: 1

Validation checks passed:
- provider accepted payload; no tool-call pairing error
- exact recall recovered raw tool result via `state_db://...`
- long `skill_view` was not re-injected raw on the next turn
- duplicate `skill_view` used `[SKILL ALREADY LOADED]`
- raw source in `state.db` stayed unchanged
- digests retained tool name, call id, status, summaries/key points/paths when budget allowed, and state refs
- cache hit increased from run 1 to run 2

## Follow-up lesson

Once tool-role bloat dropped to 4.22%, the dominant payload became `system` at ~85k chars. Future optimization should inspect persistent prompt and project context before trying to shave more from tool results.
