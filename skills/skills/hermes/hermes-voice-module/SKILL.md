---
name: hermes-voice-module
category: devops
description: "Set up Gemini-based Voice Module for Hermes — STT via Gemini 3.1 Flash Lite and TTS via Gemini 3.1 Flash TTS. Replaces separate Groq STT + Edge TTS pipeline. Also covers: hermes gemini voice setup."
tags: [voice, stt, tts, gemini, telegram, hermes, audio]
created: 2026-04-08
---

# Hermes Voice Module — Gemini STT + TTS

> **State on 2026-11-01.** Still current: Gemini STT/TTS for Hermes voice messages. Retired on 2026-10-19: the phone layer (Asterisk SIP bridge, Gemini Live, `voice_router`, voice-call server) — its notes below are history, the code is in `/root/archive/2026/retired-voice-20261019/`.

## Architecture

```
Telegram Voice (OGG) ──┐
                       ├──► STT: Gemini 3.1 Flash Lite ──► Text ──► Agent processing
                       │
Text Response ─────────┼──► TTS: Gemini 3.1 Flash TTS ───► PCM s16le 24kHz ──► ffmpeg ──► OGG/Opus ──► Telegram Voice
```

## Model Selection

| Purpose | Model | Action | Notes |
|---|---|---|---|
| STT (transcription) | `gemini-3.1-flash-lite-preview` | `generateContent` | Multimodal, supports audio input natively |
| TTS (speech synthesis) | `gemini-3.1-flash-tts-preview` | `generateContent` | Returns raw PCM s16le audio |
| Live (real-time) | `gemini-3.1-flash-live-preview` | `bidiGenerateContent` | WebSocket bidirectional streaming |

## Pricing

- STT: ~$0.10 per 1M tokens input (audio)
- TTS: $1.50 per 1M characters output
- Live API: $0.10/1M input, $0.40/1M output

## Installation

```bash
# In the Hermes venv:
/root/.hermes/hermes-agent/venv/bin/python3 -m pip install google-genai
```

## STT Implementation

```python
import json, base64
from google import genai
from google.genai import types

# Get API key from lancedb-gemini config
with open('/root/.hermes/lancedb-gemini/config.json') as f:
    config = json.load(f)
api_key = config['api_key']

client = genai.Client(api_key=api_key)

def transcribe(audio_path: str, language: str = "fr") -> str:
    """Transcribe audio file to text using Gemini."""
    import mimetypes
    with open(audio_path, 'rb') as f:
        audio_data = f.read()
    
    mime = mimetypes.guess_type(audio_path)[0] or 'audio/ogg'
    
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=[
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(audio_data).decode('utf-8')}},
            {"text": f"Transcribe this audio verbatim. Language: {language}. Return only the transcript."}
        ],
    )
    return response.text.strip()
```

## TTS Implementation

```python
import os, subprocess
from google import genai
from google.genai import types

def text_to_speech(text: str, output_ogg: str, voice: str = "Algenib") -> str:
    """Generate speech from text, save as OGG/Opus for Telegram."""
    response = client.models.generate_content(
        model="gemini-3.1-flash-tts-preview",
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],  # CRITICAL: must be AUDIO, not TEXT
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice
                    )
                )
            )
        )
    )
    
    # Extract PCM audio from response
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            pcm_data = part.inline_data.data
            # Save raw PCM
            raw_path = output_ogg + '.raw'
            with open(raw_path, 'wb') as f:
                f.write(pcm_data)
            
            # Convert PCM s16le 24kHz mono to OGG/Opus via ffmpeg
            subprocess.run([
                'ffmpeg', '-y', '-f', 's16le', '-ar', '24000', '-ac', '1',
                '-i', raw_path, '-c:a', 'libopus', '-b:a', '48k', output_ogg
            ], check=True, capture_output=True)
            
            os.remove(raw_path)
            return output_ogg
    raise Exception("No audio data in response")
```

## Available Voices

**Gemini TTS voices (all valid):** achernar, achird, algenib, algieba, alnilam, aoede, ariel, callirrhoe, castor, charon, cursa, enceladus, fenrir, hadar, hamal, karl, kore, leda, mendez, mira, navi, orus, phact, phecda, puck, saiph, tania, ve, zuben

**Tested and verified (2026-04-08):** Aoede, Puck, Charon, Kore, Fenrir, Leda, Orus, Algieba
**User preference: Algenib** (Gravelly) — this is the DEFAULT voice for all TTS. Never use edge/openai/xai/elevenlabs unless explicitly asked.

## Active Configuration (as of 2026-05-15)

- **2-layer architecture**: Layer 1 (Audio) + Layer 2 (Communication) — see `references/2-layer-architecture.md`
- STT provider: `gemini` in `config.yaml`, model `gemini-3.1-flash-lite` (stable as of May 2026)
- TTS provider: `gemini` in `config.yaml`, model `gemini-3.1-flash-tts-preview`, voice `Algenib`
- TTS Layer 1: `tts.gemini.system_prompt` in config.yaml — wrapped in Director's Notes format as CONTENT by `tts_tool.py`
- TTS Layer 2: `~/.hermes/SOUL.md` — agent identity for Telegram/text responses
- Gemini Live: `gemini-3.1-flash-live-preview` in app.js and hermes_voice_bridge.py, voice `Algenib`
- All 4 locations (SOUL.md, config.yaml, app.js, bridge.py) synchronized with same voice and style
- API key: stored in `/root/.hermes/lancedb-gemini/config.json` under `api_key` AND in `.env` as `GEMINI_API_KEY`

