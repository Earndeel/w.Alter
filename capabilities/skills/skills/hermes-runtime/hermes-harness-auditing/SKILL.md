---
name: hermes-harness-auditing
description: Audit end-to-end Hermes Agent across Desktop, TUI Gateway, sessions, agent loop, tools, providers, compression, persistence, runtime, and return events. Use for architecture reviews, payload/cost investigations, robustness audits, or global harness reports where provider-specific evidence must remain subordinate to the system architecture.
---

# Hermes Harness Auditing

Audit the **whole execution harness**, not merely the provider that made a symptom visible.

## Trigger

Use this skill when asked to:

- map Desktop → Gateway → agent → provider → tools → DB → response;
- investigate context growth, repeated compression, session rollover, payload overhead, retries, or cost;
- review Hermes robustness, security, observability, persistence, or E2E coverage;
- turn a provider-specific investigation into a global Hermes report.

For current Hermes commands and configuration, load the protected `hermes-agent` skill and consult the official docs. This skill governs the **audit method and evidence discipline**.

## Core distinctions

### Never conflate the gateways

- `tui_gateway/`: Desktop/TUI WebSocket JSON-RPC surface.
- `gateway/`: messaging channels such as Telegram/Discord and their own session/concurrency policy.

Both may converge on `AIAgent.run_conversation()`, but their ownership, queuing, auth, interruption, and delivery rules differ.

### Separate architecture from provider case studies

A provider capture can prove serialization, token accounting, strict-schema behavior, or retry semantics. It does **not** describe the whole harness. Keep provider evidence in an appendix unless the finding is demonstrably transport-agnostic.

### Desktop plugins are a separate local surface

When auditing or explaining plugins in Hermes Desktop, do not reuse the Python/gateway plugin inventory. The three plugin surfaces are independent:

- **Desktop UI plugins:** local Mac files under `$HERMES_HOME/desktop-plugins/<id>/plugin.js`, inventoried in **Settings → Plugins**;
- **Bundled Desktop plugins:** `apps/desktop/src/plugins/<id>/plugin.{ts,tsx}` (the current tree may ship none);
- **Python/gateway plugins:** the registry reported by `hermes plugins list` under `~/.hermes/plugins/`.

For a Desktop inventory, first inspect Settings → Plugins or the Mac's local `desktop-plugins` directory. If the Mac filesystem or SSH path is unavailable, label the exact inventory **UNKNOWN** and request a screenshot or the plugin files rather than inferring from the remote backend. For each plugin, audit registered UI contributions, gateway RPC calls, scoped REST/socket access, persistence, imports, external URLs, and enable/disable state. See `references/desktop-plugin-audit.md` for the compact checklist.

### Use four evidence labels

Every material claim must be tagged or clearly framed as:

1. **MEASURED** — command, test, DB query, runtime probe, or captured request actually executed.
2. **OBSERVED IN CODE** — behavior visible in the audited worktree.
3. **RISK** — plausible consequence inferred from an observed mechanism.
4. **UNKNOWN** — insufficient evidence; do not upgrade it to fact through confident prose.

## Workflow

### 1. Freeze the audited state

Record before analysis:

- commit, branch, tag/describe, and dirty-worktree counts;
- UTC timestamp;
- source hashes for pivotal files;
- runtime/service state separately from repository state.

Resolve each live PID's interpreter, command and editable-install mapping before selecting the source tree; the CLI symlink may target a different release. Compare config/source mtimes with process start time, and label loaded in-memory settings unknown when not observed.

Trace optimization settings through config reader → assembly caller → final transport; a YAML key, helper definition or passing helper test does not prove production integration. Inspect plugin consumers separately before calling a setting globally unused.

Separate pre-audit usage from the audit's own skill loads, web results and subagents. Check cache-counter semantics in source before dividing: some session stores report only uncached input while API logs report total input. Report cache-token reuse separately from money or subscription quota savings.

For automatic memory, identify the provider's actual config file, endpoint and query timing; a separate filtered search service does not protect a direct recall path. Treat injected historical optimization claims as dated evidence, never proof of current wiring.

A dirty worktree is auditable, but it is not a release certification. Say so explicitly.

### 2. Map the full path

Trace concrete symbols and state transitions for:

1. Desktop request/event facade and Electron bridge;
2. WebSocket/JSON-RPC parsing, request correlation, and long-handler dispatch;
3. session create/resume/interrupt/model switch/prompt submit;
4. `AIAgent` and turn-context assembly;
5. provider transport selection and normalized response contract;
6. streaming, retry, backoff, and cooperative cancellation;
7. tool permission, dispatch, timeout, progress, terminal result, and cleanup;
8. compression, summary continuity, session split, and active-slot transfer;
9. raw ledger, prompt projection, usage, FTS, WAL, recovery;
10. outbound events and Desktop reconstruction;
11. CLI, API, and messaging entry surfaces that reuse the same core.

For each boundary, document inputs, outputs, owner, state mutation, invariant, failure mode, and existing/missing tests.

