# walter-context

The payload a model sees on each call, cache first. Runtime-agnostic core (stdlib only, Python ≥ 3.11, no Hermes
import); Hermes is the first port. Spec, measurements and decisions: `/root/.hermes/docs/walter-memory/CONTEXT-ENGINE.md`
(P6 + P8.4 in `PLAN.md`, dated entries in `DECISIONS.md`).

## The idea in one picture

```
payload = head | record | compact | live
          system  one message:     host messages,     host messages,
          rows    earlier turns    tool outputs →     byte for byte
                  as an inert      digest + ref,      (the live turn and
                  session record   no replay sidecars  the last k turns)
```

* Each zone is a **pure function** of the messages it covers; the cut points (an `Epoch`) only move **forward**.
* Between boundaries the payload only grows by appending → every call re-reads the previous one from the provider cache.
* At a boundary, what was already compacted renders to the same bytes → the prefix up to it stays cached; the record
  grows by appending entries, so even folding keeps its earlier bytes.
* Nothing is lost: a compacted tool output keeps its call id as a `ref`; `context_recover` reads the original from the
  session journal (`walter_logs`), with the usual privacy classes.
* The record is bounded: past `record_share` of the budget its oldest turns become one line each, then are omitted
  (they stay in the journal and in long-term memory).

## When the cut points move (`policy.py`)

At the first call of each turn (and mid-turn only when the payload passed the effective budget and grew by
`regret_tokens`), every forward move is priced with the model profile:
`next call (cached prefix × cached_cost + rest × write_cost) + H × payload × cached_cost`, H = the session's calls
per turn. Cheapest wins; past the model's **effective budget** quality wins (the cheapest option back under budget,
including — last resort — compacting older steps of the live turn, its last steps always verbatim). A cold cache makes
a rewrite free. Host-side compression only fires past `emergency_share` of the window and then gets `compact_all()`.

## Layout

```
walter_context/   wire (vocabulary) · digest (tool traffic) · layers (projection, record levels, render cache)
                  policy (boundaries) · session (state, the 4 calls) · config · journal (context_recover) · cli
config/walter-context.toml   the only place for tunables (projection, policy, model profiles)
ports/hermes/     ContextEngine plugin (public API: select_context, compress, update_from_response, …)
bench/replay.py   C0: real sessions from walter_logs re-played — tokens, simulated prefix cache, cost, latency
bench/quality.py  C0: retention probes, LLM-judged (estimate by default; --run spends the backfill budget)
tests/            invariants: purity, append-only, cross-boundary prefix, record append, tool pairs, refs, speed
```

## Commands

```bash
/opt/walter-context/bin/walter-context bench --a8 --sessions 40        # vs Hermes' real calls (A8-covered chains)
/opt/walter-context/bin/walter-context bench --set projection.keep_turns=2
/opt/walter-context/bin/walter-context quality --samples 30            # estimate only
/opt/walter-context/bin/walter-context recover <call id> [--offset N]
/root/.hermes/hermes-agent/venv/bin/python -m pytest -q /opt/walter-context/tests
```

## Ports

* **Hermes** (`ports/hermes`, link `~/.hermes/plugins/walter-context`): `context.engine: walter-context`, plugin
  enabled instead of `walter-compress`, toolset `context_engine` on the platforms that should see `context_recover`.
  Each request logs `walter-context: {trace}` in agent.log; the A8 collector attaches it to the call
  (`system.agent_calls.context_engine/context_trace`).
* **DSH / a future Walter runtime**: call `Session.select / observe / turn_complete` directly.
* **Claude Code / Codex**: their compaction is theirs; they keep getting memory through the hook and the MCP.
