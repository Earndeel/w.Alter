# walter-context

Decides what enters a model's window on each call: what, how much, where and in what form. The target has no
sessions and is dynamic. Activity is cut into threads that cross sessions and runtimes. Context is recomputed for each
owner message, then stays stable for the turn so the provider cache keeps working. History is compressed without
silent loss. The core is runtime-neutral Python 3.11+ stdlib. Hosts plug in through `ports/`.

Spec, plan and measurements: `docs/walter-memory/CONTEXT-ENGINE.md` (instance documentation). Dated decisions:
`DECISIONS.md` next to it.

## Sub-modules

| Sub-module | Role | State |
|---|---|---|
| `compress` | The compression engine: history in, its most useful form for the budget out | built (projection + checkpoint) |
| `recover` | Originals behind compacted refs, read from walter_logs with privacy classes applied | built |
| `config` | The only tunables (`config/walter-context.toml`): projection, policy, model profiles | built |
| `bridge` | Versioned JSON bridge for out-of-process hosts (DSH) | built |
| `sense` | Local pre-selection: candidate threads and memory from local embeddings, entities, recency | plan, lot 4 |
| `decide` | Context plan from the decision model: which thread, what context | plan, lot 4 |
| `gather` | Thread notebook, verbatim excerpts (walter_logs), memory (reranked only when over budget) | plan, lot 4 |
| `compose` | Layers ordered from stable to volatile, one budget, provider cache markers | plan, lot 4 |

Threads and their notebooks belong to Walter Memory. They are derived, revisable data with provenance.
walter-context reads them and renders them. It never writes them.

## The compression engine (`compress`)

```text
payload = head | record | compact | live
          system earlier turns    tool digests,    recent host messages
          rows   as inert record  clipped text    with original sidecars
```

- **Journal is truth, payload is a projection.** Every zone is a pure function of what it covers. Cut points only
  move forward. Between boundaries the payload only grows, and at a boundary already-compacted entries render to
  the same bytes, so the prefix stays cached.
- **Boundaries are priced** (`compress/policy.py`) against the model profile: cached/write costs, TTL and calls per
  turn. Past the effective budget, quality wins over cache.
- **Two host contracts today:**
  - *projection*: request-only. The host keeps its history (`Session.select/observe/turn_complete/compact_all`).
  - *checkpoint*: the host persists a replacement record (`checkpoint.plan/summarize`, through `bridge`). It
    retains all user and visible assistant text, or refuses.

  Lot 2 merges them into one planner with one retention ladder (verbatim → digest + ref → one line → omitted,
  recoverable). The fixed sacrifice order is tool outputs, then reasoning, then answers, then owner messages last.
  When retention cannot fit, the engine refuses explicitly.
- **Nothing is lost.** A compacted tool output keeps its call id as `ref`, and `walter-context recover <ref>` reads
  the original.

No mode has a general proof of semantic answer quality. Tool references make evidence recoverable; they do not put
it in every request.

## Ports

| Host | Contract | State |
|---|---|---|
| DSH | public compaction transaction (`ports/dsh`, checkpoint) | active on new launches |
| Hermes | public `ContextEngine` (`ports/hermes`, projection) | built, not activated. Hermes runs its native compressor (walter-compress retired 2026-10-21) until lot 6 |
| Claude Code, Codex | native compaction; additive context only through hooks / MCP | lot 4 |

## Commands

```bash
walter-context recover <call-id> [--offset N]     # original of a compacted output
walter-context bench --sessions 40                # replay: tokens, simulated cache, cost
walter-context acceptance                         # synthetic exact-retention corpus, offline
walter-context quality --samples 30               # judged retention, estimate by default
walter-context threads --gold FILE --mode both    # thread attachment on the real stream; --decide adds the decision model
walter-python -m pytest -q tests                  # from the module root
node tests/test_dsh.mjs
```

`threads` reads walter_logs and embeds locally. Only `--decide` and `quality --run` call a model, through
`walter_memory.llm`, and they send `cloud_allowed` data only. Reference sets that contain the owner's data live in
the instance (`@instance/state/context/`), never in this module.
