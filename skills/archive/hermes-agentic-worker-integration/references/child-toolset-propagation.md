# Child toolset propagation

Use this recipe when a delegated Hermes child must execute tools.

## Boundary trace

Capture non-secret values at each transition:

| Boundary | Capture | Empty means |
|---|---|---|
| Requested | labels passed to `delegate_task` | caller did not request tools |
| Resolved | registry-resolved toolsets allowed by parent | alias/composite failure or permission denial |
| Registered | child function names | child builder lost the scope |
| Provider schemas | function definitions attached to the model request | model filtering or adapter conversion removed them |

Keep the trace temporary in a harness or behind debug logging. Never record keys, cookies, full prompts, or arbitrary arguments.

## Resolution and permissions

Resolve labels through the active Hermes registry before authorizing them. Typical mappings are `terminal` to terminal/process functions, `file` to functions such as `read_file` and `write_file`, and `code_execution` to `execute_code`; verify the live registry instead of hardcoding these examples. Resolve composite `includes` recursively or through the public resolver. Authorize aliases by their resolved function set.

The parent's effective tool scope is the security boundary. A child request may narrow that scope but must not widen it. If a lean test parent exposes only `delegation`, add the required child toolsets to the parent's trusted allowlist and instruct the parent model not to call implementation tools. Report denied requests with a safe reason instead of silently treating them as unresolved.

## Provider-free loop

Use a real child registry and tool handlers with only the model/provider boundary faked:

1. fake model emits `write_file`;
2. Hermes dispatches the call through the child bridge;
3. feed the real function output to the fake model;
4. fake model emits `read_file`;
5. feed the second output back;
6. fake model emits a final response.

Assert call/output pairing, real local results, dependent second-turn input, and the final response. Do not mock the registry or handlers.

## Live gate

A live proof needs non-empty resolved and registered scopes, non-empty provider schemas, multiple child model turns, paired function outputs, parent non-execution of the implementation task, and cleanup. A malformed or repeated supervisory delegation is a separate control finding; do not silently deduplicate it into the tool-loop evidence.

## Verification

Run the focused propagation regression and existing delegation/provider suites before a live call. Re-run the exact live path after changing the child builder or provider adapter; unit-level schemas alone do not prove the wire request.