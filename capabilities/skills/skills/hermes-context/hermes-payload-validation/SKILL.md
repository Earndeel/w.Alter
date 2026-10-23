---
name: hermes-payload-validation
description: Production-grade validation of Hermes provider payloads, prompt slimming, tool-result digests, exact_recall, and cache-hit behavior.
created: 2026-07-04
updated: 2026-07-04
---

# Hermes Payload Validation

Use this when Monsieur asks for production validation of Hermes prompt/context changes, especially payload slimming, prompt caching, tool-call pairing, exact recall, or cost/token metrics.

## Principle

Unit tests are not enough. Validate the actual provider request body emitted by a real Hermes run after middleware, transport conversion, cache-control insertion, sanitization, and prompt slimming. Otherwise one is merely admiring a mock. Charming, but useless.

## Required workflow

1. Enable request dumping for the validation run:
   - `HERMES_DUMP_REQUESTS=1`
   - keep the feature flag under test enabled, e.g. `HERMES_WIRE_PRUNE=1`
2. Build or reuse a real Hermes session containing raw heavy tool outputs in `state.db`:
   - multiple `skill_view` results, including a duplicate skill
   - heavy `execute_code` output
   - heavy `terminal` output
3. Run a real Hermes turn through `AIAgent.run_conversation(...)` or the normal CLI/gateway path.
4. Capture the emitted request dump. Search both locations:
   - `/root/.hermes/sessions/request_dump_*.json`
   - `/root/.hermes/logs/request_dump_*.json`
5. Normalize provider payload shapes before metrics:
   - Chat Completions: `request.body.messages`; `role=tool` is explicit
   - Codex Responses: `request.body.input`; count `type=function_call_output` as logical `role=tool`
   - Count `request.body.instructions` as `role=system`
6. Compare two views:
   - raw unslimmed transcript restored from `state.db`
   - actual post-patch provider payload from the request dump
7. Verify exact recall from a `state_db://...` found in the provider payload:
   - call `exact_recall(state_ref=..., include_raw_tool_result=True)`
8. Verify raw ledger invariance:
   - compare raw tool row lengths or hashes in `state.db` before and after provider calls
9. Run two similar consecutive turns in one live agent session to measure real provider cache-hit deltas.
10. Re-run targeted tests after any validation-script-driven code patch.

## Metrics to report

- total prompt tokens
- cached tokens
- non-cached tokens
- estimated cost and cost status/source
- percent by role: system, user, assistant, tool
- number of tool messages
- total logical tool-role chars
- top 10 heaviest messages
- number of raw tool results over 4000 chars still present in provider payload
- number of `[TOOL RESULT DIGEST]`
- number of `state_ref`
- number of full `skill_view` contents still present
- number of duplicate `skill_view` loads deduped
- provider acceptance and tool-call pairing status
- exact recall success/failure
- raw `state.db` source unchanged yes/no
- cache hit run 1 vs run 2

## Acceptance targets for tool-result slimming

- Logical tool role below 15-20% of provider payload.
- No large raw `skill_view` content after the turn where it is used.
- No raw tool output over 4000 chars in provider payload after digestion.
- `state_ref` present for every digested tool result.
- `exact_recall` can recover a precise old raw tool result.
- Consecutive similar runs show real cache hits when using normal prompt/context.

## Fresh-session wire validation gate

When validating a context or prompt change after a long session has been resumed, do not use the resumed session as proof of the new system prompt: its persisted prompt/cache can legitimately contain pre-change USER/MEMORY/skills state. Start a fresh session after the reload/reset boundary.

1. Verify the candidate model ID and route first. For a validation-only provider override, pass `--model` and `--provider` on the test invocation rather than changing permanent configuration; record the route and restore config afterward.
2. Temporarily enable the final-payload dump, run the normal Hermes CLI path, and distinguish real `preflight` dumps from paired `context_report_test_payload` instrumentation dumps. The former is the wire evidence.
3. Normalize transport shape before reporting. OpenRouter Chat Completions may carry the permanent prompt as `messages[0].role=developer`; do not interpret a reporter's `system_prompt: 0` as proof the permanent prompt is absent. Measure the developer/system envelope directly and report diagnostic subcomponents separately: skills index, Hindsight, USER.md, MEMORY.md, and SOUL.md.
4. Use one fresh session for A/B/C: capture A before tool calls, perform deliberate read-only batches including heavy terminal/read_file/search_files/skill_view results, capture B, repeat for C. Compare provider-view totals and tool-result chars, not raw ledger growth. Ignore duplicate test-payload dumps when selecting checkpoints.
5. Verify explicit invariants on every checkpoint: USER.md and MEMORY.md are absent globally unless explicitly retrieved; the tool working set stays within its configured cap; no stale full skill body remains after its consumption turn; raw ledger rows remain available; and the provider is accepted before claiming cache/token evidence.
6. Restore `dump_payload: false` even when the provider call succeeds. Do not broaden validation into Context Manager refactoring or schema slimming; treat tool-schema optimization as a separate class of work.

The reusable session-specific recipe and evidence notes live in `references/fresh-session-wire-ab-validation.md`.

## Pitfalls

- Do not report helper-level or unit-test metrics as production validation.
- Do not inspect only `state.db`; it is the raw ledger by design, not the provider payload.
- Codex Responses reshapes tool calls into `function_call` / `function_call_output`; map those back to assistant/tool roles for fair metrics.
- Request dumps may be written under `/root/.hermes/sessions/`; do not assume `/root/.hermes/logs/` only.
- If the harness disables context files, memory, or tools, cache metrics are not representative of a normal Hermes run.
- After successful tool slimming, the dominant payload can become `system`; then the next optimization target is persistent prompt/project context, not more tool trimming.
- Digests must preserve enough semantics: tool name, call id, status, summary/key points/paths when budget allows, `state_ref`, and raw availability.

## Support files

- `references/production-payload-validation-2026-07-04.md` records the first production run pattern and observed metrics.
