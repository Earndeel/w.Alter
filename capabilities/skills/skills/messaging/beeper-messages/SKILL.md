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
- **Audio**: Groq Whisper large-v3-turbo (free, ~1s)
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

## Audio Transcription Pipeline

**Primary:** Groq Whisper (whisper-large-v3-turbo) — ~0.9s, gratuit, propre mais sans ponctuation riche.
**Fallback 1:** Gemini 3.1 Flash Lite (gemini-3.1-flash-lite-preview) — ~3s, gratuit, ponctuation complète + hésitations.
**Fallback 2:** Local faster-whisper (base model, CPU) — ~8s/file, zero API keys needed. Use when Groq/Gemini keys are expired or invalid.

```bash
# Groq (primary)
GROQ_KEY=$(vault get groq/api_key)
curl -s -X POST "https://api.groq.com/openai/v1/audio/transcriptions" \
  -H "Authorization: Bearer $GROQ_KEY" \
  -F "file=@audio.ogg" -F "model=whisper-large-v3-turbo" -F "language=fr"

# Gemini (fallback 1 — if Groq fails or returns empty)
GEMINI_KEY=$(vault get gemini/api_key)
AUDIO_B64=$(base64 -w0 audio.ogg)
curl -s "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key=$GEMINI_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"contents\":[{\"parts\":[{\"text\":\"Transcrits cet audio en français.\"},{\"inline_data\":{\"mime_type\":\"audio/ogg\",\"data\":\"$AUDIO_B64\"}}]}]}"

# Local faster-whisper (fallback 2 — zero API keys)
# Requires: uv venv /tmp/whisper_venv --python 3.11 && uv pip install --python /tmp/whisper_venv/bin/python faster-whisper
/tmp/whisper_venv/bin/python -c "
from faster_whisper import WhisperModel
model = WhisperModel('base', device='cpu', compute_type='int8')
segments, info = model.transcribe('audio.ogg', language='fr')
print(' '.join(s.text for s in segments))
"
```

**Logic:** Try Groq first. If HTTP error, empty text, invalid key, or timeout → fall back to Gemini. If Gemini key also invalid → fall back to local faster-whisper. The local fallback is ~8s per file on CPU but works with zero external dependencies once installed.

**Pitfall**: Vault may return masked keys (`***` or `sk-or-...5f43` with len=13) when accessed from `execute_code`. This happens for OpenRouter, Groq, and Gemini keys. If all API transcription fails with "Invalid API Key", switch to local faster-whisper immediately — don't waste time debugging vault masking.

## Image Analysis

**vision_analyze tool limitation:** If the current model doesn't support native vision (e.g., mimo-v2.5-pro), `vision_analyze` will fail with a 404 or fallback error. Use OpenRouter directly with a vision-capable model instead:

```bash
OPENROUTER_KEY=$(vault get openrouter/api_key)
IMAGE_B64=$(base64 -w0 image.jpg)
curl -s "https://openrouter.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"google/gemini-2.5-flash\",
    \"messages\": [{\"role\": \"user\", \"content\": [
      {\"type\": \"text\", \"text\": \"Describe this image.\"},
      {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/jpeg;base64,$IMAGE_B64\"}}
    ]}],
    \"max_tokens\": 300
  }"
```

**Tested models for vision:** google/gemini-2.5-flash (free via OpenRouter, ~2s).

## Hindsight Memory Integration

To ingest Beeper messages into Hindsight long-term memory, use the connector script at `/root/.hermes/scripts/memory_connectors.py --beeper`. Key details:

- Fetches from `/v1/chats` + `/v1/chats/{id}/messages` (NOT `/v0/messages` which 404s)
- Tracks last-seen timestamp per chat in `~/.hermes/scripts/.connector_state.json`
- Retains via `POST /v1/default/banks/walter/memories` with `{"items": [{"content": "...", ...}]}`
- Field name is `content`, NOT `text`
- Tokens must be read from vault (cron env has no env vars)

See `hindsight-qdrant-hybrid-search` skill → `references/memory-connectors.md` for full details.

## Memory Connector Integration

The memory connector (`/root/.hermes/scripts/memory_connectors.py`) ingests Beeper messages into Hindsight. Key learnings:

- **API endpoint**: Use `/v1/chats` (NOT `/v0/messages` which returns 404)
- **Token**: Read from vault `vault get beeper/token` (not env var — cron doesn't have it)
- **State tracking**: Incremental via `~/.hermes/scripts/.connector_state.json` — stores `beeper_last_seen` per chat ID
- **Hindsight endpoint**: `POST /v1/default/banks/walter/memories` with `{"items": [{"content": "..."}]}`
- **Cron schedule**: Runs at 5h daily via Hermes cron (job: Memory External Connectors)

## Batch Media Retrieval for a Specific Chat

The media directory has ~5500 files with no extensions and no chat association in the filename. To get images for a specific conversation:

1. **Fetch all attachment metadata via API** — paginate through `/v1/chats/{id}/messages` and collect all `attachments[].srcURL` values. Each `srcURL` is a `file://` path with the filename.
2. **Write filenames to a file on Mac** — SCP the list, then use a bash loop on Mac to check existence and get sizes.
3. **Filter stickers from real photos**:
   - GIF < 50KB → sticker/reaction (skip)
   - GIF 50-200KB → likely animated sticker (skip unless needed)
   - JPEG/PNG/WebP > 50KB → real photo (keep)
   - View-once placeholders: all exactly 43655 bytes, same md5 hash (skip)
4. **Batch SCP** the filtered set to VPS, then analyze.

```bash
# Full pipeline (Python orchestration recommended for >20 files)
# Step 1: Collect filenames from API pagination
# Step 2: Write to /tmp/filenames.txt on Mac
# Step 3: Filter by size/type on Mac
# Step 4: SCP filtered set to VPS
# Step 5: Add proper extensions via magic bytes
# Step 6: Analyze with OpenRouter vision
```

**Pitfall**: Shell argument length limit (~128KB). When batch-analyzing images, write OpenRouter payloads to JSON files and use `curl -d @file.json` instead of inline `-d '{...}'`. Better: use `execute_code` to orchestrate the full pipeline — it handles file I/O, subprocess calls, and avoids shell escaping issues entirely.

**Pitfall**: `file` command may not be installed on VPS. Use Python magic bytes instead:
```python
with open(path, "rb") as f:
    header = f.read(8)
if header[:3] == b'\xff\xd8\xff': ftype = "JPEG"
elif header[:8] == b'\x89PNG\r\n\x1a\n': ftype = "PNG"
elif header[:6] in (b'GIF87a', b'GIF89a'): ftype = "GIF"
elif header[:4] == b'RIFF': ftype = "WebP"
```

**Pitfall**: `&` backgrounding in terminal commands is forbidden. Use `terminal(background=true)` for long-lived processes, or sequential commands. For parallel SCP, run them sequentially — it's fast enough over Tailscale.

## Full Conversation Analysis Workflow

When the user asks to "analyze the full conversation" with someone, or to "build a profile" / "find out who someone is" — see also **`references/contact-profile-analysis.md`** for the identity research pipeline (multi-platform search, phone lookup, profile pic analysis).

1. **Resolve chat IDs FIRST** — paginate through ALL chats (not just 25) to find the contact. Use `oldestCursor` pagination. If the user names multiple contacts, resolve ALL of them before starting any analysis. **Never skip a contact** — if you can't find one after full pagination, tell the user immediately.
2. **Confirm which contact** — if multiple matches exist (e.g. two "Hani" chats with different IDs), show both and let the user pick.
3. **Fetch ALL messages** via paginated sortKey API (cap at ~400 pages / 8000 messages)
4. **Quantitative analysis**:
   - Message count per sender, ratio (e.g. "1.6x more from her")
   - Who initiates conversations (gaps >2-3h = new thread)
   - Questions asked per side (count `?` occurrences)
   - Emotional keywords per side (miss, love, sorry, feel, scared, tired, pain, etc.)
   - Average message length per sender
   - Message distribution by hour, day of week, and week
   - Media/attachment count per sender
4. **Timeline of key events** — extract dates with significant exchanges (arguments, reveals, plans, milestones)
5. **Dynamic assessment** — who invests more, communication patterns, tension points
6. **Retrieve and analyze media** — see `references/batch-media-retrieval.md`
7. **Summarize** — key themes, dynamic, timeline, not a raw dump
8. **For dating/romantic conversations**: analyze communication patterns, who initiates, response times, emotional dynamics, and suggest strategies

Lucas expects:
- **Direct analysis**, not a wall of raw messages
- **Insights** about the relationship dynamic, communication patterns
- **Actionable observations** (what's working, what's not, what to do next)
- Context from images/videos/voice notes when relevant
- French output by default (Lucas communicates in French)

**When a chat is not available in Beeper**, fall back to:
1. Hindsight memory (`hindsight_recall`) — fragments of past sessions
2. Session history (`session_search`) — past W.Alter analyses that included the contact
3. Kardex PG (`SELECT * FROM kardex.messages WHERE sender ILIKE '%name%'`) — only if synced
4. Tell the user what's available vs. what's lost

**Kardex integration**: Beeper messages can be synced into the Kardex system (`kardex` skill) for persistent contact profiles, event extraction, and cross-source aggregation. Use `beeper_sync.py` for bulk sync.

## Contact Resolution
When the user gives a contact name that doesn't match any chat title:
1. **Check Hindsight FIRST** — `hindsight_recall` with the contact name. Past sessions often have the mapping (e.g. "Hani (WhatsApp) — projet PuttGame"). If Hindsight returns a match with a chat ID or network, use that directly.
2. Search ALL chats for partial matches (username, fullName, title, participant names)
3. If no match found, show the 15-20 most recent chats sorted by `lastActivity` so the user can identify the right one
4. Instagram usernames often diverge from real names (e.g. `shaulskayaa_` = "Charles Kaya") — don't assume the chat title matches the person's name

**Critical: the API returns max 25 chats.** Contacts inactive for 3+ days may fall off the list. If the user names a contact that was active recently (within a week) but isn't in the current list, check Hindsight memory — the contact likely existed but was pushed out by more recent chats.

Pattern: the user will often know someone by a different name than their handle. Show recent chats with network and participant info, let them pick.

**Confirm contact identity BEFORE deep-diving.** When the user names multiple contacts (e.g. "check Yohan and Hani"), resolve ALL of them first. If one is missing from the API, tell the user immediately rather than analyzing the wrong contact. Don't assume a chat that exists is the one they meant — the user knows their contacts better than the handle matching does.

## Critical: Message Fetching & Analysis Rules

1. **API returns messages NEWEST FIRST** — do NOT use `[-3:]` to get latest messages. Use `[:3]` instead. `[-3:]` gives the OLDEST messages on the page, not the most recent.
2. **Always verify dates before writing "hier", "ce matin", "hier soir"** — calculate `time_ago()` from actual timestamps. If a message is from 2 months ago, say "il y a 2 mois", NOT "hier soir".
3. **Sort messages chronologically** (oldest first) for display — `msgs.sort(key=lambda m: m["ts"])` after fetching.
4. **Clean HTML from text** — strip `<br>`, `<a>`, decode `&amp;` entities before displaying.
5. **Never assume temporal proximity** — a chat with `lastActivity` of 2 hours ago does NOT mean the last TEXT MESSAGE was 2 hours ago. The lastActivity may reflect a reaction, a read receipt, or an outgoing message not returned by the API.


## Pitfalls

## Pitfalls

- **Beeper Desktop must be running**: If `curl` returns `HTTP 000` or `connection refused` on port 23373, Beeper Desktop is closed on the Mac. The Mac itself may be online on Tailscale but the app isn't running. Ask user to open Beeper Desktop or find alternative retrieval (Gmail for email codes, direct SMS access).
- **Chat list API returns 25 per page BUT supports cursor pagination**: `/v1/chats` returns 25 chats per page, sorted by `lastActivity`. The response includes `oldestCursor` and `newestCursor` fields. To get older chats, paginate with `?cursor=<oldestCursor>`. There are typically 200-300+ total chats. **Always paginate when a contact isn't in the first 25.** Do NOT conclude a contact doesn't exist until you've paginated through all pages (cap at 15 pages / ~375 chats). If a user asks about a contact that should exist but isn't in the first page: (1) paginate with cursor, (2) check Hindsight memory, (3) search session history via `session_search`. Do NOT give up and ask the user — paginate first.
- **Group Chat Exclusion**: When listing or checking messages, always exclude group chats. Focus strictly on private (1-on-1) conversations. Check `chat["type"] == "single"` — groups have `type: "group"`.
- **Kardex integration**: For full history sync into Kardex (schema `kardex` in PG), use `/root/.hermes/services/kardex/scripts/beeper_sync.py`. It handles chat pagination, HTML cleaning, deduplication, speaker direction, identity links, and stores raw JSONB. Fusion rule: auto-merge only on strong identity signals (`source_thread`/exact Beeper room, phone, email). Same display name or handle collision becomes a `kardex.contact_merge_candidates` review item, never an automatic merge. See `contact-intelligence-systems` skill for full documentation.
- **Message cleaning for storage**: Raw messages contain HTML (`<br>`, `<a>`), "Reacted to @...story" prefixes, and duplicate URLs. Strip before storing: `re.sub(r'<[^>]+>', '', text)`, `re.sub(r'Reacted to @\w+\'s story\s*', '', text)`, `re.sub(r'https?://\S+', '', text)`.
- **Direction attribution**: Preserve speaker direction from raw Beeper payload using `isSender` first and fallback `isOutgoing`; store as `sender='lucas'` vs `sender='contact'`. Do not infer direction from `senderName`, chat title, or message text. Any extraction/event/context layer must carry the speaker label explicitly (`Lucas` or contact name), otherwise Kardex will attribute Monsieur's plans/travel/preferences to the contact.
- **Voice messages**: Appear as empty `text` fields with `isVoiceNote: true` in attachments — cannot be transcribed without direct file access. Transcribe via SSH filesystem access: copy `.ogg` file from Mac to VPS, then use Groq Whisper (primary, ~0.9s) or Gemini 3.1 Flash Lite (fallback, ~3s). See Audio Transcription Pipeline section above. **MANDATORY**: When the user asks to "check messages" or "check what X sent", ALWAYS auto-transcribe any voice notes in the results WITHOUT being asked. Pipeline: get attachment `id` (MXC URI) from message detail → extract filename → `scp` from Mac `~/Library/Application Support/BeeperTexts/media/local.beeper.com/{filename}` → `ffmpeg -i file.ogg -ar 16000 -ac 1 file.wav` → Groq Whisper. Present transcript inline with the text messages. Never respond "it's an audio, I can't" — transcribe it.
- **Image files**: Same pattern — copy from Mac filesystem via SSH, then analyze with vision-capable model (e.g., google/gemini-2.5-flash via OpenRouter). The API only returns metadata, not image data.
- **View-once Instagram photos are NOT recoverable**: Instagram "view once" photos (the ones that say "This photo can only be replayed once") are stored by Beeper as identical placeholder GIFs — all exactly 43,655 bytes, same MD5 hash. The actual image content is ephemeral and not persisted on disk. When filtering media, detect and skip these by checking for duplicate file sizes in the 43-44KB range.
- **Sticker/reaction filtering**: Files with no extensions can be identified by magic bytes. GIF files (< 50KB) are almost always stickers/reaction GIFs. JPEG/PNG/WebP > 50KB are real photos. Some GIFs are large (1MB+) and are animated stickers, not photos. To reliably separate: check both size AND format.
- **Header**: Uses `X-Beeper-Desktop-Version: 4.2.742` in responses.
- **`hasMore: true` without `nextCursor`**: Not a bug — use sortKey pagination (see above).
- **Sorting chats by recency**: There is NO `lastMessage.timestamp` field on chat objects. Sort by `chat["lastActivity"]` (ISO 8601, e.g. `2026-05-18T18:04:08.785Z`). The `sortKey` is also available but `lastActivity` is human-readable and sufficient.
- **Contact discovery**: Chat list contains many "Unnamed" entries. The real name is in `chat["title"]` and for single chats, `chat["participants"]["items"][0]["fullName"]` or `["username"]`. Network comes from `chat["networkDisplayName"]` or `chat["accountID"]` (whatsapp, instagramgo, telegram, imessagecloud).
- **Unicode encoding in names**: Beeper returns display names with mathematical unicode characters (e.g. `𝙎𝙖𝙧𝙪𝙣𝙮𝙖 𝙏𝙞𝙥𝙖.`) that need `encode('unicode-escape', errors='ignore').decode()` for clean display.
- **Lost chat recovery — not all chats are synced to Kardex**: The memory connector (`memory_connectors.py --beeper`) only syncs chats that are in the 25-chat window AND have new messages since the last run. If a contact was active briefly and then dropped off, their messages may never have been synced to Kardex. In this case, only Hindsight fragments and session history remain. Always check Kardex with `SELECT DISTINCT sender FROM kardex.messages` before assuming data exists.

- **CRITICAL: Timestamps are UTC** — the Beeper Desktop API returns all timestamps in UTC. Lucas is in Bangkok (UTC+7). Always convert: `datetime.fromisoformat(ts.replace("Z","+00:00")).astimezone(timezone(timedelta(hours=7)))`. Display as `DD/MM HH:mm` format. Never display raw UTC timestamps — they cause systematic 7-hour offset errors.

- **Outgoing messages may not be returned**: The `/v1/chats/{id}/messages` endpoint may return ONLY the contact's messages, not the user's (outgoing) messages. Observed on WhatsApp chats: 128 messages returned, all with `isOutgoing: false` despite clear back-and-forth conversation. The contact's messages sometimes quote or reference what the user said, making the conversation reconstructable but incomplete. This is a Beeper Desktop API limitation, not a pagination bug. When performing conversation analysis, be aware you may only see one side. Check `isOutgoing` counts early to detect this — if outgoing count is 0 on an active chat, you're seeing half the picture.

- **Mac SSH tunnel drops after sleep**: The autossh reverse tunnel (Mac port 2222 → VPS) can die when the Mac sleeps. To make it permanent and auto-recovering, install a macOS LaunchAgent. See `references/mac-ssh-tunnel-setup.md` for the full plist and setup script. SSH access is required for ALL media operations (voice transcription, image analysis). If `ssh mac 'echo connected'` returns "Connection refused", the tunnel is down — ask the user to run the LaunchAgent setup or manually restart autossh.

- **Vault API keys may be masked in execute_code**: When running `vault get groq/api_key` or similar from `execute_code`, the vault may return masked values (`***` or truncated strings). The actual keys are only available to the Hermes agent's internal HTTP client. If API transcription fails with "Invalid API Key" for both Groq and Gemini, immediately fall back to local `faster-whisper` — don't retry or debug the vault.

- **Hindsight memory cross-contamination**: When multiple contacts are discussed in the same session, Hindsight may merge attributes from different contacts into a single memory entry. Example: analyzing contact A (Russian woman, couple dynamic) and contact B (PuttGame project) in the same session can produce a Hindsight memory like "Hani is a Russian woman in a couple relationship" — which is WRONG. Always cross-validate Hindsight contact attributes against the actual Beeper messages. If the Beeper chat is unavailable, flag the Hindsight data as potentially contaminated and ask the user to confirm key facts (gender, nationality, relationship type) before relying on them.

- **CRITICAL: Do NOT analyze the wrong contact.** When the user names multiple contacts (e.g. "check Yohan and Hani"), resolve ALL chat IDs first. If one is missing from the initial 25-chat window, PAGINATE to find it before doing anything else. Never start analyzing the contacts you DID find and ignore the ones you didn't — the user listed them together for a reason. If you can't find a contact after full pagination, tell the user immediately and ask for the platform/handle. **Never assume a contact doesn't exist** — with 275+ chats in Beeper, it almost certainly does.

- **Do NOT analyze a different contact when the user asks about a specific one.** If the user asks about "Hani" and you can't find Hani, do NOT pivot to analyzing "shaulskayaa_" or another contact instead. Tell the user you're still looking, paginate further, or ask for clarification. Analyzing the wrong contact wastes the user's time and erodes trust.

- **Telegram delivery of Beeper summaries**: When sending Beeper conversation summaries to Telegram, **use plain text (no parse_mode)**. Telegram's MarkdownV2 requires escaping `(`, `)`, `-`, `.`, `!`, `=` with `\\` prefix — this is extremely fragile for multi-paragraph reports with parentheses and hyphens. Write the payload to `/tmp/tg_payload.json` and use `curl -d @/tmp/tg_payload.json` to avoid shell escaping issues. Only use MarkdownV2 for short messages with no special characters.

## Exporter une conversation multi-source avec fusion chronologique et transcription des vocaux

Pour produire un export combiné Instagram/WhatsApp depuis Beeper, procéder ainsi :

1. Créer un répertoire de travail temporaire et extraire les événements Beeper avec `walter-memory` :

```bash
mkdir -p /tmp/claude-alina
cd /tmp/claude-alina
walter-memory events --source beeper --since YYYY-MM-DD --limit 100000 > beeper_raw.json
```

2. Identifier les fils cibles dans `beeper_raw.json` en recherchant le nom, le pseudo et les champs `payload`, puis vérifier les `thread_id` retenus avant de filtrer. Conserver les deux fils dans un ensemble explicite, par exemple `T = {'<instagram-thread-id>', '<whatsapp-thread-id>'}`. Ne pas déduire l'identité d'un fil uniquement à partir de son titre si plusieurs conversations portent le même nom.

3. Pour les médias audio, rechercher les objets Raw Vault associés aux fils dans PostgreSQL si `walter-memory objects search` ne fournit pas assez de métadonnées :

```bash
export PGPASSFILE=/root/.pgpass
psql -h 127.0.0.1 -p 5433 -U hindsight -d hindsight -Atc "select id::text, kind, mime, original_name, captured_at, size_bytes, storage_zone, storage_key, source_ref::text, meta::text from core.objects where source='beeper' and kind='audio' order by captured_at desc"
```

Utiliser `/opt/walter-memory` et le module `walter_memory.objects.get_object` pour récupérer les fichiers par identifiant, au lieu d'exposer ou de copier des identifiants d'accès au stockage. Vérifier que `source_ref` relie bien l'objet au `chat_id` et au `message_id` de l'événement.

4. Extraire les vocaux dans un sous-répertoire temporaire, puis les convertir avec `ffmpeg` si nécessaire. Utiliser le fournisseur STT installé dans `/root/.hermes/plugins/gemini-stt/__init__.py` via l'environnement `/root/.hermes/hermes-agent`. Vérifier la disponibilité de `ffmpeg` et de `ffprobe` avant la transcription. Enregistrer pour chaque vocal le statut, le texte, le message source et l'éventuelle erreur.

5. Fusionner les événements des deux fils après filtrage, en triant par `occurred_at` et en imposant l'ordre des messages reçus/envoyés avant les événements de modification ou de suppression lorsque les timestamps sont identiques :

```python
src.sort(key=lambda e: (
    e['occurred_at'],
    0 if e['event_type'] in ('message.received', 'message.sent') else 1,
))
```

Convertir ensuite les timestamps UTC en `Europe/Paris` avec `zoneinfo.ZoneInfo`, et conserver une étiquette de source distincte telle que `[IG]` ou `[WA]` sur chaque ligne.

6. Préserver les événements édités, supprimés, réactions et messages éphémères dans la chronologie. Si l'export ne contient pas le texte original d'une modification, marquer seulement `(modifié)` et indiquer que le texte disponible est celui de l'export. Si un vocal supprimé n'a plus d'objet Raw Vault, le conserver comme vocal supprimé sans inventer de transcription.

7. Rendre le fichier Markdown avec un script séparé. Remplacer les retours `<br>` par de vrais retours à la ligne avant rendu et vérifier que les vocaux transcrits sont repérables. Effectuer des contrôles de cohérence avant livraison : nombre d'événements par source, nombre de vocaux, nombre de transcriptions réussies, présence des bornes temporelles, absence de `<br>` résiduels et inspection du début, de la fin et de quelques lignes de vocaux, réactions et modifications.

8. Écrire le résultat dans `/root/reports/<contact>-instagram-whatsapp-<début>_<fin>.md`, puis supprimer le répertoire temporaire contenant les dumps JSON et les fichiers audio :

```bash
rm -rf /tmp/claude-alina
```

Pièges à vérifier : `walter-memory events` renvoie parfois davantage d'événements que les seuls messages, les vocaux peuvent être référencés dans `core.objects` plutôt que dans l'événement lui-même, un message supprimé peut ne plus avoir de média récupérable, plusieurs événements peuvent partager exactement le même timestamp, et l'export d'un message modifié peut ne pas contenir son texte précédent.
