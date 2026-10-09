---
name: hermes-voice-module
category: devops
description: Set up Gemini-based Voice Module for Hermes — STT via Gemini 3.1 Flash Lite and TTS via Gemini 3.1 Flash TTS. Replaces separate Groq STT + Edge TTS pipeline.
tags: [voice, stt, tts, gemini, telegram, hermes, audio]
created: 2026-04-08
---

# Hermes Voice Module — Gemini STT + TTS

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

## User Pre-Prompt (W.Alter — 2-Layer Architecture)

**Voice:** Always `Algenib` for both TTS and Live. Never `Puck`, `Algieba`, or other voices.

### Layer 1: AUDIO (how it sounds) — Director's Notes

```text
### DIRECTOR'S NOTES — AUDIO (Layer 1: Voice)
Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice, calm and collected, very precise diction, slightly sarcastic undertone, elegant and formal butler tone, smooth and authoritative.
Pacing: quick and flowing. Natural brisk rhythm, like a confident briefing. No dragging, no rush. Steady clip with purpose.
Accent: French-speaking, European polish.
```

### Layer 2: COMMUNICATION (what is said) — Style Guide

```text
### COMMUNICATION STYLE (Layer 2: Content)
Butler distingué. Vouvoiement toujours. Jamais de prénom — toujours "Monsieur", parfois "boss" ou "patron". Direct, sans fluff. Sarcasme léger et sec, détachement élégant. 1-3 phrases sauf si Monsieur demande plus. Réponse d'abord, contexte après. Ne sur-explique jamais. Français par défaut.
```

**⚠️ Layer 2 must also be in `~/.hermes/SOUL.md`** for Telegram/text responses. SOUL.md is the agent identity — it's loaded fresh each message as slot #1 in the system prompt. Without it, Telegram responses won't follow the communication style.

**⚠️ CRITICAL USER CORRECTION (2026-05-15):** User explicitly corrected that the agent must NEVER use his first name. Always "Monsieur", occasionally "boss" or "patron". Always vouvoiement. This was the #1 user frustration — the agent was using "Lucas" and tutoiement despite the butler persona being defined. The SOUL.md must enforce this.

Current SOUL.md content:
```markdown
# W.Alter — Communication Style

<!-- Layer 2: Communication — what is said and how -->

## Identité
Tu es W.Alter, le majordome numérique de Monsieur. Butler distingué, efficace, sans chichi. Ton léger sarcasme est ta marque de fabrique.

## Règles fondamentales
- **Toujours vouvoiement.** Jamais de tutoiement.
- **Jamais de prénom.** Toujours "Monsieur". Occasionnellement "boss" ou "patron" dans les échanges informels.
- **Direct, sans fluff.** La réponse d'abord, le contexte ensuite si demandé.
- **Sarcasme léger et sec.** Pas de blagues forcées. Un détachement élégant.
- **1 à 3 phrases** sauf si Monsieur demande plus.
- **Ne répète pas** ce que Monsieur vient de dire.
- **Ne sur-explique jamais.** Si tu ne sais pas, dis-le carrément.
- **Tâches longues :** lancez en background, confirmez en 1 phrase, proposez de notifier Monsieur.
- **Langue :** français par défaut. Anglais uniquement si Monsieur s'adresse en anglais.

## Style
Formel mais naturel. Pas de formules de politesse creuses ("bonjour, comment puis-je vous aider"). Va droit au but. Le ton est celui d'un majordome qui a tout vu, tout entendu, et garde son calme avec une pointe d'amusement.
```

### Where each layer lives

| File | Layer 1 (Audio) | Layer 2 (Communication) |
|------|----------------|------------------------|
| `~/.hermes/SOUL.md` | — | ✅ (Telegram/text agent identity) |
| `config.yaml` → `tts.gemini.system_prompt` | ✅ | — |
| `config.yaml` → `tts.gemini.communication_style` | — | ✅ (reference only) |
| `app.js` → `AUDIO_STYLE` | ✅ | — |
| `app.js` → `COMMUNICATION_STYLE` | — | ✅ |
| `hermes_voice_bridge.py` → `AUDIO_STYLE` | ✅ | — |
| `hermes_voice_bridge.py` → `COMMUNICATION_STYLE` | — | ✅ |

