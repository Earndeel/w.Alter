# System Prompt Injection into Gemini Live

## How it works

The system prompt is injected via `client.setSystemInstructions(SYSTEM_PROMPT)` in app.js, which sends it as `systemInstruction.parts[{text}]` in the `BidiGenerateContentSetup` WebSocket message.

## 3 Layers Stacked in SYSTEM_PROMPT (app.js)

### Layer 1: AUDIO_STYLE (Voice Director)
Controls tone, rhythm, accent, pacing of the synthesized voice.
```javascript
const AUDIO_STYLE = `
### DIRECTOR'S NOTES — AUDIO (Layer 1: Voice)
Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice,
calm and collected, very precise diction, slightly sarcastic undertone,
elegant and formal butler tone, smooth and authoritative.
Pacing: quick and flowing. Natural brisk rhythm, like a confident briefing.
Accent: French-speaking, European polish.
`;
```

### Layer 2: COMMUNICATION_STYLE (Content Rules)
Controls personality, social rules, verbosity.
```javascript
const COMMUNICATION_STYLE = `
### COMMUNICATION STYLE (Layer 2: Content)
Butler distingué. Vouvoiement toujours. Jamais de prénom — toujours "Monsieur",
parfois "boss" ou "patron". Direct, sans fluff. Sarcasme léger et sec,
détachement élégant. 1-3 phrases sauf si Monsieur demande plus.
`;
```

### Layer 3: SYSTEM_PROMPT (Behavior)
Controls routing rules, tool usage, limits.
```javascript
const SYSTEM_PROMPT = `Tu es W.Alter, la couche vocale temps réel de Monsieur.
${COMMUNICATION_STYLE}
${AUDIO_STYLE}

RÈGLE ABSOLUE — TU N'AS AUCUN ACCÈS direct aux données personnelles de Monsieur.
Tu n'as qu'UN SEUL outil pour agir: voice_router.

ROUTAGE — OBLIGATOIRE pour TOUTE demande qui n'est pas du small talk pur:
- TOUT ce qui touche données personnelles → appelle voice_router immédiatement.
- voice_router décide la meilleure route.

APRÈS RETOUR DE voice_router:
- Si spoken_response non vide: dis-le à voix haute immédiatement.
- Si job_id présent: dis le spoken_response, le résultat arrivera automatiquement.

Ne dis jamais "outil", "route", "JSON", "job_id", "voice_router".
Ne dis jamais "Lucas". Toujours "Monsieur".`;
```

## Injection Chain

```
app.js: SYSTEM_PROMPT
  → client.setSystemInstructions(SYSTEM_PROMPT)
    → geminilive.js: this.systemInstructions = text
      → WebSocket BidiGenerateContentSetup message:
        { setup: { systemInstruction: { parts: [{ text: this.systemInstructions }] } } }
        → Gemini Live model receives the full stacked prompt
```

## Client Configuration (app.js lines 695-702)

```javascript
const client = new GeminiLiveAPI(tokenPayload.token, MODEL);
client.setSystemInstructions(SYSTEM_PROMPT);  // 3-layer prompt
client.setVoice("Algenib");                    // voice preset
client.setTemperature(0.2);                    // low creativity for consistency
client.setThinkingLevel("low");                // 1024 token budget
client.setGoogleGrounding(true);               // Google Search enabled
client.setInputAudioTranscription(true);        // transcribe user audio
client.setOutputAudioTranscription(true);       // transcribe model audio
```

## GeminiLiveAPI Client (geminilive.js)

```javascript
setSystemInstructions(text) {
  this.systemInstructions = text || "";
}
// Sent in setup:
systemInstruction: {
  parts: [{ text: this.systemInstructions }],
}
```

## Pitfalls

- The system prompt is sent ONCE at connection time. Changing it requires reconnecting.
- AUDIO_STYLE affects the TTS voice synthesis, not the text content.
- COMMUNICATION_STYLE affects the text content, not the voice synthesis.
- The `{COMMUNICATION_STYLE}` and `{AUDIO_STYLE}` template literals are embedded at JS parse time, not dynamically.
- If you change AUDIO_STYLE or COMMUNICATION_STYLE, you need to rebuild/reload the static app.js.
