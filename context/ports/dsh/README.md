# Walter Context for DSH

This plugin replaces DSH's `compaction-basic` composition entry. It calls the
stdlib Walter Context core through bounded JSON/stdin subprocesses; no Hermes
runtime, model, service or Python environment is required.

```yaml
- id: compaction-basic
  disabled: true
- insert:
    - id: walter-context
      name: /opt/walter-context/ports/dsh/index.mjs
```

DSH's public `BasicCompactionEngine.summarize()` extension and dynamically
called `compactIfNeeded()` are used. Walter owns the automatic pressure threshold,
completed-turn retention and deterministic record rendering. DSH owns the meter,
tool pairing validation, durable bracket lock, surface replacement, replay,
manual `/compact` range selection and context-overflow retry budget. These host
mechanisms are dependencies, not a second summarizer. No request middleware
rewrites DSH's immutable, journal-derived requests.

`context_recover` reads an original tool result from the current DSH session's
raw journal, including shadowed events; it works before Walter Logs ingestion.
It uses DSH's normal tool execution and permission pipeline. References never
open a different session. The durable transcript is neither rewritten nor deleted.

Failure of the Python bridge fails this compaction operation. DSH logs an explicit
warning and can continue with the intact surface; it does not call its native
LLM summarizer as a fallback. Overflow can still fail for an indivisible recent
turn. The record is lossy and extractive: source recovery and structural tests
are not evidence of semantic answer quality.

`WALTER_CONTEXT_HOME` and `WALTER_CONTEXT_PYTHON` override the module and Python
paths. Peer dependencies should resolve normally when installed as a package;
the VM deployment can instead resolve the DSH host via `WALTER_DSH_PACKAGE`
(default `/opt/dsh/package.json`). Supported/tested host: DSH 0.2.0-rc.2.

Tests: `node /opt/walter-context/tests/test_dsh.mjs`. They use actual DSH Session,
CompactionEngine, ToolRuntime and replay with synthetic conversation fixtures;
provider metadata and meter are isolated fixtures, with no external model calls.
