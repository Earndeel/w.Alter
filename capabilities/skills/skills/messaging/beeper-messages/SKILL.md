---
name: beeper-messages
description: Read and interact with Beeper messages via the Beeper Desktop local REST API. Use when the user asks to check Beeper messages, read chats, or send messages on Beeper.
version: 1.2.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [messaging, beeper, chat, api, voice, osint, transcription]
---

# Beeper Messages

Access Beeper chats and messages via the Beeper Desktop local REST API.

## Prerequisites

- Beeper Desktop running on the remote machine (100.127.150.1 via Tailscale)
- API: `http://100.127.150.1:23373`
- Token: stored in vault — `vault get beeper/token`
- **Always get token from vault** — old hardcoded tokens expire

## Mandatory Temporal Context

When fetching Beeper messages, ALWAYS include:
1. Current time at moment of request (UTC+7 Bangkok)
2. All timestamps converted from UTC to UTC+7: `datetime.fromisoformat(ts.replace("Z","+00:00")).astimezone(timezone(timedelta(hours=7)))`
3. Full dates (DD/MM HH:mm) for situational awareness

This is critical for contextual understanding — Lucas needs to know if a message is from 5 minutes ago or 5 hours ago.

## Quick Reference

```bash
TOKEN=$(vault get beeper/token)
API="http://100.127.150.1:23373"

# List all chats
curl -s "$API/v1/chats" -H "Authorization: Bearer $TOKEN"

# Fetch messages from a specific chat
curl -s "$API/v1/chats/{chat_id}/messages?limit=10" -H "Authorization: Bearer $TOKEN"
```

## Chat ID Format

Chat IDs look like `!7Le8lDsatbsQfj7WHrk4:beeper.local` — they are Matrix room IDs.

## Response Structure

- Chats: `{"items": [...]}` — each item has `id`, `name`, `unreadCount`, etc.
- Messages: `{"items": [...]}` — each item has `senderName`, `text`, `timestamp`

## Pagination

### Chat list pagination (`/v1/chats`)

The chat list endpoint returns 25 chats per page. The response contains `oldestCursor` and `newestCursor` for pagination:

```python
import json, subprocess

token = subprocess.getoutput("vault get beeper/token").strip()
all_chats = []
cursor = None

while True:
    url = f"http://100.127.150.1:23373/v1/chats"
    if cursor:
        url += f"?cursor={cursor}"
    data = json.loads(subprocess.getoutput(f'curl -s "{url}" -H "Authorization: Bearer {token}"'))
    items = data.get("items", [])
    if not items:
        break
    all_chats.extend(items)
    cursor = data.get("oldestCursor")
    if not data.get("hasMore") or not cursor:
        break

# all_chats now contains ALL contacts (typically 200-300+)
```

### Message pagination (`/v1/chats/{id}/messages`)

The messages endpoint returns `hasMore: true` but **never sends `nextCursor`**. You MUST paginate using the **`sortKey`** of the oldest message on each page:

```python
cursor = None
while True:
    url = f"{API}/v1/chats/{chat_id}/messages?limit=50"
    if cursor:
        url += f"&cursor={cursor}"
    # ... fetch and process items ...
    cursor = items[-1].get("sortKey")
    if not cursor:
        break
```

This works because Beeper Desktop's API uses `sortKey` as an internal sequence number. Each page returns up to 20 items regardless of `limit`. **Full history can be very deep** — active chats return 400+ pages (8000+ messages). `hasMore` may remain `true` even when the next page is empty, so stop on: empty `items`, missing `sortKey`, `hasMore=false`, timestamp cutoff, or an explicit safety limit (e.g. 500 pages).

## Media Files (audio, images, voice notes)

**Media filtering:** before claiming photos were recovered, classify copied files by header/size/hash. See `references/media-filtering-kardex.md` for the Kardex/CL filtering pattern (real photos vs GIF stickers/placeholders vs view-once unrecoverable media).

**The API does NOT serve media files.** Attachments contain metadata only (`srcURL` is a local Mac filesystem path). However, W.Alter has SSH access to the Mac, so media CAN be accessed and processed.

See **`references/media-access-pipeline.md`** for the full pipeline:
- Copy files from Mac via SCP (`~/Library/Application Support/BeeperTexts/media/local.beeper.com/` — WhatsApp/Instagram voice notes and images live under `local.beeper.com/`, NOT the parent `media/` directory. The parent contains `beeper.com/`, `gitter.im/`, and `local.beeper.com/` subdirectories.)
- **Images**: Gemini 2.5 Flash via OpenRouter (free, ~2s)
- **Audio / voice notes**: MCP `audio_transcribe(paths=[...])` (Router `stt` poste, ~2 s per note, up to 20 files) after copying them to the VM — never a provider key under `walter-secret exec` (its output is discarded by design, so a transcript can never come back)
- ~5000 media files on disk, no extensions — use `file -b --mime-type` to detect type
- **Batch retrieval** for a specific chat: see `references/batch-media-retrieval.md`

