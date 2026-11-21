---
name: beeper-messages
description: Read and analyze Beeper through Walter Memory first; use the native local Server MCP channel for fresh messages and Engine-authorized sends.
version: 1.5.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [messaging, beeper, chat, api, voice]
---

# Beeper Messages

Read the existing Memory history first. Changing Beeper's installation changes the live source, not Memory's history: never trigger a full reimport as a migration default.

## Reading and identifying the recipient

1. Use person_lookup for the person, their networks and full Matrix chat IDs; use memory_context for wider context.
2. Read memory_events(source="beeper", since=…, until=…, order="oldest") and its attachments. Ingestion is asynchronous: verify freshness before claiming every latest message is present.
3. Use beeper_read(operation="status"|"accounts"|"chats"|"messages"|"search", chat_id=…, query=…, cursor=…, direction="before", limit=…) for missing or fresh data. The native Server runs on Oracle; no Mac is needed.
4. Search is literal message search, not contact identity resolution. Match names/handles across the person's networks and the paginated chat list. Never infer the recipient from a matching word inside message text.

For a client using a reduced MCP toolset: walter_call(tool="beeper_read", arguments={…}); use describe=true if needed. Existing MCP connections may need reconnecting to discover the tool.

Resolve all named contacts before analysis. Do not assume that a chat title or username is the right person. Use full chat IDs beginning with !.

## Pagination, identifiers and dates

Use oldestCursor/newestCursor returned by the same installation and direction before/after. Cursors are opaque: do not construct one from sortKey or reuse a Mac cursor on Server. Stop on an empty page, hasMore=false, a date cutoff, or a repeated cursor.

Message IDs are installation-local. Memory keeps its canonical source IDs; the connector resolves shared chat/order metadata and validates time, direction and sender. Do not treat a local numeric ID as portable or create a second message store.

Messages arrive newest first. Sort ascending for presentation and verify actual timestamps before saying "hier" or "ce matin". lastActivity can reflect a reaction. Use full dates DD/MM HH:mm and convert UTC to the owner's timezone from their profile (Bangkok UTC+7 as of this instance), including the current time when timing matters. Clean rich text for presentation.

## Media and codes

Already ingested media/transcripts are in Memory attachments and Raw Vault. Use vault_search/vault_get for missing derived text, and audio_transcribe for audio through the Router. Do not recopy media from the Mac or call model providers directly.

The current Server exposes assets/download and assets/serve, used by the existing Memory media connector. Old references claiming that the API cannot serve media describe an older version.

Received verification codes: walter-secret otp locally; never show a code or token to the model or place it in argv, a URL or a unit. Try the authorized Gmail source if Beeper has no applicable channel. Do not assume SMS/iMessage exists: check connected accounts.

## Sending and permissions

Use beeper_send_message(chat_id, text, reply_to="") only through Walter Engine with an explicit owner request and an identified recipient. The existing Engine permission/disclosure plugin applies, including through walter_call. The writer is not exposed to external Codex/Claude clients or HTTP MCP; command and child execution are refused by the Engine policy.

Never replace this route with a curl/CLI POST from a shell to bypass the Engine gate. A send timeout means delivery unknown: inspect history before deciding on a retry. The transport never retries sends automatically. Never send test messages without explicit authorization.

## Operations

Current configuration comes from walter instance config core beeper.toml; credentials from the named Secrets grant, never pasted into a command. Native production services: beeper-server, walter-memory-beeper-watch, walter-memory-beeper.timer. Memory remains the only canonical store, jobs/checkpoints and bus.

Server 4.3.308 and CLI 0.6.4 were qualified on Linux ARM64 on 2026-11-16. Recheck official releases for a future deployment. Issues https://github.com/beeper/cli/issues/21 and /31 require a production/stable artifact and real chats/history/search tests; ready state or a populated SQLite DB alone is insufficient.

The WS is at-most-once with no replay; reconnect schedules bounded HTTP recovery. Older edits/deletions missed during an outage cannot be guaranteed by this protocol. Preserve old checkpoints when switching sources; no historical backfill without a reason and explicit scope.

Never reset a recovery key or add/remove/reconfigure existing bridges without the owner's approval. The Oracle Desktop rollback and first-import duplicate repair were still awaiting approval at qualification time; inspect the current change report before cleanup.
