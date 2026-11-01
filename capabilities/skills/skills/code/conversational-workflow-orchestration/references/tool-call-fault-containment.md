# Scena ReAct tool-call fault containment

## Scope

Use this reference when a conversational agent dispatches model-generated tool calls from a ReAct loop, especially with Cloudflare Workers, D1 persistence, asynchronous media providers, or Telegram webhook retries.

## Failure mechanism observed

In Scena, `workers/api/src/agent.ts` originally parsed `toolCall.function.arguments` directly in `runAgentTurn`, then parsed the same value again inside `executeTool`. Invalid JSON from the model raised a `SyntaxError` and aborted the whole inbound turn.

`executeTool` also had no per-call exception boundary. A D1/provider exception could escape through `handleAgentMessage`, preventing a correlated tool observation and risking channel-level webhook retries. State advancement and asynchronous stopping were based primarily on the requested tool name rather than on a proven successful submission.

## Repair pattern

1. **Parse once before dispatch.** A helper returns either `{ ok: true, args }` or `{ ok: false, error }`. Require a non-array object.
2. **Correlate invalid input.** Append one result for the original tool-call ID with `success: false`, `state: invalid_tool_arguments`, the tool name, and a generic user-safe message. Do not echo malformed arguments.
3. **Pass parsed arguments into the dispatcher.** Remove duplicate parsing from `executeTool`.
4. **Catch per tool call.** Convert thrown errors to `success: false`, `state: tool_execution_failed`; clip the exception message and omit stacks and raw provider bodies.
5. **Keep error logging subordinate.** Wrap `tool_error` persistence separately so a logging failure cannot mask the tool failure.
6. **Preserve state on failure.** Update the client/workflow state only when the tool result is not explicitly failed.
7. **Classify async from outcome.** Invalid or failed calls to normally asynchronous tools must re-enter reasoning rather than returning `Traitement en cours…` or creating a phantom callback expectation.
8. **Do not blindly retry mutations.** Before retrying generation, billing, publishing, or storage writes, add a durable idempotency/correlation key and reconcile any remote submission whose outcome is unknown.

## TDD reproduction

Add behavioral tests in `tests/agent-communication.test.mjs` through the public `handleAgentMessage` path rather than unit-testing the parser alone.

### Malformed arguments

- First mocked model response requests a real tool with truncated JSON arguments.
- Before the fix, assert the test fails with the JSON parser exception.
- After the fix, assert the second model request contains `invalid_tool_arguments` and the original tool name.
- Assert the turn returns the model's corrective natural-language response.

### Tool execution exception

- First mocked model response requests a persistence-backed synchronous tool with valid arguments.
- Make only that D1 write throw a deterministic exception; keep context assembly and agent logging functional.
- Before the fix, assert the exception escapes the turn.
- After the fix, assert the next model request contains `tool_execution_failed` and the tool name.
- Assert the durable client state remains unchanged.

Useful commands:

```bash
node --experimental-strip-types --test \
  --test-name-pattern='malformed model tool arguments' \
  tests/agent-communication.test.mjs

node --experimental-strip-types --test \
  --test-name-pattern='tool execution failures are isolated' \
  tests/agent-communication.test.mjs

node --experimental-strip-types --test tests/agent-communication.test.mjs
npm run test
cd workers/api && npx wrangler deploy --dry-run
```

Run the focused agent suite first. Run workflow/media regressions independently, then the full suite; classify unrelated pre-existing failures rather than altering them to manufacture green output.

## Acceptance checklist

- Each requested tool call has exactly one correlated tool result.
- Invalid arguments and thrown exceptions do not reject the inbound agent turn.
- Tool errors contain no stack, credentials, or raw malformed payload.
- Failed tools do not advance client, step, run, billing, or async-pending state.
- The next model iteration can explain or correct recoverable failures.
- Costly/mutating retries require idempotency, not optimism.
- Worker dry-run bundles successfully after the change.
