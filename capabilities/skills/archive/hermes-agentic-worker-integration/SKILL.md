---
name: hermes-agentic-worker-integration
category: devops
description: Use when adding a Hermes agentic worker.
version: 1.0.0
author: curator
metadata:
  hermes:
    tags: [hermes, agentic-worker, delegation, provider-routing, tool-loop, validation]
    related_skills: [hermes-provider-routing, hermes-delegate-task-routing, hermes-payload-validation]
---

# Hermes Agentic Worker Integration

Use this class skill when a stable Hermes/W.Alter orchestrator must delegate a complex subproblem to a model that owns an autonomous multi-turn tool loop, while the rest of Hermes keeps its current model, tools, persistence, cancellation, and accounting behavior.

## Always-on architecture rules

- Keep the primary orchestrator unchanged. A worker route is additive; never replace the default model globally merely to make a worker available.
- Reuse Hermes' existing `delegate_task` → child `AIAgent` → provider transport → tool-dispatch loop. Do not build a parallel agent loop unless the existing child runtime cannot express a proven requirement.
- Give the worker one objective and acceptance criteria, not a sequence of micro-managed subcalls. The worker owns inspection, tool execution, replanning, patching, and validation until it returns a result.
- Resolve the provider from the concrete target model at runtime. A mixed vendor block may need different base URLs and `api_mode` values; provider identity, picker identity, model identity, endpoint, and wire protocol are separate facts.
- Preserve the raw provider response/events for diagnostics, but expose a provider-neutral event/result contract to the worker integration: status/reasoning, text, function call name/arguments, call ID, usage, finish state, metadata, and error.
- Keep tool permissions, skill discovery, memory policy, session state, timeout, cancellation, tracing, and cost accounting on Hermes' existing child path. A worker facade may narrow these surfaces, but must not bypass them.
- Treat every model ID literally. Verify the exact route and do not silently substitute a nearby model or fallback provider; report fallback explicitly when it occurs.
- Separate measured facts from code observations, documentation claims, and untested capabilities. A passing unit test is not production readiness.

## Procedure

1. **Map the live architecture before editing.** Read repository `AGENTS.md` files, then inspect `tools/delegate_tool.py`, `tools/delegate_tool_config.py`, `tools/delegate_tool_child_run.py`, `run_agent.py`, the active provider resolver, the relevant transport/adapter, tool discovery, context compilation, session persistence, usage/cost, and cancellation code. Search for the actual function definitions and call sites; do not trust line numbers copied from an older checkout.
2. **Find the smallest integration seam.** Prefer a request/profile facade that compiles objective, lean context, toolsets, reasoning, limits, and metadata into the existing child-agent constructor. Keep provider credentials and transport resolution in the existing resolver; keep tool execution in Hermes, not in a worker-specific bridge.
3. **Compile a bounded worker capsule.** Include objective, repository/workspace hint, constraints, acceptance criteria, selected toolsets, and only targeted memory/skills. Resolve requested labels through Hermes' live toolset registry before applying permissions: aliases and composite `includes` must be compared by their resolved function sets, not raw names. Intersect the resolved request with the parent's effective allowlist and inherited denies; an explicit child request may narrow authority but must not widen a lean parent that exposes only delegation. Reject ambiguous multi-task batches when the worker contract is single-objective.
4. **Route by target model.** Pass `target_model` into provider resolution and verify the returned model, provider identity, base URL, `api_mode`, auth presence (boolean only), request overrides, and max-output setting. For mixed Kie routes, keep one configured vendor identity when appropriate but rewrite Claude/Grok/GPT families to their own protocol endpoints; do not force one API mode across the catalog.
5. **Validate the wire builder before spending credits.** Build a request through the real Hermes transport and inspect model, endpoint, stream setting, tool schema conversion, reasoning fields, cache fields, headers, and provider-specific body extensions. For Kie Codex/Responses, verify browser-shaped headers, explicit SSE, and the route-specific `call_`/`fc_` contract; do not apply that ID rewrite to a provider whose live contract preserves another ID form.
6. **Exercise the MODE_3 loop without the orchestrator doing the work.** Snapshot the capability chain as `requested toolsets → resolved toolsets → child registered functions → provider function schemas` before making a paid call. Use a deterministic tool fixture and assert the sequence `worker response → function_call → Hermes tool result → worker continuation → next function_call or final`. Assert that dependent calls see prior tool outputs and that the same child session/trajectory retains state. Test malformed/missing IDs, provider errors, empty streams, cancellation, timeout, and maximum turns.
7. **Attach observability at the existing result boundary.** Record worker profile, requested/effective provider and model, reasoning level, model-turn count, tool names/call IDs, token counters, cache counters, estimated cost plus cost status/source, duration, finish state, and raw-trace reference. Preserve generic subagent result compatibility; add worker metrics rather than replacing the parent result contract.
8. **Enforce limits fail-closed where evidence exists.** Bound turns and wall time before launch. Reject invalid or negative budgets. Mark a run failed when a known cost limit is exceeded; label cost enforcement `unknown` when the provider does not expose reliable pricing/credit usage rather than pretending that a zero counter means zero spend.
9. **Run verification in layers.** Start with compile/import checks, focused unit tests for profiles, route resolution, tool selection, reasoning translation, ID normalization, reinjection, budgets, and metrics; then run existing transport/delegation regressions. Next run a mocked multi-turn child loop. Only then perform one approved live provider smoke test and one dependent multi-tool delegation. Record the exact model, route, stream/content type, function-call events, outputs, usage, retries, latency, and spend.
10. **Declare readiness conservatively.** Use `PRODUCTION_READY: YES` only when the real `delegate_task` path—not merely a direct provider probe—has completed the required multi-turn tool loop, the result has returned through Luna, and cancellation, limits, errors, and accounting have been verified. Otherwise state the exact untested gate.

