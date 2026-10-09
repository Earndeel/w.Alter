---
name: hermes-platform-operations
description: Use for Hermes platform configuration and operations.
tags: [hermes, platform, config, dashboard, runtime, memory, sessions, updates]
metadata:
  hermes:
    tags: [hermes, platform, config, dashboard, runtime, memory, sessions, updates]
---

# Hermes Platform Operations

Use this class-level umbrella for Hermes configuration, dashboard, runtime routing, profiles, sessions, memory, updates, agentic workers, callbacks, and platform health. Keep the always-on invariants here; use the source-routing reference for exact historical procedures preserved in archives.

## Always-on rules

- Identify the active Hermes home, profile, checkout, interpreter, process owner, gateway surface, and config source before changing state, because similarly named runtimes can load different files.
- Treat configuration, cached snapshots, persistent sessions, service processes, and browser/desktop clients as separate state; changing one does not prove the others reloaded.
- Preserve exact model/provider IDs, endpoint/API mode, tool permissions, session lineage, and auth scope; never silently substitute a route, credential, or account.
- Prefer additive, reversible changes and narrow restarts; inspect process ownership before stopping anything and never use broad process termination for cleanup.
- Keep secrets out of skills, logs, screenshots, artifacts, and diagnostics; verify credential presence and scope without exposing values.
- Separate measured evidence, code observations, inferred risks, and unknowns; a healthy HTTP response, visible UI, passing unit test, or process state is only evidence for the layer it tests.
- Treat provider onboarding as five independent gates—live catalog and exact model ID, account/API authentication, credential issuance/binding, Hermes configuration reload, and real inference entitlement—and verify each with its own evidence before declaring a provider ready. For dashboard-issued keys and OpenAI-compatible endpoints, follow `references/provider-onboarding.md`; it defines the read-back evidence and no-secret test boundary.
- When a configured model is missing from a Desktop picker, query the authenticated live owner gateway at `/api/model/options?explicit_only=1` and inspect the exact provider slug and model ID. Do not treat `config show`, CLI inventory, or `/v1/models` as equivalent evidence: `/v1/models` may expose an OpenAI-compatible alias instead of the picker catalog; use `refresh=1` only when testing a dynamic provider cache.
- Resolve the picker’s profile/session owner before comparing catalogs, because a healthy default gateway can coexist with a different session route. Distinguish a compact quick-model list from the full searchable picker; if the owner catalog already contains the exact ID, refresh or reconnect the client and compare compiled Desktop and backend build identities before editing provider configuration or substituting a model.
- Verify every external or runtime effect by reading the exact target back: process, endpoint, catalog, config, artifact, session, database, or provider result.
- Distinguish the raw ledger from provider prompt projections. Optimize copied request context without deleting canonical history or weakening tool-call/result pairing.

## Host and storage audits

- Treat questions about disk usage or possible cleanup as read-only diagnosis, not deletion approval. Show the main consumers, their function, measured size and cleanup risk before proposing actions; prioritize material savings over tiny projects.
- Reconcile storage totals before assigning blame: include hidden directories, keep parent totals separate from their children, distinguish GiB from Docker's decimal GB, and label any unexplained remainder as unclassified rather than calling it projects.
- Separate re-downloadable installation caches from runtime assets: browser binaries, model weights, virtual environments and npm `_npx` directories may be actively used despite living under a cache path. Verify consumers before removal.
- Treat Docker reclaimable figures as estimates, not deletion promises; shared image layers, stopped containers and unattached volumes require separate inspection. A `tmp` filename, old timestamp or absence of an open file handle does not establish that a database is disposable.
- Report inventory, process liveness and functional health separately. Do not call an audit complete or a memory stack healthy when only selected directories and active unit labels were checked; an empty or failed health probe leaves that layer unverified.

Use `references/host-storage-audit.md` for the ordered measurement and cleanup-candidate workflow.

## Configuration and services

- Resolve the authoritative config path through the live Hermes command before editing; confirm YAML types after writes because JSON-looking lists can persist as scalar strings.
- Put adapter-specific `host`, `port`, and similar keys under the adapter's documented `extra` mapping when its loader reads `config.extra`; top-level lookalikes may be silently ignored.
- Keep dashboard frontend, dashboard server, and `api_server` gateway as separate services and ports. Bind remote-facing surfaces to loopback behind an approved tunnel or authenticated proxy; do not expose an insecure public bind by default.
- Rebuild frontend assets with the repository's working Vite path before serving changes, then restart only the dashboard owner and verify local and external HTTP status plus host-header behavior.
- Treat service state labels and PIDs separately. A failed unit with `MainPID=0` may be safely reset before replacement; never proceed while an old process remains.
- Avoid grep pipelines that close Hermes CLI stdout early and create false `BrokenPipeError` failures; query systemd or capture complete output instead.

