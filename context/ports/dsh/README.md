# Walter Context for DSH

The plugin connects the shared Walter Context checkpoint contract to DSH's public
compaction service. It calls the Python 3.11+ stdlib core through bounded
JSON/stdin subprocesses. It requires no Hermes runtime or Hermes virtualenv and
makes no summarization model call.

The VM's `cordis.patch.yml` disables the stock entry and inserts this port:

```yaml
- id: compaction-basic
  disabled: true
- insert:
    - id: walter-context
      name: /opt/walter-context/ports/dsh/index.mjs
```

Changing only the name on an existing entry does not replace it in this DSH
version. The resolved composition was checked with `dsh --dump-config`; this
configuration takes effect on new launches.

## Ownership

The port extends `BasicCompactionEngine.summarize()` and its dynamically called
`compactIfNeeded()`. Walter owns the automatic pressure threshold, completed-turn
retention and deterministic checkpoint rendering. DSH owns the token meter, tool
pairing validation, durable bracket lock, replacement transaction, replay, manual
`/compact` range selection and context-overflow retry budget. These are host
dependencies; the stock model summarizer is not used as a fallback. No request
middleware edits DSH's immutable journal-derived requests.

Both planning and summarization receive the routed model id and its input
capacity after output-token reservation. The shared core takes the smaller of
that capacity and its model profile's effective budget. Automatic selection keeps
the live user turn plus `projection.keep_turns` completed turns.

## Retention and failure behavior

Checkpoint rendering keeps the complete user text of the selected span, including
any prior checkpoint, and every tool-result call id. Leading/trailing whitespace
can be normalized. The shared `record_user_chars` clipping limit used by projection
mode does not truncate checkpoint user text. Assistant answers and action details
remain extractive and clipped; tool contents and reasoning are not copied in full.
Image/file blocks retain textual attachment references, not their visual/audio
content. These losses can affect later answers.

A checkpoint must fit `policy.record_share` of its effective budget (currently
30%, estimated by the core). If full user text or the rendered record cannot fit,
compaction fails explicitly. A `system` or `developer` message inside the selected
history also causes refusal: its instruction role must not be erased by a plain
user record. Only the injected global system head is exempt, identified by its durable id.
A privileged role at the first node of a manual/explicit region is also refused. DSH separately
checks that the framed replacement is smaller using its token meter.

A refused record or failed Python bridge closes the compaction bracket without a
replacement; DSH logs the failure and can continue with the intact surface. There
is no automatic LLM summary fallback. An indivisible recent turn, growing prior
checkpoints or too many preserved instructions may ultimately produce a visible
context-limit failure. The bridge's diagnostic intentionally excludes transcript
content; the durable transaction records the failure.

`context_recover` reads an original tool result from the current DSH session's raw
journal, including events shadowed by earlier compaction. It works before Walter
Logs ingestion and uses DSH's normal tool execution and permission pipeline.
References cannot open another session. Responses are paged at 12,000 characters.
The raw transcript is not rewritten or deleted by this port. Source availability
is distinct from evidence actually visible to the model; the model must request
a recovery before it can use omitted tool content.

## Installation and qualification

`WALTER_CONTEXT_HOME` and `WALTER_CONTEXT_PYTHON` override the module and Python
paths. Peer dependencies resolve normally when installed as a package; this VM
can resolve the host through `WALTER_DSH_PACKAGE` (default
`/opt/dsh/package.json`). The supported and tested host is DSH 0.2.0-rc.2.

`node /opt/walter-context/tests/test_dsh.mjs` runs seven tests with actual DSH
Session, CompactionEngine, ToolRuntime and replay. They cover a successful
checkpoint, source recovery, intact raw events, Python failure, system/developer
instruction refusal (including leading roles and manual compaction), abort and
concurrent locking. Histories are synthetic;
provider metadata and metering are fixtures and no external model is called.
Python tests additionally check complete user-text retention through repeated
checkpoints, all tool references and explicit budget refusal.

A separate 19-item exact-retention probe keeps 13 textual facts/constraints in the
checkpoint and six tool results as references, with no silently omitted probe.
This establishes those deterministic properties, not semantic answer quality or
model compliance with every instruction. It does not qualify the different
Hermes projection mode; Hermes remains on `walter-compress`.