## Common pitfalls

- **A facade that only generates text is not an agentic worker.** Verify that the worker child receives tools and can perform at least two dependent tool turns before claiming autonomy.
- **Filtering labels before resolving them can erase valid tools.** Resolve aliases and composite `includes` through the live registry first, because a raw-name intersection can turn a valid child request into an empty registry and schema list.
- **A lean parent is not automatically authorized to grant more tools.** Configure required child tools in the parent's trusted allowlist while telling the parent not to execute implementation work; never replace the permission boundary with an unconditional union.
- **An empty provider schema list is not a provider verdict.** Trace requested, resolved, registered, and schema layers first; investigate transport conversion only after the child registry is non-empty.
- **A direct provider probe is not Hermes E2E evidence.** Capture the actual Hermes outbound route and child result; a successful raw HTTP call cannot prove delegation wiring, permissions, persistence, or reinjection.
- **A provider-level API mode is not a model-family contract.** Resolve with the target model on every construction and model switch, because the same vendor can expose Messages, Chat Completions, and Responses endpoints.
- **Do not let an empty cached delegation config shadow persistent routing.** Merge persistent configuration with non-empty runtime overrides, then assert the resolved child model/provider before making a paid call; otherwise the child silently inherits Luna.
- **Normalize call IDs only at the adapter boundary.** The Kie Codex route may return `call_…` while requiring `fc_…` in replayed Responses items; normalize both function-call and function-output sides consistently, and keep other Kie routes on their own observed contract.
- **Do not infer unsupported capabilities from a text answer.** Tool calling, dependent loops, streaming, structured output, web access, computer use, cache behavior, and reasoning levels each need their own evidence.
- **Do not forward generic provider fields blindly.** Gate cache retention, parallel tools, native compaction, `reasoning.summary`, and body extensions by route/model because a compatible Responses shape can still reject one field.
- **Do not expose secrets in traces or tests.** Assert header presence, endpoint, and credential source—not key values—and redact raw request dumps before retaining them.
- **Do not report a cost total without a status/source.** Distinguish measured, estimated, unavailable, and unknown; Kie proxy credits and zero input counters need explicit interpretation.
- **Do not stop at green unit tests.** The final report must name the live E2E gate and any fallback/cancellation/benchmark that remains unverified.

## Reference

Use `references/agentic-worker-validation-matrix.md` for the compact evidence matrix and MODE_3 test recipe. Use `references/child-toolset-propagation.md` for the registry/permission/schema boundary trace and provider-free bridge test.