## Runtime routing and delegation

- Separate picker identity from runtime provider, endpoint, protocol, model, and auth. Resolve the concrete target model at runtime for mixed catalogs.
- Use the existing Hermes child-agent/delegation path for workers. Give one objective with acceptance criteria, preserve inherited tool limits, session state, cancellation, tracing, and cost accounting, and reject ambiguous multi-task batches.
- Validate the full chain `requested tools → resolved tools → child registry → provider schemas → function call → Hermes result → continuation`; direct provider success is not Hermes E2E evidence.
- Route asynchronous provider jobs through a durable local correlation record, dedicated HTTPS callback, signature/replay checks, idempotent monotonic state transitions, bounded polling, and immediate result download. A completion callback is not necessarily progress.
- Keep model-family API modes and ID normalization at adapter boundaries. Do not forward unsupported cache, reasoning, parallel-tool, or body fields blindly.

## Profiles, sessions, and memory

- Resolve active profile and inherited config before auditing or migrating it. Preserve profile-local skills, plugins, cron references, session DBs, and auth stores; never assume the default profile owns another profile's state.
- Keep session SQLite as canonical verbatim conversation history, Hindsight/PostgreSQL as extracted durable knowledge, and Qdrant/hybrid search as an index; do not conflate counts, token totals, or retention semantics.
- Inject recalled memory through the intended ephemeral turn path, gate trivial prompts, cap server/client budgets explicitly, and do not claim a relevance threshold exists when the client receives no scores.
- Route stable preferences, identity rules, procedures, historical lessons, credentials, and raw session history to their correct stores rather than using `MEMORY.md` as a general dump. Enforce routing at the tool boundary when possible.
- Read databases read-only for audits, report logical versus physical storage separately, and account for FTS/index/snapshot duplication before making cleanup decisions.
- Treat context compaction as a lineage-preserving boundary operation: keep assistant tool calls with matching results, clamp invalid indices defensively, and prove a real post-boundary model call.

## Update-safe extension

- Keep custom plugins and backend policy outside the Hermes checkout where possible, use stdlib-only glue plus subprocess boundaries for external runtimes, and let Hermes' stable tool/agent seams own permissions and lifecycle.
- Before an update, record version, branch/dirty state, config/plugin inventory, and a backup strategy. Replay patch bundles on a clean base, run canonical gates, test in an isolated Hermes home, prove bad config fails closed, and verify rollback construction.
- After an update, verify exact version, plugin discovery/import, external CLI smoke, config migration, active process owner, gateway health, and no unintended driver/socket processes.
- Treat content hashes as byte identity, not safe provenance: a ledger blob can faithfully contain an external symlink target captured by an unsafe snapshot producer. Never restore archived supporting files through a loader unless snapshot-time containment is proven; fail closed and explicitly load the surviving canonical skill's own linked file instead.
- Before activating discovery-only skill prompts, verify `query` and `limit` on the installed native `skills_list` registry schema, then dispatch task query → returned skill name → full main document → a real returned linked reference. Use the actual service interpreter, copied real skills in an isolated HOME/HERMES_HOME, deny network and subprocess execution, and bypass preprocessing only when the native handler has no document-only flag. Report that bypass explicitly; this verifies document loading, not execution of the skill procedure.
- Deploy reviewed core patches only after matching both candidate review hashes and live pre-change hashes, preserving inherited local edits. Keep a mode-0700 release directory with exact backups, a checksum-guarded rollback command, and readback receipts. A fresh interpreter import proves installed code, not reloaded long-lived Gateway/Desktop modules; when activation is authorized, finish the narrow restart and runtime readback instead of stopping at an on-disk installation. Preserve cached conversation history rather than rewriting it to force new settings.
- Run a restart that can terminate its own agent through an independent durable supervisor, with health checks and a terminal receipt owned by that supervisor; loss of the delegation owner proves neither success nor failure. Recover by reading that receipt and checking the exact services, not by launching a second restart.

- Split mixed patch bundles by approved runtime file and corresponding behavioral tests; reproduce attribution failures on the actual dirty baseline before installing, because a reviewed neighboring projector does not authorize its activation.
- Verify the service interpreter independently of the developer environment; when pytest is absent, use isolated test-only dependency support after service packages and byte-identical official runner scripts against installed-code links, without modifying either live environment.
- Exercise rollback on a disposable copy with edited targets and corrupt backups before relying on it; refuse the entire restore during preflight when any owned hash differs.

## Payload and compression rules

