# Gemini Live API — Technical Reference

Source: https://ai.google.dev/gemini-api/docs/live-api (fetched 2026-05-19)

## Model
`gemini-3.1-flash-live-preview`

## Audio Specs

| Category | Detail |
|---|---|
| Input audio | Raw 16-bit PCM, 16kHz, little-endian |
| Output audio | Raw 16-bit PCM, 24kHz, little-endian |
| Input images | JPEG, ≤1 FPS |
| Input text | UTF-8 |
| Protocol | WebSocket WSS (stateful) |
| Languages | 70 supported |

## Key Features

### Proactive Audio
Model decides WHEN to speak and in what context. Configurable via `proactiveAudio` in setup config. Prevents responses to background noise, hesitations, etc.

```json
{
  "config": {
    "proactiveAudio": true
  }
}
```

### Affective Dialog
Model adapts response style/tone to match user's emotional expression. Detects emotion in voice and adjusts.

### Barge-in (Interruptions)
User can interrupt model at any time. Model stops and listens. Handled automatically by SDK — browser receives `INTERRUPTED` response type.

### Audio Transcription
Real-time transcription of both user input and model output:

```json
{
  "config": {
    "inputAudioTranscription": {},
    "outputAudioTranscription": {}
  }
}
```

### Thinking (Reasoning)
Model can "think" before responding. Configurable via `thinkingConfig`:

```json
{
  "generationConfig": {
    "thinkingConfig": {
      "thinkingBudget": 1024,
      "includeThoughts": true
    }
  }
}
```

- `thinkingBudget`: max tokens for reasoning (0 = disabled)
- `includeThoughts`: include thoughts in response (for debugging)

### Session Resumption
Sessions can be resumed after disconnection. Server maintains session state.

## Tools in Live Session

### Function Calling
Defined in setup config, called during session:

```json
{
  "setup": {
    "tools": [
      {
        "functionDeclarations": [
          {
            "name": "voice_router",
            "description": "Route la requête vers le cerveau profond",
            "parameters": {
              "type": "OBJECT",
              "properties": {
                "user_utterance": {"type": "STRING"},
                "intent": {"type": "STRING"}
              },
              "required": ["user_utterance"]
            }
          }
        ]
      }
    ]
  }
}
```

### Google Search
Model can search Google in real-time during audio session.

### Code Execution
Model can execute Python code during session.

## Ephemeral Tokens (Production)

For production, NEVER expose API key client-side. Use ephemeral tokens:

```
POST /v1alpha/auth_tokens
→ { "token": "auth_tokens/xxx", "expires_at": "..." }
```

Token used by client to connect to WebSocket. Expires after short delay.

## Full Setup Config Example

```json
{
  "model": "models/gemini-3.1-flash-live-preview",
  "generationConfig": {
    "responseModalities": ["AUDIO"],
    "speechConfig": {
      "voiceConfig": {
        "prebuiltVoiceConfig": {
          "voiceName": "Algenib"
        }
      }
    },
    "temperature": 0.7,
    "thinkingConfig": {
      "thinkingBudget": 1024
    }
  },
  "systemInstruction": {
    "parts": [{"text": "Tu es W.Alter..."}]
  },
  "tools": [...],
  "config": {
    "proactiveAudio": true,
    "inputAudioTranscription": {},
    "outputAudioTranscription": {}
  }
}
```

## Best Practices (from Google)

1. Use ephemeral tokens for production (not API key client-side)
2. Handle interruptions — model stops when user speaks
3. Use proactive audio to avoid unwanted responses
4. Stream audio in chunks — don't send all at once
5. Handle reconnections — WebSocket can close, auto-reconnect
6. Monitor token usage — Live sessions consume tokens continuously

## Partner Integrations

- **LiveKit Agents** — Gemini Live with LiveKit
- **Pipecat by Daily** — real-time AI chatbot
- **Fishjam** — live video/audio streaming
- **Vision Agents by Stream** — real-time voice+video
- **Voximplant** — inbound/outbound calls
- **Agora** — real-time conversational AI
- **Firebase AI SDK** — Gemini Live via Firebase

## Features We Should Consider Enabling

| Feature | Status | Benefit |
|---|---|---|
| Proactive Audio | NOT enabled | Prevents responses to noise/hesitation |
| Affective Dialog | NOT enabled | Adapts tone to user emotion |
| Thinking Config | NOT enabled | Better reasoning for complex queries |
| Google Search | NOT enabled | Real-time search during voice |
| Code Execution | NOT enabled | Run code during voice session |
| Session Resumption | NOT implemented | Avoid re-creating sessions |
