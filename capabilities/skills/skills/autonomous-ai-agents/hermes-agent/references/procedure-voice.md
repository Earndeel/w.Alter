## Voice & Transcription

### STT (Voice → Text)

Voice messages from messaging platforms are auto-transcribed.

Provider priority (auto-detected):
1. **Local faster-whisper** — free, no API key: `pip install faster-whisper`
2. **Groq Whisper** — free tier: set `GROQ_API_KEY`
3. **OpenAI Whisper** — paid: set `VOICE_TOOLS_OPENAI_KEY`

Config:
```yaml
stt:
  enabled: true
  provider: groq         # local, groq, openai, gemini
  local:
    model: base          # tiny, base, small, medium, large-v3
  groq:
    model: whisper-large-v3-turbo
  gemini:
    model: gemini-3.1-flash-lite
```

**Recommended STT strategy (tested):**

| Priority | Provider | Model | Speed | Quality |
|----------|----------|-------|-------|---------|
| Primary | Groq | whisper-large-v3-turbo | ~0.9s | Clean, no rich punctuation |
| Fallback | Gemini | gemini-3.1-flash-lite | ~3s | Full punctuation, filler words, tone |

- Groq Whisper: fast, clean output but strips hesitations and rich punctuation
- Gemini 3.1 Flash Lite: slower but more faithful to oral speech (ponctuation, "euh", "tu vois", ton)
- Both are free. Use Groq for real-time, Gemini for archival fidelity.
- Fallback logic: if Groq returns empty/error/timeout → Gemini automatically.

### TTS (Text → Voice)

| Provider | Env var | Free? | Notes |
|----------|---------|-------|-------|
| Gemini TTS | `GEMINI_API_KEY` | Yes | `gemini-3.1-flash-tts-preview`, voice `Algenib` — deep butler voice, monotone, sarcastic. Best fit for W.Alter persona. Config: `tts.provider: gemini` + `tts.gemini.voice: Algenib` + `tts.gemini.system_prompt` for style control. |
| Edge TTS | None | Yes | Good free option. Change voice: `tts.edge.voice` in config.yaml. Available voices: run `edge-tts --list-voices`. |
| ElevenLabs | `ELEVENLABS_API_KEY` | Free tier | High quality, $206/1M chars. Expensive. |
| OpenAI | `VOICE_TOOLS_OPENAI_KEY` | Paid | gpt-4o-mini-tts model |
| Kokoro (local) | None | Free | Local 82M param model, install needed |
| Fish Audio | `FISH_AUDIO_API_KEY` | Free tier | |

**Sending voice on Telegram bot API:** Use `POST https://api.telegram.org/bot<TOKEN>/sendVoice` with multipart/form-data. Fields: `chat_id`, `voice` (OGG file), `caption` (optional text).

**Gemini Live API alternative:** Gemini 3.1 Flash Live and Gemini 2.5 Flash Live provide native bidirectional audio streaming (STT + LLM + TTS in one model) via WebSocket. Pricing: $0.10/1M input tokens, $0.40/1M output tokens — extremely cheap (~$0.003/conversation). SDK: `google-genai`. Replaces the entire STT(Groq)+LLM(OpenRouter)+TTS(Edge) pipeline with a single real-time voice call. Model names: `gemini-3.1-flash-live`, `gemini-2.5-flash-live`.

**Gemini TTS config example (Algenib butler voice):**
```yaml
tts:
  provider: gemini
  gemini:
    model: gemini-3.1-flash-tts-preview
    voice: Algenib
    system_prompt: 'Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice, calm and collected, very precise diction, slightly sarcastic undertone, elegant and formal butler tone, smooth and authoritative.'
```

Voice commands: `/voice on` (voice-to-voice), `/voice tts` (always voice), `/voice off`.

---

