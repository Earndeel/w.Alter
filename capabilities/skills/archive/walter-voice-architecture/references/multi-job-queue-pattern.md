# Multi-Job Queue Pattern for Voice Calls

## Problem

When Lucas asks multiple things simultaneously ("check my emails AND delete the Microsoft one AND check vast.ai"), all three go to hermes_async as separate jobs. Results come back in random order. Without tracking, Gemini Live can't tell which result belongs to which question.

## Architecture

### Browser-side (app.js)

```
activeJobs (Map)           — job_id → { question, startedAt }
jobResultQueue (Array)     — FIFO queue of { jobId, prompt, queuedAt }
state.messageQueue (Array) — transient updates with job context
currentDrainJobId          — currently-spooken job result ID
```

### Server-side (voice_router_service.py)

```
push_transient_update(job_id, message) — POST to /internal/transient-update
run_job() — streams stdout line by line, pushes significant lines as transient updates
```

### Server-side (voice-call server.py)

```
/internal/transient-update — broadcasts { type: "transient_update", job_id, message } via WebSocket
/internal/job-complete     — broadcasts full job result via WebSocket
```

## Lifecycle

1. **Job starts:** Gemini Live calls voice_router → `shouldConfirmToolResult()` detects job_id → `enqueueJobStart(jobId, question)`
2. **Transient updates:** Hermes streams stdout → voice_router pushes significant lines → browser receives via WebSocket → `enqueueTransientUpdate(jobId, message)` with original question context
3. **Job completes:** voice_router pushes full result → browser receives → `enqueueJobResult(jobId, prompt)`
4. **Drain:** When Gemini finishes speaking (`markGeminiDone()`), `drainQueue()` sends next result via `sendTextMessage()`

## Queue Priority

1. **Job results first** (FIFO order — first asked, first answered)
2. **Transient updates second** (batched, max 3 per message)

## Key Implementation Details

### enqueueJobStart
```javascript
function enqueueJobStart(jobId, question) {
  activeJobs.set(jobId, { question, startedAt: Date.now() });
}
```
Called in `shouldConfirmToolResult()` when voice_router returns `status: "started"` with a `job_id`.

### enqueueTransientUpdate
```javascript
function enqueueTransientUpdate(jobId, message) {
  const jobInfo = activeJobs.get(jobId);
  const context = jobInfo ? `Concernant "${jobInfo.question}": ` : "";
  state.messageQueue.push({ type: "transient", text: `${context}${message}`, jobId, queuedAt: Date.now() });
  if (!state.isGeminiSpeaking) drainQueue();
}
```

### enqueueJobResult
```javascript
function enqueueJobResult(jobId, prompt) {
  jobResultQueue.push({ jobId, prompt, queuedAt: Date.now() });
  activeJobs.delete(jobId);
  if (!state.isGeminiSpeaking) drainQueue();
}
```

### drainQueue
```javascript
function drainQueue() {
  if (state.isGeminiSpeaking) return;
  // Priority: job results (FIFO) > transient updates (batched)
  if (jobResultQueue.length > 0) {
    const result = jobResultQueue.shift();
    state.isGeminiSpeaking = true;
    state.client.sendTextMessage(result.prompt);
    // 15s safety timeout
    return;
  }
  if (state.messageQueue.length > 0) {
    const batch = state.messageQueue.splice(0, 3);
    // batch and send
  }
}
```

### Speaking state hooks
- `markGeminiSpeaking()` — called on `AUDIO` response
- `markGeminiDone()` — called on `TURN_COMPLETE` or `INTERRUPTED`, triggers drainQueue after 800ms

## Pitfalls

- **Without per-job tracking**, results arrive in random order and Gemini Live mixes up subjects
- **Without the queue**, job results interrupt Gemini mid-sentence
- **Without question context**, Gemini Live says "le résultat est prêt" but doesn't know what it's about
- **The 15s safety timeout** is critical — if `turn_complete` never fires (e.g., Gemini gets stuck), the queue would deadlock without it
- **Transient updates should include the original question** so Gemini Live can say "Concernant vos mails: j'ai trouvé 15 résultats" instead of just "j'ai trouvé 15 résultats"
