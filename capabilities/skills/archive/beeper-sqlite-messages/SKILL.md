---
name: beeper-sqlite-messages
description: Read Beeper messages directly from SQLite DB on Mac when the API fails (missing outgoing messages, pagination bugs). SSH + sqlite3 approach that returns both sides of every conversation.
tags: [beeper, sqlite, messages, mac, ssh, outgoing-messages]
---

# Beeper SQLite Direct Access

## When to Use

The Beeper Desktop API (`/v1/chats/{id}/messages`) has a known bug: **outgoing messages are never returned**. All messages appear as `isOutgoing: false` even on active conversations. When you need BOTH sides of a conversation, bypass the API and read the SQLite database directly.

**Symptoms:**
- API returns 20 messages, all from the contact, zero from Lucas
- Paginating deeper still returns zero outgoing messages
- The `isOutgoing` field is always `false`

## Prerequisites

- SSH access to Mac: `lucasjouvencon@100.127.150.1` (Tailscale, port 22)
- Beeper Desktop must be running (DB is locked otherwise)
- sqlite3 available on Mac (ships with macOS)

## Database

**Path:** `~/Library/Application Support/BeeperTexts/index.db`

**Key table:** `mx_room_messages` (NOT `messages` — that one is often empty)

### Schema (relevant columns)

| Column | Type | Description |
|--------|------|-------------|
| `isSentByMe` | INTEGER | **1 = Lucas**, 0 = contact |
| `timestamp` | INTEGER | Milliseconds since epoch |
| `roomID` | TEXT | Matrix room ID (`!xxx:beeper.local`) |
| `message` | JSON | Full message object |
| `type` | TEXT | `m.text`, `m.image`, `m.audio` |
| `isDeleted` | INTEGER | 0 = visible |

### Extract text from JSON

```sql
json_extract(message, '$.text')        -- message text
json_extract(message, '$.extra.type')  -- TEXT, VOICE, IMAGE, REACTION
```

Note: `text_content` column is often empty. Always use `json_extract(message, '$.text')`.

## Workflow

### Step 1: Find the room ID

```bash
ssh lucasjouvencon@100.127.150.1 "sqlite3 ~/Library/Application\\ Support/BeeperTexts/index.db \"
SELECT threadID, json_extract(thread, '$.extra.bridge.channel.id') as remote_id
FROM threads
WHERE json_extract(thread, '$.extra.protocol') = 'whatsapp'
LIMIT 20;
\""
```

Or use a known room ID from the Beeper API.

### Step 2: Query messages with direction

```bash
ssh lucasjouvencon@100.127.150.1 "sqlite3 ~/Library/Application\\ Support/BeeperTexts/index.db \"
SELECT 
  datetime(timestamp/1000, 'unixepoch', '+7 hours') as time,
  CASE WHEN isSentByMe = 1 THEN '→ Lucas' ELSE '← Contact' END as who,
  json_extract(message, '$.text') as text,
  json_extract(message, '$.extra.type') as msg_type
FROM mx_room_messages 
WHERE roomID = '!xxx:beeper.local'
AND isDeleted = 0
ORDER BY timestamp DESC
LIMIT 40;
\""
```

### Step 3: Voice notes

Voice notes have `msg_type = 'VOICE'` and empty text. Audio files are on disk:
```
~/Library/Application Support/BeeperTexts/media/local.beeper.com/<filename>
```

SCP to VPS, add `.ogg` extension, transcribe with Groq Whisper.

## Pitfalls

- **Port 22 vs 2222**: Use port 22 (Tailscale native SSH). The SSH config (`~/.ssh/config`) defaults to port 2222 (reverse tunnel). Override with direct `lucasjouvencon@100.127.150.1` which uses port 22.
- **Beeper must be running**: SQLite DB is locked when Beeper Desktop is closed.
- **Timestamps are UTC**: Add `+7 hours` for Bangkok (ICT).
- **text_content is often empty**: Always use `json_extract(message, '$.text')`.
- **REACTION type has no text**: Filter out with `msg_type != 'REACTION'` or handle empty text.
- **Group chats**: Check `$.extra.bridge.room_type` in threads table. `'dm'` = 1-on-1.