- Measure the complete final request before building an optimization: include system text, current tool schemas and provider conversion, distinguish reconstructed samples from captured requests, and reject added persistence or routing complexity for negligible whole-request savings.
- Trace an enabled setting to the actual request call site before claiming an optimization is active; a dormant helper and its passing unit tests do not establish production behavior.
- For Walter Compress, prefer one small standalone Hermes plugin that reuses existing context, storage and delegation facilities. Borrow LCM recoverability and U-Fold goal/constraint tracking without automatically installing their entire architectures; Monsieur explicitly prioritizes simplicity over extra routers, stores or orchestration layers. Preserve useful cached context, avoid per-turn LLM recompilation and arbitrary small hard caps, and justify complexity through measured whole-task quality and cost. Qualify existing machinery and its smallest supported configuration before rebuilding storage or reconciliation; reject reuse that requires a large private adapter or sprawling configuration rather than assuming an established extension is compatible.
- Keep one host-visible compaction state owner and test the native baseline before attributing lifecycle failures to a plugin. Verify commit, rejection, cancellation, timeout and session-reset behavior for both transcript and bookkeeping (counter, previous summary, durable cooldown); a protected transcript does not prove that a stale worker cannot mutate a successor's state. Neither native inheritance nor an inner compressor establishes rollback safety.
- Select and protect active required skill instructions before requesting a summary, preserving complete tool groups; requiring every historical skill response to survive only after summarization can repeatedly discard completed summaries without making progress. Route structural no-ops through the existing backoff rather than introducing another retry loop.
- Bound exact-source recovery by source bytes and response bytes/tokens, including continuation within a single message; message-count pagination alone cannot bound a large tool output. Verify archive containment independently of content hashes, because matching bytes do not prove a safe filesystem origin.
- Require independent defect-reproduction and product-fitness gates: tests that pass by reproducing bugs are blocking evidence, not approval. Mocked summaries establish structural behavior, not semantic usefulness, actual cache savings or billing gains; keep those claims unverified until measured.
- Do not equate a lower token trigger with task-adaptive context management. For adaptive-compression requests, separately assess semantic summary quality, which evidence the current task needs, variable working-context size, recoverability and cache-rebuild cost; report threshold changes as guardrails, not completion of that objective. Attribute native repairs, borrowed LCM/U-Fold ideas and implemented plugin behavior separately; goal-conditioned summarization is not per-call semantic selection or a complete implementation of either research architecture.
- Explain cache friendliness through unchanged serialized prefixes and episodic rewrite costs, not fewer tokens alone. Distinguish deterministic retirement of old/large/duplicate tool results from proof that the model has absorbed their evidence; never promise immediate safe disposal after a tool has been read. Verify tail budgets, capped message floors, tool-group alignment and image/dedup exceptions before describing the recent tail as raw or guaranteeing a fixed last-N count.
- Prefer verified native compression budgets to another projection layer. Read the effective constructed trigger, output reservation and model overrides rather than interpreting the configured percentage literally; a compression trigger is not a guaranteed payload ceiling.
- Preserve required main and linked skill procedures, the current request and all pending parallel evidence. Test appending turns and toggling configuration against the existing serialized prefix; mutate historical prompt content only at an explicit compression boundary, while keeping canonical history recoverable.
- Preserve history after exhausted summarizer provider outages, including HTTP 5xx, and use the existing cooldown; never turn overload into permission for a lossy fallback. Prove that a successful permitted fallback still commits and a failed attempt does not advance compression state.
- For this user's optimization work, report only material progress, blockers and verified completion; do not turn each expected red-test subprocess notification into a user-facing failure report. Once the necessary scope is authorized, repair the demonstrated blocker and complete integration rather than cycling through new candidate architectures or repeated approval requests; parallelize independent core and plugin work, then test their combined artifact before activation.

Use `references/platform-operations.md` for the ordered payload audit, failure regressions and restart-receipt procedure.

## Evidence-oriented verification

1. Freeze the active state and scope.
2. Map the relevant config→runtime→transport→persistence path.
3. Make the smallest reversible change through the ledgered/configured interface.
4. Read back the exact changed target and inspect logs/status without secrets.
5. Run focused tests, then a deterministic end-to-end canary through the real Hermes path.
6. Recheck cleanup, caches, snapshots, session integrity, and external artifacts.
7. Report verified facts, remaining unknowns, and any untested paid/destructive gate.

## Historical source routing

Use `references/curator-source-routing.md` when the umbrella rules are insufficient. Before loading an archived source, confirm the actual archive root with `skill_view(name='.archive/<old-name>')`; only then use the original `file_path` returned by that result. Do not retry an old unqualified name after it has been archived.

## References

- `references/curator-source-routing.md` — explicit archive routes for absorbed Hermes platform procedures.
- `references/platform-operations.md` — compact configuration, routing, service, profile, session, memory, callback, and update decision tables.
