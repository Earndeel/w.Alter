# Agentic worker validation matrix

Use this reference after the implementation compiles. Keep the evidence attached to a run, not to a model marketing claim.

| Layer | What to exercise | Minimum evidence | Status to report |
|---|---|---|---|
| Facade | profile, objective, context, tool allow-list, reasoning, limits | deterministic request object and validation tests | measured locally |
| Resolver | target model → provider/base URL/api mode | resolved bundle with key presence only | observed in code/test |
| Transport | payload, tools, reasoning, headers, stream, route-specific fields | sanitized final kwargs or request dump | wire contract verified |
| Adapter | text, reasoning, function call, usage, raw metadata | normalized event plus preserved raw event | parser verified |
| MODE_3 | two dependent tool calls in one child trajectory | call A → output A → call B using A → final | agentic loop verified |
| Failure | bad ID, provider 4xx/5xx, empty stream, timeout, cancellation | bounded error and no false success | failure path verified |
| Budget | max turns, wall time, known cost/credits | stop or failed result with status/source | enforced or explicitly unknown |
| Integration | real `delegate_task(agent="<worker>", objective=...)` | child model/route, tool trace, final result returned to parent | Hermes E2E verified |
| Economics | same task on candidate and fallback | successful-task cost, retries, latency, quality | promotion decision |

## Deterministic MODE_3 recipe

1. Define two harmless tools with strict, small schemas: `lookup_seed` and `derive_value`.
2. Make the first tool return a fixed value and require the second tool to consume it; do not accept prose that merely describes a tool call.
3. Run the existing child runtime with the worker provider and capture raw Responses events.
4. Dispatch the first function call through Hermes' normal tool registry.
5. Reinject the exact normalized function-output item expected by the active provider. For Kie Codex, verify the `fc_` identifier is identical on the replayed function call and output; never assume this for another Kie route.
6. Assert that the second call's arguments depend on the first output and that the final answer contains the deterministic result.
7. Repeat once with a provider error and once with cancellation/turn exhaustion; assert a bounded failure, not a fabricated final answer.

## Evidence ledger

Record these fields for every live smoke test:

- requested model ID and effective model ID;
- requested provider and effective provider;
- resolved base URL and `api_mode`;
- `stream` and response `Content-Type`;
- tool names, raw call IDs, normalized replay IDs, and output pairing;
- input/output/reasoning/cache token counters;
- cost amount, status, and source;
- latency, retry count, finish status, and cancellation state;
- raw-event artifact path or redacted trace handle.

A direct Kie generation proves only upstream reachability. A production claim requires the integration row to be verified through Hermes delegation and the final result boundary.
