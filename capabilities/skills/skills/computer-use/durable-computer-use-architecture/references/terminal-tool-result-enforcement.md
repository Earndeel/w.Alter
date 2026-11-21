# Direct terminal reply — validated pattern

## Why this exists

A terminal tool result may already contain the exact safe message the user must
receive. Calling the model again solely to paraphrase it adds latency and cost.
The optimization is safe only when disclosure is an explicit producer-granted
capability rather than an inference from a generic `message` field.

## Two independent decisions

1. **Is the tool phase terminal?**
   - requires `completion_known: true`;
   - explicit `terminal: true` is strongest;
   - known final statuses may still stop tool dispatch for the legacy text-only
     continuation;
   - ambiguous negatives remain non-terminal.
2. **May Hermes disclose text without a model?**
   - requires all of `completion_known=true`, `terminal=true`, a non-empty
     `user_message`, and `safe_to_return=true`;
   - never promote ordinary `message` automatically.

```text
tool result
   |
   +-- terminal? no --> normal loop
   |
   +-- terminal? yes
          |
          +-- certified safe user_message? yes --> persist + direct final
          |                                      0 extra provider calls
          |
          +-- no --> one continuation with tools=[]
```

## Security gates

Before the direct path, reject:

- any payload with an `error` value or failure/internal-error status;
- messages changed by `redact_sensitive_text(..., force=True,
  redact_url_credentials=True)`;
- traceback/stack-trace text;
- backend/internal diagnostics and transport identifiers;
- empty or non-string messages.

The direct path should return the original certified text, not a redacted
variant: if redaction changes it, fall back to the model continuation. That
avoids silently delivering a technically mutilated message while still
preventing raw disclosure.

## Producer boundary

The generic classifier consumes the contract, but each tool owns whether to
grant it. For Computer Use, certify only a narrow, known-complete, error-free
`needs_user_input` result at the high-level `computer_use(action="goal")`
boundary. Do not change goal routing, AX policy, target selection, or the model-
facing front door merely to add direct reply.

A different tool can use the same contract, provided its producer makes the
same explicit safety commitment.

## Agent-loop insertion

After tool execution and canonical tool-result persistence, but before another
provider request:

1. read the first terminal classification recorded for the turn;
2. if its safe direct text exists, append an assistant message;
3. flush/persist it;
4. set a distinct exit reason such as
   `terminal_tool_result_direct_response`;
5. log measured `direct_final_overhead_ms`;
6. break the loop before request construction.

If no direct text exists, leave the established terminal enforcement path
unchanged: the next request is text-only (`tools=[]`), stale returned tool calls
are not dispatched, and terminal state resets on the next user turn.

## Regression matrix

| Case | Provider calls | Tool behavior |
|---|---:|---|
| terminal + full safe contract | 1 | initial tool only; direct final |
| terminal without `user_message` or safe flag | 2 | second request has `tools=[]` |
| known terminal status but no explicit `terminal=true` | 2 | no direct disclosure |
| non-terminal | normal | tools remain available |
| internal error | 2 | raw internals absent from final |
| stack trace or credential-shaped safe message | 2 | direct path rejected |
| Computer Use `needs_user_input` | 1 | generic direct contract |
| another tool with full contract | 1 | same generic behavior |
| legacy `message` only | 2 | never treated as capability |

Assert both request count and actual dispatch count. A test that merely checks
the final string can miss an expensive second request.

## Natural smoke and measurement

Use an ordinary session with no special skill/toolset restriction and the exact
user prompt. Retain the verbose trace. Report:

- provider request/response count;
- model-facing tool-call count and exact first action;
- forbidden extra tools (`skill_view`, terminal, session history, vision,
  capture, clicks);
- first-model latency;
- Computer Use latency;
- direct-final overhead;
- end-to-end latency;
- total input/output tokens.

The acceptance trace is:

```text
API Request #1
  -> computer_use(goal)
tool result
  -> needs_user_input + explicit safe terminal contract
DIRECT FINAL RESPONSE
API Request #2 does not exist
```

Run the smoke after the last source edit. A benchmark taken before a late
security hardening change is supporting evidence, not release evidence.

## Verification discipline

- Compile every touched Python module immediately after structural loop edits.
- Run focused terminal-result tests plus Computer Use routing, AX, delivery-
  ladder, backend registry, and front-door regressions.
- Use the project’s canonical test wrapper or environment. A global suite run
  under a different interpreter can fail during collection because optional
  extras are absent; report that honestly, but do not treat it as a regression
  in the changed code without evidence.
- Keep unrelated dirty-worktree changes out of the verdict.
- Freeze the orchestration only after the exact final source has a fresh natural
  trace and the focused regression matrix is green.