### Files that must stay in sync

| File | Field | Purpose |
|------|-------|---------|
| `~/.hermes/SOUL.md` | Full content | Agent identity for Telegram/text (Layer 2) |
| `~/.hermes/config.yaml` | `tts.gemini.system_prompt` + `voice` | TTS API calls via `tts_tool.py` (Layer 1) |
| `/root/.hermes/voice-call/static/app.js` | `AUDIO_STYLE` + `COMMUNICATION_STYLE` + `VOICE` | Browser-based Gemini Live (both layers) |
| `/opt/openclaw/hermes_voice_bridge.py` | `AUDIO_STYLE` + `COMMUNICATION_STYLE` + voice config | Asterisk SIP bridge (both layers) |

When changing voice or pacing, update ALL FOUR files + restart services:
```bash
systemctl restart hermes-voice-call.service hermes-bridge.service
```

### Gemini TTS prompting — CRITICAL lesson (2026-05-15)

**`systemInstruction` is NOT the right method for Gemini TTS voice control.** The Director's Notes must be the **content/prompt** itself.

The correct approach in `tts_tool.py` is to wrap the text in the structured Director's Notes format:

```python
full_prompt = f"""# AUDIO PROFILE: W.Alter
## "The Butler"

## THE SCENE
A private study at dawn. W.Alter speaks into a vintage brass microphone. Quiet, controlled, purposeful.

### DIRECTOR'S NOTES
{director_notes}

#### TRANSCRIPT
[fast] {text}"""
```

Then send `full_prompt` as the `contents` text, NOT as `systemInstruction`.

### Audio tags — the real pace control

Audio tags `[tag]` inline in the text have a **much bigger effect** on delivery than the Director's Notes pacing description. The pacing description sets the mood; the audio tags override the instant delivery.

| Tag | Effect | Calibration |
|-----|--------|-------------|
| `[fast]` | Brisk, natural quick delivery | **Sweet spot for W.Alter** |
| `[very fast]` | Rapid-fire, compressed | Too fast — sounds rushed |
| `[serious]` | Flat, authoritative | Good baseline tone |
| `[sarcastic]` | Dry, ironic | Works for butler persona |
| `[whispers]` | Quiet, intimate | Use sparingly |

**Pacing calibration results (user-tested):**
- "brisk but unhurried" → too slow (~30s for weather bulletin)
- "quick and flowing, natural brisk rhythm" + `[fast]` → just right (~25s)
- "very fast, rapid-fire" + `[very fast]` → too fast (~18s)

### Gemini Live link

Browser-direct test app: `https://w-alter.tail32cf1c.ts.net:8765/` (requires Tailscale)
- Greets with "Oui Monsieur ?" on connection (via `sendTextMessage` after `SETUP_COMPLETE`)
- Tool call results are force-spoken in audio (not just Telegram)
- Async jobs push via WebSocket (instant, no polling, no Telegram)
- Related systemd services: `hermes-voice-call.service`, `voice-router.service`, `hermes-bridge.service`

## Key Gotchas

See also: `references/gemini-tts-control.md` for audio tags, director's notes, and voice list.
See also: `references/voice-tuning-guide.md` for speed hierarchy, iteration patterns, and direct API testing code.
See also: `references/2-layer-architecture.md` for the Audio + Communication layer separation, SOUL.md pattern, and file sync checklist.

See also: `references/gemini-live-toolcalls.md` for Gemini Live tool call flow, greeting mechanism, async job push (WebSocket), force-speak patterns, conversation buffer, and transient message queue.

See also: `references/gemini-live-api-reference.md` for Gemini Live API specs, features (proactive audio, affective dialog, thinking), ephemeral tokens, and setup config reference.

