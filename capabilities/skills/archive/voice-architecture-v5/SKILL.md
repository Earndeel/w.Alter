---
name: voice-architecture-v5
description: W.Alter Voice Call v5 architecture — Gemini Live STS, voice_router, multi-job queue, transient updates.
tags: [voice, gemini-live, sts, audio, walter]
---

# W.Alter Voice Architecture v5

## Overview
Browser → Gemini Live (STS) → voice_router → Hermes (deep brain). Client-to-server via ephemeral tokens.

## Components
- **Voice Call Server**: FastAPI on port 8765 TLS. Serves static UI, creates ephemeral tokens, broadcasts WebSocket updates.
- **Voice Router**: FastAPI on port 12110. Routes intents, manages async jobs, streams transient updates.
- **Browser (app.js)**: Gemini Live client, multi-job queue with FIFO delivery, transient update queue.

## Gemini Live STS Config
- Model: `gemini-3.1-flash-live-preview`
- Endpoint: `BidiGenerateContentConstrained` (NOT `BidiGenerateContent`)
- Temperature: 0.2
- Thinking: `thinkingLevel: "high"` (fastest: 6.1s vs 8s without thinking)
- Voice: Algenib
- Config: `thinkingConfig.thinkingLevel` (string "low"/"high"), NOT `thinkingBudget` (int)
- Transcription fields at `setup` level, not inside `generationConfig`

## Multi-job Queue (app.js)
- `activeJobs` Map: tracks job_id → {question, startedAt}
- `jobResultQueue` Array: FIFO queue of completed results
- `enqueueJobStart(jobId, question)`: called when voice_router returns job_id
- `enqueueJobResult(jobId, prompt)`: called when job completes
- `enqueueTransientUpdate(jobId, message)`: intermediate updates with context
- `drainQueue()`: sends next message when Gemini finishes speaking (TURN_COMPLETE)
- Priority: job results first (FIFO), then transient updates
- `markGeminiSpeaking()`: on AUDIO response — blocks drain
- `markGeminiDone()`: on TURN_COMPLETE/INTERRUPTED — unblocks drain

## Conversation Buffer (voice_router)
- `ConversationBuffer` class: stores last 10 turns per call_id
- Injected into Hermes async job prompts as "Contexte de la conversation vocale"
- Prevents context loss when escalating from voice to deep brain

## Transient Updates (voice_router → browser)
- `run_job()` streams Hermes stdout line by line
- Significant lines (🔧, ✓, ✗, Running, Done, Error) pushed via `/internal/transient-update`
- Browser queues them with job context for delivery after Gemini finishes speaking

## System Prompt Layers
1. AUDIO_STYLE: voice director (tone, pacing, accent)
2. COMMUNICATION_STYLE: butler rules (vouvoiement, Monsieur, direct)
3. SYSTEM_PROMPT: behavior (routing, tool use, limits)

## Key Files
- `/root/.hermes/voice-call/static/app.js` — browser client
- `/root/.hermes/voice-call/static/geminilive.js` — Gemini Live WebSocket client
- `/root/.hermes/voice-call/server.py` — FastAPI server
- `/root/.hermes/services/voice_router_service.py` — intent router + job runner

## Pitfalls
- Live model ONLY via WebSocket, NOT REST API
- Ephemeral tokens required (POST /api/token)
- Gemini spending cap blocks all WebSocket connections (code 1011)
- "off" thinking level may not be valid in Live API
- `config` field (transcription) must be at `setup` level, not nested in `generationConfig`
