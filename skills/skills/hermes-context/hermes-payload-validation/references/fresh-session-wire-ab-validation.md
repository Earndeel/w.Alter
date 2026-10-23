# Fresh-session real-wire A/B/C validation

Reusable evidence pattern for Hermes context/prompt validation.

## Invocation pattern

Use a fresh session and an explicit validation-only route; do not resume a historical session whose system prompt/cache predates the patch:

```bash
HERMES_DUMP_REQUESTS=1 HERMES_DUMP_REQUEST_STDOUT=0 \
  hermes chat \
  --model <verified-model-id> \
  --provider <verified-provider> \
  --reasoning none \
  --max-turns <bounded-value> \
  -q 'short deterministic prompt' -Q \
  --source context-fresh-validation
```

Temporarily set `compression.context_report.dump_payload: true` for the run, then restore it to `false` immediately afterward. If direct editing of the security-sensitive config is blocked, use the documented Hermes config path rather than weakening the guard.

## Selecting evidence

Hermes emits two related files per request:

- `reason: preflight` — the real provider request dump to measure.
- `reason: context_report_test_payload` — instrumentation/reporting copy; exclude it from A/B/C checkpoint selection.

The normal OpenRouter Chat Completions body can have:

```text
messages[0].role = developer
```

That developer message contains the permanent Hermes prompt. A report that only counts `system`/`instructions` may display `system_prompt: 0` while the actual permanent prompt is present. Measure the developer envelope directly, then inspect subcomponents:

- `SOUL.md` should be present in the permanent identity prompt.
- `USER.md` and `MEMORY.md` should not be present globally when `memory.inject_persistent_context: false`.
- `<available_skills>` should be bounded by the configured skills index cap.
- Hindsight should be counted separately and treated as targeted retrieval context.

## A/B/C recipe

- A: fresh request before deliberate tool calls.
- B: same session after a bounded read-only batch containing terminal/read_file/search_files/skill_view, including heavy deterministic output and a duplicate `skill_view`.
- C: same session after another bounded read-only batch and a comparable final request.

Use only `preflight` dumps and record:

```text
TOTAL_INPUT_TOKENS
OUTPUT_RESERVE / HEADROOM
tool result chars and tokens
loaded skill chars/tokens
tool schema tokens
USER/MEMORY markers
raw tool >4k count
```

The ledger is expected to grow. Acceptance is that provider-view tool results remain within the configured working-set cap and do not grow linearly with the raw historical tool rows.

## Provider usage

Only report `provider accepted: yes` and actual provider/cache input tokens when the session row or provider response contains accepted usage. An API request dump by itself is not proof of acceptance. Record the validation-only route explicitly and do not change the user's permanent model/provider configuration just to make the validation pass.

## Cleanup and proof

After C:

1. restore `dump_payload: false`;
2. verify the effective config and that `memory.inject_persistent_context` remains false;
3. compare raw tool-row counts/lengths or hashes before/after to prove the provider view did not mutate `state.db`;
4. run the targeted regression suite and `git diff --check`;
5. report schema slimming separately if tool schemas remain a large fixed prefix.

## Known interpretation

The semantic quality of automatic Hindsight recall depends on Hindsight upstream ranking when no usable score is exposed locally. Keep local work limited to budget enforcement, deduplication, and preserving upstream order; do not turn this validation into another Context Manager refactor.
