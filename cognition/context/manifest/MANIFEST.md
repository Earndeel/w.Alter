# Walter Context

**Role.** Prepares and orders the context per message and per sub-agent, and compresses the history according to the
harness's contract. It owns no canonical data: subjects, views and originals belong to Walter Memory and walter-logs,
read through their public interfaces; model choice belongs to the Router.

**Organisation**
- `preflight` (HTTP service `127.0.0.1:8897`): one decision per owner message → a ContextPlan (intent, level,
  capabilities, fast path), deterministic rules first, then the Router's decision poste when needed.
- `retrieval` + `assembly`: fetch what the plan asks (memory context, people's cards, module D2 cards, views) and order
  stable blocks before volatile ones; this is the turn's `<walter-context>` block on the engine.
- `child`: the starting brief of a sub-agent (mission, capabilities, skills, memory).
- `state`, `reassess`: per-thread working state updated by events; targeted re-evaluation during a run.
- `compress` + `recover`: projection `head → record → compact → live`, forward-only cuts priced against the provider
  cache; `context_recover(ref)` returns the original of a shortened tool output from walter-logs.

**Interfaces.** Used by the engine automatically; agents see its output, not its tools, except `context_recover`.
CLI `walter-context` (plan, capability layer, bench). Specification: `/walter/cognition/context/docs/CONTEXT-ENGINE.md`.
