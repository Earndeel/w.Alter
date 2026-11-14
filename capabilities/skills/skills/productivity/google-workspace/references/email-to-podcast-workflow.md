# Email-to-Podcast Workflow

Turn any email/newsletter into a short audio briefing and deliver it via Telegram.

## Step 1: Fetch & Extract

```bash
GAPI="$GPY $HOME/.hermes/skills/productivity/google-workspace/scripts/google_api.py"
$GAPI gmail get MESSAGE_ID   # returns JSON with "body" field
```

The `body` field may be **HTML** (not plaintext) when the email has no `text/plain` part.
Strip HTML before summarizing:

```python
import re, html
text = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL|re.IGNORECASE)
text = re.sub(r'<[^>]+>', ' ', text)
text = html.unescape(text)
text = re.sub(r'\s+', ' ', text).strip()
```

## Step 2: Write Podcast Script

Write a natural, conversational French script (or target language). Aim for 2-3 minutes.
Structure: intro hook → top stories (3-5) → quick-fire roundup → sign-off.
Save to `/tmp/podcast_<topic>.txt`.

## Step 3: Generate Audio with TTS

### Primary: Gemini TTS (best quality)
Use the `text_to_speech` tool. If it returns HTTP 429 (quota exceeded), fall back to edge-tts.

### Fallback: edge-tts (free, no API key, always available)

```bash
# Install once: pip install edge-tts
edge-tts --voice fr-FR-HenriNeural --rate="+10%" \
  --file /tmp/podcast.txt --write-media /tmp/podcast.mp3
```

**French voices:** `fr-FR-HenriNeural` (male), `fr-FR-DeniseNeural` (female)
**English voices:** `en-US-GuyNeural`, `en-US-AriaNeural`
**Rate:** `+10%` to `+20%` for podcast feel (slightly faster than default)

### Other TTS providers (in config.yaml priority order)
- **OpenAI** `gpt-4o-mini-tts` — good quality, costs tokens
- **ElevenLabs** — best quality, costs money
- **Mistral** `voxtral-mini-tts-2603` — check availability
- **Piper** — local, offline, decent quality

## Step 4: Send to Telegram

```bash
BOT_TOKEN="<token>"
CHAT_ID="<chat_id>"

curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendAudio" \
  -F "chat_id=${CHAT_ID}" \
  -F "audio=@/tmp/podcast.mp3" \
  -F "title=Podcast Title — Date" \
  -F "caption=🎙️ Short description of content"
```

Telegram accepts MP3 up to 50MB. `sendAudio` shows it as a playable audio player in chat.

## Pitfalls

- **Gemini TTS monthly quota** — Gemini TTS (flash-tts-preview) has a monthly spend cap. When exceeded, returns HTTP 429. Always have edge-tts as fallback.
- **edge-tts requires internet** — it's a cloud service (Microsoft), not local. But it's free and has no quota.
- **HTML email bodies** — newsletters (FT, Medium, etc.) almost always return HTML. Always strip tags before feeding to LLM summarizer.
- **Telegram caption encoding** — Unicode emoji in `caption` field works, but keep it short (< 1024 chars).