**Note**: The built-in `vision_analyze` tool may or may not work depending on the session model. As of 2026-05, it worked with mimo-v2.5-pro (returned text descriptions). For guaranteed reliability, use OpenRouter directly with Gemini 2.5 Flash.

## Stripe 3DS Code Retrieval

Stripe sends verification codes via iMessage to `+•• •• •• •• 59`.
Chat: `stripelink` on `imessagecloud`, ID: `!0Yv8SCqY2O98k6y8V9wN:beeper.local`

```bash
TOKEN=$(vault get beeper/token)
curl -s "http://100.127.150.1:23373/v1/chats/!0Yv8SCqY2O98k6y8V9wN:beeper.local/messages?limit=1" \
  -H "Authorization: Bearer $TOKEN" | jq '.items[0].text'
# → "062680 is your Link verification code."
```

**User preference**: NEVER ask Lucas for a verification code. Always retrieve it from Beeper automatically. If Beeper is unreachable, try Gmail. Only ask as last resort.

## Remote Access
If Beeper Desktop has remote access enabled, MCP endpoint is at `http://192.168.1.35:23373/v0/mcp` (LAN) and OpenAPI at `http://192.168.1.35:23373/v1/spec`. Via Tailscale: `http://100.127.150.1:23373`. MCP requires auth token.

## Memory ingestion (Walter Memory)

Beeper messages are ingested automatically by the walter-memory Beeper connector (timer `walter-memory-beeper`, every 3 min, read-only Mac API; media go to the encrypted Raw Vault). To find past messages use `memory_search` / `person_lookup` (MCP) or `walter-memory search`. The former Hindsight connector notes are kept verbatim in `references/legacy-hindsight-ingestion.md` (Hindsight retired 2026-10-19).

## Contact Resolution
When the user gives a contact name that doesn't match any chat title:
1. **Check Walter Memory FIRST** — `person_lookup` / `memory_search` with the contact name. Past sessions often have the mapping (e.g. "Hani (WhatsApp) — projet PuttGame"). If it returns a match with a chat ID or network, use that directly.
2. Search ALL chats for partial matches (username, fullName, title, participant names)
3. If no match found, show the 15-20 most recent chats sorted by `lastActivity` so the user can identify the right one
4. Instagram usernames often diverge from real names (e.g. `shaulskayaa_` = "Charles Kaya") — don't assume the chat title matches the person's name

**Critical: the API returns max 25 chats.** Contacts inactive for 3+ days may fall off the list. If the user names a contact that was active recently (within a week) but isn't in the current list, check Walter Memory (`person_lookup`) — the contact likely existed but was pushed out by more recent chats.

Pattern: the user will often know someone by a different name than their handle. Show recent chats with network and participant info, let them pick.

**Confirm contact identity BEFORE deep-diving.** When the user names multiple contacts (e.g. "check Yohan and Hani"), resolve ALL of them first. If one is missing from the API, tell the user immediately rather than analyzing the wrong contact. Don't assume a chat that exists is the one they meant — the user knows their contacts better than the handle matching does.

## Critical: Message Fetching & Analysis Rules

1. **API returns messages NEWEST FIRST** — do NOT use `[-3:]` to get latest messages. Use `[:3]` instead. `[-3:]` gives the OLDEST messages on the page, not the most recent.
2. **Always verify dates before writing "hier", "ce matin", "hier soir"** — calculate `time_ago()` from actual timestamps. If a message is from 2 months ago, say "il y a 2 mois", NOT "hier soir".
3. **Sort messages chronologically** (oldest first) for display — `msgs.sort(key=lambda m: m["ts"])` after fetching.
4. **Clean HTML from text** — strip `<br>`, `<a>`, decode `&amp;` entities before displaying.
5. **Never assume temporal proximity** — a chat with `lastActivity` of 2 hours ago does NOT mean the last TEXT MESSAGE was 2 hours ago. The lastActivity may reflect a reaction, a read receipt, or an outgoing message not returned by the API.

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/pitfalls.md` — All known pitfalls (pagination, IDs, media, contacts, API quirks) — read before any long analysis.
- `references/multi-source-export.md` — Exporting a multi-source conversation with chronological merge and voice-note transcription.
- `references/analysis-workflows.md` — Full conversation analysis, batch media retrieval for one chat, the audio transcription pipeline, image analysis.