### 3. Measure payloads at two levels

For Monsieur, reducing total model-visible context is an objective even when cache reuse is high. Measure total context, uncached input, latency, quality and maintenance complexity separately; cache reuse is not a reason to retain irrelevant material. Preserve workflows, accesses and integrations by reducing their model-visible representation rather than removing capabilities or migrating harnesses by default.

Do not substitute one for the other:

- **Nominal prompt build**: system bytes, schema bytes, tool count, platform/toolset resolution.
- **Actual provider body**: serialized bytes and provider-reported usage from a real or deterministic captured call.

Never label reconstructed JSON as a wire capture. Never infer token counts by dividing bytes unless clearly labeled as an estimate. Prefer provider usage or the actual tokenizer.

### 4. Audit compression as a lineage

Measure:

- number of physical session segments in one logical lineage;
- closure reasons;
- median and tail segment duration;
- API calls, input/cache/output counters;
- compression log frequency;
- fixed/cacheable payload versus dynamic history/tool output.

A lock may prevent concurrent compression while still allowing pathological rollover frequency. Distinguish collision prevention from rate control.

### 5. Audit persistence and secrets safely

Open SQLite read-only. Record schema version, WAL/synchronous mode, integrity check, table counts, file growth, FTS footprint, message-token coverage, and cost coverage.

For secret-at-rest detection:

- scan syntax classes and return **counts only**;
- never print candidate values;
- state that validity and privileges are unknown unless separately authorized;
- inspect the write path before claiming redaction coverage;
- remember FTS can duplicate sensitive content physically.

Do not purge, reindex, revoke, or test credentials during an audit without explicit approval.

### 6. Audit runtime ownership

Measure service restarts, binds, RSS, worker age, PPID, session ownership, and DB end state. A process is a confirmed leak only when ownership/state evidence rules out active work. Never kill user processes as part of a read-only audit.

### 7. Validate in independent batches

One stale import can abort pytest collection and hide hundreds of passing tests. Run logically independent batches:

- Gateway/session/WebSocket;
- transports/provider parity;
- compression/continuity;
- tools/async DB;
- dedicated regressions;
- Electron Node tests;
- Desktop UI tests;
- TypeScript and lint.

Classify accurately:

- collection failure from removed symbol → code/test skew;
- stale expected payload beside updated tests → obsolete test;
- missing dependency → validation blocked, not product failure;
- functional assertion failure → product or test defect pending source comparison.

Do not repair tests during a read-only audit merely to make the dashboard green.

### 8. Challenge attractive hypotheses

Before publishing a suspected root cause such as “buffer saturation” or “JSON deserializer latency,” require direct evidence: exception, profile, queue depth, blocked stack, OOM, or benchmark. If logs instead show repeated compaction, report the measured mechanism and explicitly retract the unsupported hypothesis.

### 9. Produce one authoritative deliverable

The global report should contain:

- scope/revision/status;
- executive verdict;
- evidence taxonomy;
- end-to-end map;
- boundary-by-boundary findings;
- measured runtime/DB/payload/test results;
- prioritized risk register;
- unknowns;
- cost-benefit remediation plan;
- provider annexes;
- artifact paths and hashes.

Mark superseded provider-centric reports as archives pointing to the global report. Do not leave two documents that both claim authority.

### 10. Audit the audit

Before delivery:

- read the complete report back;
- verify required sections;
- recompute referenced hashes after the final artifact write;
- scan the report itself for secret-shaped values;
- ensure removed/unverified numbers are absent;
- validate JSON artifacts;
- run `git diff --check`;
- distinguish source changes from report-only changes.

Use `scripts/validate_audit_artifacts.py` for deterministic final checks. See `references/global-audit-case-study.md` for a condensed worked example and `templates/global-report-outline.md` for the report skeleton. To prove a plugin/tool is actually registered and invoked by the real harness (config allow-list, `hermes plugins list` misdirection, PluginManager._plugin_tool_names, HERMES_HOME sub-profile pitfall, state.db double-escaped tool_calls), see `references/proving-tool-registration-real-harness.md`. For a component map of the `computer_use` tool system (schema, backend registry seam, cua MCP session lifecycle, browser-route boundaries, Walter plugin delivered-vs-gap, and the walter×YOLO shim `serve` gap), see `references/computer-use-tool-system-architecture.md`.

## Pitfalls

- Treating the provider as the architecture.
- Calling a reconstructed body “real wire payload.”
- Reporting dynamic DB metrics without timestamping the snapshot.
- Summing provider usage fields whose semantics may overlap without checking normalization.
- Calling every long-lived worker an orphan without session evidence.
- Declaring the whole suite broken because one file fails collection.
- Optimizing small prompt fragments while ignoring rollover frequency, worker leaks, or FTS duplication.
- Deleting useful cached context or search indexes before measuring quality impact.
- Trusting a subagent’s file write or exact number without reading the artifact and recomputing it.