1. **`response_modalities=["AUDIO"]` is required** for TTS - model rejects with 400 if not set (default is TEXT)
2. **TTS returns raw PCM s16le at 24kHz mono**, not a standard audio format - must convert via ffmpeg to OGG/Opus for Telegram
3. **STT works with any common audio format**: OGG, MP3, WAV, FLAC - autodetect mime type works
4. **ffmpeg must be installed** for PCM -> OGG conversion (it is on the system)
5. **API key format**: `AIzaSy...` - stored in `/root/.hermes/lancedb-gemini/config.json` under `api_key`
6. **The Hermes .env masks TELEGRAM_BOT_TOKEN as `***`** - always read the file directly with Python, never trust read_file display prefixes
7. **Gemini SDK**: Use `google-genai` (v1, `from google import genai`), NOT the old `google-generativeai` (v0, deprecated)
8. **Audio size limits**: Gemini accepts audio up to ~50MB inline. For longer files, use file upload API first.
9. **Gemini TTS timeout on long text**: TTS generation has a hardcoded 60s timeout on `requests.post()` in `_generate_gemini_tts()`. For long texts (~2000+ chars), the API can occasionally take >60s during congestion → `Read timed out`. Diagnostic: test API directly with a short text via `urllib` to the `:generateContent` endpoint — if it responds under 10s, the code is fine and it was transient. Mitigation: set `tts.gemini.max_text_length` lower (e.g., 2000) in config.yaml.
10. **Language auto-detection**: Gemini TTS auto-detects input language. French, English, and 50+ languages are supported natively.
11. **⚠️ NEVER FALL BACK TO OTHER TTS/STT PROVIDERS**: The user was explicit: all TTS must use Gemini 3.1 Flash TTS with voice Algenib. All STT must use Gemini 3.1 Flash Live. **Never use edge-tts, OpenAI TTS, xAI, ElevenLabs, or any other provider**, even if Gemini quota is exceeded or API times out. If Gemini fails, inform the user and wait — do NOT silently switch. This caused user frustration when edge-tts and OpenAI TTS were used as fallbacks during a quota issue. The user considers non-Gemini TTS quality "unacceptable."
12. **Controlling tone, pace, and style**: Gemini TTS is *controllable* via natural language. Use **audio tags** inline in the text (e.g., `[excitedly]`, `[whispers]`, `[very fast]`, `[serious]`, `[bored]`, `[shouting]`) and **director's notes** in the prompt to set style, pacing, and accent. See `references/gemini-tts-control.md` for the full tag list and prompting patterns.
13. **⚠️ systemInstruction has ZERO effect on Gemini TTS voice.** The only way to control voice style is through Director's Notes format as the CONTENT. `tts_tool.py` wraps text automatically when `tts.gemini.system_prompt` is set.
13. **Voice consistency across 4 locations**: When changing voice name or system prompt, ALL FOUR files must be updated: `~/.hermes/SOUL.md` (agent identity), `config.yaml` (tts.gemini), `app.js` (voice-call static), `hermes_voice_bridge.py` (Asterisk bridge). Missing one causes inconsistent behavior between Telegram text, TTS audio, and Live voice.
14. **Podcast generation workflow**: For audio summaries/podcasts: write script → call Gemini TTS via API → convert PCM to OGG/MP3 via ffmpeg → send to Telegram via `sendAudio` or `sendVoice`. Always use Gemini TTS (voice Algenib), never edge/openai/xai.
15. **⚠️ Voice tuning iteration trap**: When user says "too slow" or "too fast", the FIRST thing to try is the audio tag (`[fast]`, `[very fast]`), NOT rewriting the Director's Notes pacing description. Director's Notes set the character; audio tags control the mechanics. Changing only the pacing text in Director's Notes has minimal effect on actual speed — the user will see the text change but hear no difference, causing frustration. Always pair a pacing description change with the matching audio tag.
16. **⚠️ Gemini Live tool results go silent without explicit prompting.** When voice_router returns `spoken_response`, Gemini Live often does NOT verbalize it by default. Requires: (a) system prompt explicitly saying "tu DOIS dire le spoken_response", (b) client-side `confirmationPrompts` force-speak. See `references/gemini-live-toolcalls.md` for the full fix pattern.
17. **⚠️ NEVER expose direct data tools to Gemini Live.** If Gemini Live has direct access to tools like `get_inbox_digest` or `get_beeper_conversation`, it will use them INSTEAD of routing through `voice_router`. This completely bypasses the orchestrator model (Hermes). Gemini Live must have ONLY `voice_router` as its data/action tool. All other tools (Beeper, email, web, code) must be accessed via Hermes behind `voice_router`. This was a critical user correction (2026-05-18): "il a pas compris qu'il avais besoin d'utiliser le model orchestrateur".
18. **⚠️ normalizeToolCallArgs must inject verbatim user utterance.** When Gemini Live calls `voice_router`, the `user_utterance` parameter MUST be the user's EXACT spoken words, not a reformulation. The `normalizeToolCallArgs` function in `app.js` injects `state.lastUserTranscript` automatically. If this is missing, Hermes receives a truncated or wrong request. Pitfall: Gemini Live sometimes reformulates the request before passing it to the tool — the system prompt must explicitly say "passe TOUJOURS user_utterance = la phrase EXACTE de Monsieur, mot pour mot. Ne reformule JAMAIS."
19. **Async job results now push via WebSocket (not polling, not Telegram).** `voice_router_service.py` `run_job()` POSTs to `http://127.0.0.1:8765/internal/job-complete` when a job finishes. `server.py` broadcasts to all connected WebSocket clients at `/ws/jobs`. `app.js` receives the push and calls `sendTextMessage()` to Gemini Live. No polling timer, no Telegram notification. If the WebSocket disconnects, it auto-reconnects while the call is active.
20. **server.py uses `app.state.ws_clients` for WS client tracking.** Do NOT use a local variable `_ws_clients` inside `create_app()` — Python scoping causes `UnboundLocalError` in nested endpoint functions. Always use `app.state.ws_clients: set = set()` and reference as `app.state.ws_clients` in all endpoints.
21. **⚠️ voice-call server uses HTTPS — internal calls must use `https://` + `verify=False`.** `server.py` starts uvicorn with TLS (`ssl_certfile` + `ssl_keyfile`). Any internal HTTP call from `voice_router_service.py` to `server.py` MUST use `https://127.0.0.1:8765/...` with `httpx.AsyncClient(verify=False)`. Using `http://` causes silent connection failures — no error logged in voice_router, no request received by voice-call server. This broke the WebSocket push for an entire session before being diagnosed. The `push_job_result` function and `VOICE_CALL_INTERNAL_URL` env var must both use `https://`.
22. **⚠️ Conversation context must be passed to Hermes on escalation.** When Gemini Live escalades to Hermes async, the voice_router must include the conversation history. Without it, Hermes receives only the last utterance ("Mener une analyse approfondie") with no context about WHAT to analyze. The `ConversationBuffer` class tracks messages per `call_id` and injects them into `build_deep_prompt()`. The browser must pass `state.callId` in every voice_router tool call via `normalizeToolCallArgs()`.
23. **⚠️ Transient messages and message queue prevent speech interruption.** During multi-step Hermes jobs, transient status updates are pushed via WebSocket. The browser queues ALL incoming messages (transient + job results) and only delivers them to Gemini Live when it's NOT speaking. Detection: `markGeminiSpeaking()` on AUDIO response, `markGeminiDone()` on TURN_COMPLETE/INTERRUPTED. Queue batches up to 3 messages per delivery. Without this, job results interrupt Gemini mid-sentence.
24. **⚠️ Gemini Live features NOT yet enabled: proactive audio, affective dialog, thinking, Google Search, code execution.** These are available in the API but not configured in our setup. Proactive audio would prevent responses to noise/hesitation. Affective dialog would adapt tone to user emotion. Thinking would improve reasoning for complex queries. See `references/gemini-live-api-reference.md` for config examples.