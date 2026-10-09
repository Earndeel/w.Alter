---
name: hermes-runtime-operations
description: "Use for Hermes runtime, profiles, sessions, and UI."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, runtime, profiles, sessions, dashboard, desktop, tui, memory]
---

# Hermes Runtime Operations

Use this class-level skill for Hermes configuration and runtime state, profiles, gateways, dashboard/Desktop/TUI surfaces, sessions, memory, context compression, provider routing, and live UI verification. Treat config, process, transport, persistence, client, and rendered UI as separate evidence layers.

## Freeze identity before changing state

- Resolve the active `HERMES_HOME`, profile, checkout, interpreter, version, config source, gateway/process owner, compiled client, and relevant session before reading or writing.
- Preserve exact profile identity, provider/model IDs, endpoint/API mode, tool permissions, session lineage, and auth scope; never substitute a default route or profile silently.
- Treat written config, loaded process state, provider catalog, session database, memory index, and client rendering as independent states. A successful check in one layer proves only that layer.
- Prefer the smallest additive and reversible change. Inspect ownership before restart/stop and never use broad process termination for cleanup.
- Keep secrets, tokens, session identifiers, cookies, and private metadata out of logs, screenshots, artifacts, and reports.

## Configuration, services, and routing

- Resolve the authoritative config through the live Hermes installation and verify YAML types after edits; adapter-specific `host`/`port` values belong under the loader's documented `extra` mapping when required.
- Keep dashboard frontend, dashboard/API server, `api_server` gateway, Desktop, TUI, and remote relays as separate surfaces and ports. Bind remote-facing interfaces to loopback behind an approved tunnel or authenticated proxy.
- Rebuild compiled clients through the repository's working path before serving source changes; a server edit does not update an Electron client without rebuild or verified runtime injection.
- Distinguish model picker identity from runtime provider, endpoint, protocol, model, and auth. Query the authenticated owner catalog for the exact case-sensitive model ID; a CLI inventory or generic `/v1/models` alias is not picker proof.
- For delegated workers, preserve objective, resolved profile, tools, cancellation, tracing, session lineage, provider schemas, usage, and cost. Verify the chain from requested tools through child registry, provider call, Hermes result, and continuation.
- For asynchronous provider jobs, persist correlation before polling, verify signatures/replay protection, use bounded polling and monotonic idempotent transitions, and download expiring artifacts immediately.

## Profiles, sessions, and memory

- Keep profile-local skills, plugins, cron references, session databases, and auth stores isolated; never assume the default profile owns another profile's state.
- Treat session SQLite as canonical verbatim history, PostgreSQL/Hindsight as extracted knowledge, and Qdrant/hybrid search as a derived index. Do not conflate token counts, record counts, and retention.
- Inject recalled memory through the intended ephemeral turn path, gate trivial prompts, cap budgets explicitly, and do not claim relevance scores or thresholds that the exercised client does not expose.
- Route identity rules, stable preferences, procedures, credentials, raw history, and extracted claims to their correct stores; do not use a general memory file as a data dump.
- Preserve assistant tool calls with matching results through compaction and provider conversion. Keep canonical history distinct from the provider prompt projection.

## UI and live desktop inspection

Choose the surface before editing: dashboard theme/API, compiled Electron source, runtime injection, TUI theme, or remote/headless browser. Verify the active renderer after changes; dashboard, Desktop, and TUI themes do not propagate automatically.

For a running development Desktop, use the documented CDP endpoint on loopback to answer factual questions about the live DOM, computed styles, geometry, console errors, and winning CSS rule. Prefer stable `data-slot` selectors, connect to the intended window, project evaluations into small JSON, and never relaunch or kill the user's app to obtain a port. CDP proves rendered facts, not whether a design looks good; use screenshots or user review for aesthetics.

When no port exists, use an isolated Electron instance with a separate `HERMES_HOME`, user-data directory, and CDP port. A throwaway renderer may have no backend and can exit while the DOM remains briefly readable; distinguish that from a production failure.

For missing sessions or chats, distinguish previews from the complete session list and verify build, profile, backend, and pagination before investigating deletion. For local media that will not open from chat, use the verified wrapper-and-preview workflow in `references/desktop-media-preview.md` instead of handing the renderer a raw `/tmp` path alone. For stuck TUI/tmux/cmux clients, start a disposable recovery client without disturbing the original and clean only the disposable process.

## Context, compression, and restarts

- Measure effective context length, output reservation, configured threshold, minimum floor, model overrides, runtime events, and provider metadata separately before naming a cause.
- Count the complete final request at the provider boundary, including system text, tool schemas, reconstructed samples, and serialized conversions; token estimates are not wire evidence.
- Keep raw ledger history and tool-pair integrity intact. Only mutate historical prompt content at an explicit compression boundary, and preserve the current request, required procedures, pending parallel evidence, and complete tool call/result groups.
- Treat repeated compaction, stale summary bookkeeping, failed summarizer attempts, or a fixed tail that omits required instructions as progress failures. Use existing cooldown/backoff rather than adding a second retry loop.
- Restart only the owner of changed code/config, then read back process identity, config, endpoint, session continuity, renderer state, and a real Hermes-path canary. Written-versus-live state must be reported separately.
- Run update or plugin changes in an isolated home, record version/dirty state and rollback inputs, prove incompatible configuration fails closed, and verify discovery/import, active process, gateway health, and rollback construction.

## Evidence-oriented completion

1. Freeze target and scope.
2. Map config → runtime → transport → persistence → client/rendering.
3. Make one reversible change through the approved/ledgered interface.
4. Read back every exact target affected.
5. Run focused tests and an end-to-end canary through the real Hermes path.
6. Recheck cleanup, session integrity, caches, snapshots, and external artifacts.
7. Report `MEASURED`, `OBSERVED IN CODE`, `RISK`, and `UNKNOWN` separately; a healthy HTTP response, visible picker row, passing unit test, or process label does not prove the other layers.
