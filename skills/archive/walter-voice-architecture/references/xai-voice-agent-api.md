# xAI Voice Agent API — Real-time Speech-to-Speech

Source: https://docs.x.ai/developers/model-capabilities/audio/voice (fetched 2026-05-17)

## Overview

xAI's Voice Agent API provides real-time bidirectional audio streaming over WebSocket — the direct equivalent of Gemini Live and OpenAI's Realtime API. Endpoint: `wss://api.x.ai/v1/realtime?model=grok-voice-latest`

## API Components

### Voice Agent API (Real-time S2S)
- **Endpoint:** `wss://api.x.ai/v1/realtime`
- **Model:** `grok-voice-latest`
- **Protocol:** WebSocket with JSON events
- **Latency:** Sub-second
- **Pricing:** $3.00/hour
- **Tools in voice:** web_search, X Search, function_calling, code_execution
- **Turn detection:** Server-side VAD
- **Demo apps:** Web, Twilio Phone, WebRTC, iOS — all in `xai-org/xai-cookbook` on GitHub

### TTS (Text-to-Speech)
- **Endpoint:** `POST https://api.x.ai/v1/tts`
- **Pricing:** $15.00/1M characters
- **5 voices:** eve (energetic female), ara (warm female), rex (confident male), sal (neutral), leo (authoritative male)
- **Features:** Inline speech tags (laughter, whispers, pauses), telephony μ-law codec, WebSocket streaming mode
- **Custom voices:** Clone from audio clip (max 120s) via `POST /v1/custom-voices` → get `voice_id` → use in TTS/Agent

### STT (Speech-to-Text)
- **Endpoint:** `POST https://api.x.ai/v1/stt`
- **Pricing:** $0.20/hour
- **25 languages**, 12 audio formats, word-level timestamps, multichannel, speaker diarization
- **Modes:** Batch (single call) and streaming (WebSocket)

### Custom Voices
- Create: `POST /v1/custom-voices` with reference audio (max 120s)
- Returns `voice_id` usable in TTS, streaming TTS WebSocket, and Voice Agent realtime API
- Same pricing as built-in voices

## Integration Examples (from docs)

### Python Voice Agent
```python
import asyncio, json, os, websockets

async def voice_agent():
    async with websockets.connect(
        "wss://api.x.ai/v1/realtime?model=grok-voice-latest",
        additional_headers={"Authorization": f"Bearer {os.environ['XAI_API_KEY']}"}
    ) as ws:
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "voice": "eve",
                "instructions": "You are a helpful customer support agent.",
                "turn_detection": {"type": "server_vad"},
                "tools": [{"type": "web_search"}]
            }
        }))
        async for message in ws:
            event = json.loads(message)
            if event["type"] == "response.output_audio.delta":
                pass  # Play audio: base64.b64decode(event["delta"])

asyncio.run(voice_agent())
```

### Integration frameworks
- **LiveKit:** https://docs.livekit.io/agents/integrations/xai/
- **Pipecat:** https://docs.pipecat.ai/server/services/s2s/grok

## Comparison: xAI Voice Agent vs Gemini Live vs OpenAI Realtime

| Feature | xAI Voice Agent | Gemini 3.1 Flash Live | OpenAI Realtime |
|---|---|---|---|
| Pricing | $3.00/hr | ~$0.003/conversation | $0.06/min ($3.60/hr) |
| Latency | Sub-second | Sub-second | Sub-second |
| Tools in voice | web_search, X Search, code_exec, functions | functions only | functions, web_search |
| Custom voices | ✅ Clone from clip | ❌ | ❌ |
| Built-in voices | 5 | ~30 | 6+ |
| X Search in voice | ✅ Unique | ❌ | ❌ |
| Hermes STT support | ✅ (tts/STT providers) | ✅ (as STT provider) | ❌ |
| Hermes realtime voice | ❌ Not yet | ❌ Not yet | ❌ Not yet |

## For Hermes/W.Alter Integration

Hermes currently supports xAI for:
- **TTS:** `tts.provider: xai` with `voice_id`, `language`, `sample_rate`, `bit_rate` config
- **STT:** `stt.provider: xai` as Whisper alternative
- **LLM:** `provider: xai` for Grok models (grok-4.3, etc.)

Hermes does NOT yet have a realtime voice agent client for xAI (or Gemini Live). The Walter 3-tier architecture (Gemini Live for calls) could be extended to support xAI Voice Agent as an alternative backend, gaining X Search in the voice loop.

## Key Distinction: "Grok Voice Think Fast"

"Grok Voice Think Fast" is the consumer-facing name in the Grok app (x.com/grok) for the real-time voice mode. The API equivalent is the Voice Agent API. It's not a separate model — it's the same `grok-voice-latest` accessed via WebSocket.

## Pitfalls

- The $3/hr pricing makes it ~1000x more expensive than Gemini Live for short interactions. Use Gemini Live for quick voice exchanges, xAI Voice Agent when X Search or custom voices are needed.
- Custom voice cloning requires a reference audio clip — can't be done programmatically without audio input.
- The Voice Agent API requires `XAI_API_KEY` — with Premium+ this comes via SuperGrok access.
