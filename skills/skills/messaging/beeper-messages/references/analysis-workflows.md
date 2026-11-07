# beeper-messages — Full conversation analysis, batch media retrieval for one chat, the audio transcription pipeline, image analysis.

Moved verbatim from SKILL.md on 2026-11-01.

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
1. Walter Memory (`memory_search` / `person_lookup`) — past messages, sessions and the person card
2. Session history (`session_search`) — past W.Alter analyses that included the contact
3. Kardex PG (`SELECT * FROM kardex.messages WHERE sender ILIKE '%name%'`) — only if synced
4. Tell the user what's available vs. what's lost

**Kardex integration**: Beeper messages can be synced into the Kardex system (`kardex` skill) for persistent contact profiles, event extraction, and cross-source aggregation. Use `beeper_sync.py` for bulk sync.