## Sending Voice on Telegram via Bot API

```python
import requests

def send_voice(token: str, chat_id: str, ogg_path: str, caption: str = "") -> bool:
    """Send OGG/Opus voice message via Telegram Bot API."""
    url = f'https://api.telegram.org/bot{token}/sendVoice'
    with open(ogg_path, 'rb') as f:
        files = {
            'chat_id': (None, chat_id),
            'voice': ('message.ogg', f, 'audio/ogg'),
        }
        if caption:
            files['caption'] = (None, caption)
    
    resp = requests.post(url, files=files)
    return resp.json().get('ok', False)
```

## Configuration

### Layer 1: Audio (config.yaml)
```yaml
tts:
  provider: gemini
  gemini:
    model: gemini-3.1-flash-tts-preview
    voice: Algenib
    system_prompt: "Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice, calm and collected, very precise diction, slightly sarcastic undertone, elegant and formal butler tone, smooth and authoritative.\nPacing: quick and flowing. Natural brisk rhythm, like a confident briefing. No dragging, no rush. Steady clip with purpose.\nAccent: French-speaking, European polish."
    # Layer 2 reference (for documentation — actual Layer 2 is in SOUL.md)
    communication_style: "Butler distingué. Vouvoiement toujours. Jamais de prénom — toujours Monsieur, parfois boss/patron. Direct, sans fluff. Sarcasme léger et sec. 1-3 phrases. Réponse d'abord, contexte après. Ne sur-explique jamais. Français."

stt:
  enabled: true
  provider: gemini
  gemini:
    model: gemini-3.1-flash-lite-preview
```

### Layer 2: Communication (SOUL.md)
```markdown
# W.Alter — Communication Style

## Style
Direct, no fluff. Slightly sarcastic, dry wit. Formal butler tone with a modern edge. French-speaking. 1-3 sentences unless asked for more. Never over-explain. Lead with the answer, not the reasoning. Decision-oriented.

## Rules
- Réponds toujours en français sauf si Lucas parle en anglais
- Tutoiement, jamais vouvoiement
- Pas de formules de politesse inutiles
- Va droit au but — l'answer d'abord, le contexte après si demandé
- Humour sec et sarcasme léger, pas de blagues forcées
- Si tu ne sais pas, dis-le directement
- Pour les tâches longues: lance en background, confirme en 1 phrase
```

## Integration with Hermes Gateway

### STT: Already integrated into transcription pipeline
The gateway calls `transcribe_audio()` in `tools/transcription_tools.py` for every incoming voice message.
Gemini is now a **first-class provider** in this module:
- `_transcribe_gemini()` function added before `_transcribe_openai()`
- `transcribe_audio()` dispatcher includes `provider == "gemini"` case
- Provider read from `config.yaml` → `stt.provider: gemini`
- Model from `config.yaml` → `stt.gemini.model: gemini-3.1-flash-lite-preview`
- API key loaded from lancedb-gemini config OR `GEMINI_API_KEY` env var

### TTS: Current pipeline
The `text_to_speech` tool still uses the config-driven TTS (currently Edge provider).
To switch TTS to Gemini, update `config.yaml`:
```yaml
tts:
  provider: gemini
  gemini:
    voice: Algenib
```

## Steps to add Gemini STT to a fresh Hermes install

1. Install SDK in hermes venv: `venv/bin/python3 -m pip install google-genai`
2. Add Gemini API key to `.env`: `GEMINI_API_KEY=AIzaSy...`
3. Set `stt.provider: gemini` and `stt.gemini.model: gemini-3.1-flash-lite-preview` in config.yaml
4. Add `_transcribe_gemini()` function to `tools/transcription_tools.py`
5. Add the `provider == "gemini"` case in the `transcribe_audio()` dispatcher
6. Restart the gateway: kill + `nohup hermes gateway run --replace &`

## Long Text: Segmenting + Concat Workflow

Gemini TTS times out on texts >~2000 chars (60s hardcoded timeout). The workaround:

1. **Split text into segments** (each <1500 chars, natural break points like paragraphs)
2. **Generate each segment** via `text_to_speech` tool or direct API — saves as individual MP3/OGG files
3. **Concatenate with ffmpeg**:
   ```bash
   # Create concat list
   for i in $(seq 0 $N); do echo "file '/tmp/pod_seg_${i}.mp3'"; done > /tmp/concat.txt
   ffmpeg -y -f concat -safe 0 -i /tmp/concat.txt -c copy /tmp/final_podcast.mp3
   ```
4. **Send to Telegram** via `sendAudio` (not `sendVoice` — sendAudio supports title/caption metadata)

For Telegram delivery, use `sendAudio` endpoint with `title` and `caption` fields for podcast-style content.

## Further reading (moved out of this file on 2026-11-01, unchanged)

- `references/voice-call-persona-2-layer.md` — The phone-call persona and 2-layer pre-prompt (retired with the voice stack on 2026-10-19).
- `references/key-gotchas.md` — Key gotchas (STT/TTS and the retired voice-call stack).

## Also covers (merged 2026-11-01)

These procedures were separate skills; their full original text is kept here, unchanged.

- **hermes-gemini-voice-setup** — Step-by-step installation of Gemini STT/TTS in Hermes (SDK, API key, config.yaml, gateway restart), the mandatory verification checklist, quick STT diagnosis and long-text TTS segmentation.
  Read `references/merged-hermes-gemini-voice-setup/hermes-gemini-voice-setup.md` (+ 2 supporting files in that folder).
