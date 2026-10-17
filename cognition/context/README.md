# walter-context

Walter owns context policy and rendering in a runtime-neutral Python 3.11+ stdlib
core. A port connects that core to the host's supported context interface. The
core has two modes with different retention guarantees; installing one port does
not qualify the other.

## Public modes

| Mode | Host interface | Model-visible retention | Durable source |
| --- | --- | --- | --- |
| Checkpoint | `checkpoint.plan` / `checkpoint.summarize`, versioned JSON/stdin bridge; DSH compaction service | Full user text in the selected span, including previous checkpoints, or explicit refusal. All tool-result call ids remain references. Assistant text, action details and tool contents are lossy. | DSH owns the append-only journal, replacement transaction and replay. |
| Projection | `Session.select / observe / turn_complete / compact_all`; Hermes `ContextEngine` port | Cache-oriented `head → record → compact → live`. Older user/assistant text can be clipped, reduced to one line or omitted. | The host and Walter Logs own persistence. A recoverable source is not the same as a constraint visible to the model. |

No mode has a general proof of semantic answer quality. Preserving text does not
prove that a model will obey every constraint in that text. Tool references make
original evidence recoverable; they do not put the full evidence in every request.

## Checkpoint mode

Walter selects older completed turns when measured pressure reaches the smaller
of its model profile's effective budget and the host's input capacity. Automatic
selection retains the live user turn plus `projection.keep_turns` completed turns.
DSH supplies input capacity after reserving output tokens. Manual `/compact`
selection remains DSH's policy; summary rendering still uses Walter.

The extractive record preserves every user text without content truncation and
all tool-result call ids, including after repeated checkpoints. Boundary whitespace
can be normalized. The result must fit `policy.record_share` of the effective
budget, using the core's approximate token estimator. With the current config,
that share is 30%. If preservation cannot fit, compaction is refused instead of
silently dropping constraints. An in-history `system` or `developer` message also
refuses compaction: flattening its role into a user record would change authority.
Leading system/developer messages remain outside the selected range.

DSH independently validates tool pairing, locking, stable selection and that the
framed replacement actually shrinks its source. A bridge failure, an oversized
record or an unsupported instruction span leaves the original surface intact;
there is no automatic native LLM summary fallback. A conversation can therefore
reach a visible context-limit error when its preserved text or live turn is too
large. Repeated checkpoints retain previous checkpoint text, so their size can
grow until that explicit limit is reached.

## Projection mode

```text
payload = head | record | compact | live
          system earlier turns    tool digests,    recent host messages
          rows   as inert record  clipped text    with original sidecars
```

Each zone is a pure projection; cut points move forward. Between boundaries the
view grows by appending, and already-rendered compacted entries remain stable.
This aims to preserve provider prefix-cache reuse; cache hits depend on the
provider and model, not just on the local projection.

`policy.py` prices moves using each model profile's cached/write costs and session
calls per turn. Past the effective budget it favors a view under budget. At high
pressure it may compact older live-turn steps; the most recent steps remain
verbatim. A record over its configured share can reduce old turns to short lines
and then omit them from the view. This mode can consequently remove user
constraints from the model's immediate context. Journal retrieval does not repair
that omission automatically, and long-term memory is not guaranteed to contain
every omitted turn.

Hermes' `select_context` changes the outbound view. The separate emergency
`compress` callback returns a compressed list to the host, whose lifecycle owns
its persistence. Both paths require qualification before enabling this port.

## Layout and commands

```text
walter_context/       wire, digest, layers, policy, session, config, journal
                     checkpoint, bridge, cli
config/walter-context.toml  shared projection/policy/model tunables
ports/hermes/         public ContextEngine port (currently inactive)
ports/dsh/            public DSH compaction port
bench/replay.py       local journal replay: sizes, simulated cache/cost, latency
bench/quality.py      cloud-safe quality samples; estimate by default
```

```bash
/opt/walter-context/bin/walter-context bench --a8 --sessions 40
/opt/walter-context/bin/walter-context quality --samples 30
/opt/walter-context/bin/walter-context recover <call-id> --offset 0
/root/.hermes/hermes-agent/venv/bin/python -m pytest -q /opt/walter-context/tests
node /opt/walter-context/tests/test_dsh.mjs
```

Only `quality --run` requests judging calls through the backfill budget. Its
cloud-safe sampling excludes entire chains containing events not classified
`cloud_allowed`; local replay and source recovery have separate privacy rules.

## Ports and verified scope

- **DSH 0.2.0-rc.2:** configured to replace `compaction-basic` with the Walter port
  on new launches. Automatic planning and record rendering belong to Walter;
  transaction, replay, token meter and manual range selection belong to DSH.
  See [ports/dsh/README.md](ports/dsh/README.md).
- **Hermes:** implemented but inactive; the inspected `context.engine` remains
  `walter-compress`, a legacy Hermes adapter. Its replacement has not passed
  semantic retention qualification. The port honors smaller host budgets, resets
  core session state and inherited usage/compression counters, and scopes journal
  recovery to an exact session.
- **Claude Code / Codex:** keep their native runtime, model and compaction. Walter
  memory and tools are attached through their supported hooks/MCP interfaces.
- **Future runtimes:** choose the mode matching their public host contract.
  Request-only projection must not rewrite an event-sourced host's immutable
  journal-derived requests.

Qualification uses 24 Python tests and 5 Node tests. Node exercises real DSH
Session, CompactionEngine, ToolRuntime, transactions and replay with synthetic
histories; provider metadata and metering are fixtures. The separate known-answer
probe retains 13 textual facts/constraints directly and six tool results by
reference, including a constraint in the middle of a long user message. It also
checks repeated checkpoints and refusal when preserved text exceeds budget.
These checks made no cloud model calls and do not establish real-model answer
quality or qualify the Hermes projection.

Design references: `/root/.hermes/docs/walter-memory/CONTEXT-ENGINE.md`,
`HARNESS-CONTRACT.md`, `PLAN.md` and dated `DECISIONS.md` entries.
