# Gemini Live API Reference (2026-05-19)

Source: https://ai.google.dev/gemini-api/docs/live-api

## Technical Specs
| Category | Details |
|----------|---------|
| Input audio | Raw 16-bit PCM, 16kHz, little-endian |
| Output audio | Raw 16-bit PCM, 24kHz, little-endian |
| Input images | JPEG, ≤1 FPS |
| Protocol | WebSocket WSS (stateful) |
| Languages | 70 supported |

## Key Features
- **Proactive Audio** — model decides when to speak (configurable via `proactiveAudio` in setup)
- **Affective Dialog** — adapts tone to user emotion
- **Barge-in** — user can interrupt model at any time
- **Audio Transcription** — real-time input/output transcription
- **Thinking** — configurable thinking budget (`thinkingConfig`)
- **Function Calling** — tools during audio session
- **Google Search** — real-time search during audio
- **Code Execution** — Python execution during audio

## Setup Configuration (BidiGenerateContentSetup)
```json
{
  "model": "models/gemini-3.1-flash-live-preview",
  "generationConfig": {
    "responseModalities": ["AUDIO"],
    "speechConfig": {
      "voiceConfig": {
        "prebuiltVoiceConfig": { "voiceName": "Algenib" }
      }
    },
    "temperature": 0.2,
    "thinkingConfig": { "thinkingBudget": 1024 }
  },
  "systemInstruction": {
    "parts": [{ "text": "..." }]
  },
  "tools": [...],
  "config": {
    "proactiveAudio": true,
    "inputAudioTranscription": {},
    "outputAudioTranscription": {}
  }
}
```

## Ephemeral Tokens
For production, use ephemeral tokens instead of API keys:
```
POST /v1alpha/auth_tokens
→ { "token": "auth_tokens/xxx", "expires_at": "..." }
```

## Implementation Approaches
- **Server-to-server** — backend connects via WebSocket (our current approach)
- **Client-to-server** — frontend connects directly (better latency, needs ephemeral tokens)

## Partner Integrations
- LiveKit Agents
- Pipecat by Daily
- Fishjam by Software Mansion
- Vision Agents by Stream
- Voximplant
- Agora
- Firebase AI SDK

## Related Pages
- Capabilities: https://ai.google.dev/gemini-api/docs/live-api/capabilities
- Tools: https://ai.google.dev/gemini-api/docs/live-api/tools
- Session Management: https://ai.google.dev/gemini-api/docs/live-api/session-management
- Best Practices: https://ai.google.dev/gemini-api/docs/live-api/best-practices
- Ephemeral Tokens: https://ai.google.dev/gemini-api/docs/live-api/ephemeral-tokens
