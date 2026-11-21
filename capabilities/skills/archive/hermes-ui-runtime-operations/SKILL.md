---
name: hermes-ui-runtime-operations
description: Use for Hermes UI, profiles, sessions, and runtime.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [hermes, desktop, dashboard, tui, profiles, sessions, compression]
---

# Hermes UI and Runtime Operations

Use this class-level skill for Hermes profile layout, dashboard/Desktop/TUI surfaces, session display, voice escalation, and context-runtime behavior. Keep renderer, gateway, profile, persistence, and provider layers separate because a successful check in one layer does not prove another.

## Always-on rules

- Identify the active Hermes home, profile, compiled client, gateway, interpreter, config source, and process owner before changing state.
- Preserve exact profile identity, provider/model route, session lineage, and auth scope; never silently substitute a default profile or endpoint.
- Prefer additive reversible changes and narrow restarts; preserve existing processes and user changes unless the requested operation explicitly owns them.
- Read back the exact changed target—config, process, endpoint, catalog, session, artifact, or rendered surface—before claiming success.
- Keep secrets, tokens, session identifiers, and private metadata out of logs, screenshots, artifacts, and summaries.

## Profile and artifact operations

1. Inventory live profile directories, manifests, schemas, runtime, tests, skills, and representative job artifacts; stale diagrams are not runtime evidence.
2. Resolve the process `ExecStart`, interpreter, working directory, and `HERMES_HOME`; the PATH CLI and active gateway may be different installations.
3. Keep `SOUL.md`, config, one canonical skill copy, runtime, workflow, schema, tests, and workspace data in distinct roles. Compare duplicate packages before removing one and search for old paths afterward.
4. Use one artifact pipeline: generate → validate → normalize only documented aliases → validate again → hash → atomic persist → mark validated.
5. Carry an explicit schema version, reject legacy shapes unless migration is requested, and keep analysis assets separate from provider references through explicit roles and hashes.
6. For remote delivery, probe capabilities, write, read back the exact result, write/read `RESULT`, then set and verify `FINISHED`; a local render is not delivery proof.
7. Compile affected modules, run deterministic tests, validate valid and deliberately invalid artifacts, exercise legacy detection, and report remaining unknowns.

## Surface selection

- **Dashboard:** user themes and display state come from the dashboard's discovered configuration/API and need refresh plus API/render readback.
- **Electron Desktop:** built-in themes and shortcuts come from compiled sources; user themes may be stored in localStorage; source edits require a rebuild, while injection requires a full relaunch and readback.
- **TUI:** Ink/React theme, role glyphs, reasoning, tool/brand icons, status, streaming, focus, and overlays are separate contracts; dashboard/Desktop changes do not propagate.

Ask which surface is intended before editing. Verify the active renderer after the change, use unique user-theme names to avoid silent collisions, and treat palette normalization or transparent foregrounds as possible load-success/render-failure cases.

## Desktop, remote, and session display

- Keep renderer, gateway, dashboard/API, relay, and local-permission layers distinct; a server source edit does not alter a compiled client without rebuild or verified runtime injection.
- Distinguish the embedded Desktop browser/pane from native OS browsers and remote/headless browser sessions; verify the visible surface rather than inferring it from HTTP success or a shortcut label.
- When old chats appear missing, distinguish a Home/project preview from the complete session list, use the current full-session control, and verify build/profile/backend/pagination before investigating deletion.
- Diagnose direct TUI, tmux, and cmux attachment separately. If the client is stuck, start a disposable recovery TUI in a new session, preserve the old process, and clean only the disposable repro.
- Verify dashboard/API health, authenticated HTTP, WebSocket, renderer state, audio-device ownership, provider registration, and final user-visible behavior independently.

## Voice and external-session escalation

External voice or messaging interfaces should provide origin and conversation context, not repeat Hermes identity already supplied by the system prompt.

Include:

- source/session identifier;
- a concise response instruction appropriate to the interface;
- timestamped verbatim conversation turns;
- duration or turn metadata when useful;
- the final request.

Preserve supported session continuity, parse session identifiers from the documented stream, and strip logs, JSON, and raw technical output before text-to-speech. Trace wake-word, batch STT→agent→TTS, push-to-talk, and realtime paths separately, using correlation/state checks to prevent duplicate events.

## Context and compression

- Measure context window, requested output budget, configured threshold, minimum floor, runtime compression events, resolver values, and provider metadata separately before naming a cause.
- Treat repeated compaction as a progress failure when protected head/tail messages, tool-pair integrity, fixed instructions, or schemas keep the post-compaction payload at the trigger.
- Clamp computed boundaries to `len(messages)` and add regression coverage for all-tool tails, because `head_end + 1` can exceed the list.
- Keep canonical ledger history, the in-memory transcript, and the provider prompt projection distinct; never mutate the ledger to save prompt tokens.
- Measure persisted role content separately from fixed instructions and serialized tool schemas before adding a projection or routing layer.
- Distinguish written, validated, and live configuration; a long-lived gateway needs a controlled restart before a source/config change is active.
- Preserve matching assistant tool calls and results across compaction, keep failed summarizer attempts from advancing state, and use existing cooldown/backoff rather than creating another retry loop.

## Verification

A completed operation has evidence for the exact layer changed: active profile/process identity, config readback, renderer or endpoint behavior, session continuity, focused tests, and any controlled restart. Report written-versus-live state and remaining untested layers separately.
