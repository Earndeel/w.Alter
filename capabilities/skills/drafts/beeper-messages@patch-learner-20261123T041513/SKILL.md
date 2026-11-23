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

## Include Instagram voice notes in a Beeper analysis
1. Read the requested thread in chronological order with `tools.memory_events(thread_id=thread_id, since=start_utc, until=end_utc, order='oldest', limit=100)`. Pull an earlier window if the latest texts refer to a previous discussion. For an attachment or message that needs closer inspection, call `tools.memory_events(event_id=event_id)`. Decode the result with `json.loads` if it is a string, then read `events`.
2. Find Instagram voice notes in each event's `attachments`: select entries whose `name` starts with `audioclip` and that have an `object_id`. Keep each clip linked to its source event, timestamp, and sender. Do not skip a voice note because its filename ends in `.mp4`.
3. Download the selected clips with `await asyncio.gather(*(tools.vault_get(object_id=a['object_id']) for _, a in clips), return_exceptions=True)`, where `clips` contains `(event, attachment)` pairs. Pair each result with its original clip before filtering. Pass only returned absolute local paths (observed under `/tmp/walter-vault/`) to `tools.audio_transcribe(paths=paths)` in a Python tool call with `timeout_s=600`. Record exceptions and non-path results as missing media; do not let a failed download shift the mapping between transcripts and events.
4. Check which clips actually produced transcripts and match them back to the source events before integrating them into the timeline. State the date range and any missing audio in the analysis. Keep the workflow read-only: a request to analyze messages does not authorize sending a reply or updating a task. If `task_update` is refused for lack of Monsieur's approval, do not retry it or claim completion was recorded; deliver the analysis directly.

## Diagnose and reconnect the Instagram cloud bridge

1. Call `mcp__walter__beeper_read` with `{"operation":"accounts"}`. Confirm that Instagram needs reconnection and check whether the other accounts are affected. Use the latest Instagram event as evidence of the last observed delivery, not as the exact disconnect time. Query `core.events` using `source = 'beeper' AND payload->'chat'->>'network' ILIKE 'instagram%'`. If you need to search the nested JSON as text, cast `(payload->'chat')::text`, not `payload->'chat'::text`.
2. Prefer **Reconnect** in Monsieur's Beeper app on iPhone or Mac; it reconnects the same cloud account used by Beeper Server. If Instagram asks for an authenticator code, check Bitwarden for an OTP or recovery-code entry without printing its contents. Do not assume a code is available or change 2FA without separate approval. If an authorized password attempt returns `FI.MAU.META_RATE_LIMITED`, stop retrying. For an API password attempt, the bridge rejected a `fields`-only body; the request also needs `"type":"user_input"`.
3. If app reconnection is blocked but Monsieur's Mac Brave session is still signed in, confirm the Instagram profile matches the disconnected bridge account. Ask for explicit, one-time permission to transfer that session before reading any cookie values. For the previously successful implementation, consult `/root/.claude/projects/-root/memory/beeper-instagram-relogin.md` if present and inspect the current `/opt/walter-core/browser_auth.py` and installed Beeper SDK `src/resources/bridges/login-sessions/steps.ts`. Do not reuse the old scratchpad path, account IDs, step IDs, or login-session IDs.
4. In the approved transfer, start a fresh `POST /v1/bridges/instagramgo/login-sessions` with `{"flowID":"instagram","loginID":"<current existing bridge login ID>"}`. Read the returned step and its requested cookie fields; do not hard-code the field list. Run the reviewed one-shot helper with `walter-secret grant exec beeper-server --as engine -- /opt/walter-core/venv/bin/python -I "$SCRIPT"`. Keep cookie values in memory and send only the requested fields directly to the Beeper Server login step. Log only field names and status; never print or persist cookies, dump browser storage, or put credentials in command arguments. Stop on an account mismatch or a missing required cookie.
5. Recheck `mcp__walter__beeper_read` with `{"operation":"accounts"}` and confirm the same Instagram account is connected. Separately confirm fresh ingestion in `core.events`: discover timestamp columns with `SELECT column_name FROM information_schema.columns WHERE table_schema='core' AND table_name='events' AND data_type LIKE 'timestamp%';`. Compare the actual ingestion timestamp against the pre-reconnect baseline, and use `occurred_at` to identify backfilled events. Check both because backfilled messages can have old occurrence times. Use a bounded condition poll if needed, not a long fixed `sleep` followed by a command. Report connection and ingestion separately; do not infer complete recovery from a backfill count.
6. Close the temporary Walter browser session with `/opt/walter-core/bin/walter-browser -s ig-beeper close`. Tell Monsieur that signing out of Instagram in the source Brave profile may also disconnect Beeper. Leave 2FA unchanged unless separately authorized.
