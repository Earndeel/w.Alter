# Gemini Live — Tool Calls, Greeting & Async Job Push

## Architecture (Browser → Gemini Live)

```
Browser mic/audio worklets → Gemini Live WebSocket (direct, ephemeral token)
                            ↕ function calls
FastAPI server (port 8765)  → voice_router (port 12110) → Hindsight / Hermes async / Brave
       ↕ WebSocket /ws/jobs (push)
Browser ← instant job result push
```

Key files:
- `/root/.hermes/voice-call/static/app.js` — client logic, system prompt, tool handlers
- `/root/.hermes/voice-call/static/tools.js` — tool definitions (VoiceRouterTool, etc.)
- `/root/.hermes/voice-call/static/geminilive.js` — GeminiLiveAPI WebSocket wrapper
- `/root/.hermes/voice-call/server.py` — FastAPI: static assets, token provisioning, voice-router proxy, call logging, proactive polling, WebSocket push
- `/root/.hermes/services/voice_router_service.py` — backend routing (direct_answer, context_lookup, quick_web, hermes_async, notify)

## Greeting on Connection

Gemini Live does NOT speak automatically on setup. To trigger a greeting:

1. In `app.js`, listen for `SETUP_COMPLETE` in `handleResponse`
2. After ~800ms delay, send: `state.client.sendTextMessage("Dis exactement: Oui Monsieur ?")`
3. The system prompt persona handles the rest

```js
case MultimodalLiveResponseType.SETUP_COMPLETE:
  // ... UI updates ...
  setTimeout(() => {
    if (state.client?.connected && state.callWanted) {
      state.client.sendTextMessage("Dis exactement: Oui Monsieur ?");
    }
  }, 800);
  break;
```

**Pitfall:** Without the delay, the text message may arrive before Gemini is fully ready.

## Tool Call Result Vocalization

When `voice_router` returns a `spoken_response`, the client forces Gemini Live to speak it via `confirmationPrompts`. For sync results (no job_id), this happens immediately. For async results, see the WebSocket push section below.

### Client-side force-speak (app.js — handleToolCall)

After getting tool result, extract `spoken_response` and push to `confirmationPrompts`:
```js
// Force-speak voice_router spoken_response if Gemini might not verbalize it
if (call.name === "voice_router" && result?.spoken_response && !result?.job_id) {
  const spoken = result.spoken_response;
  confirmationPrompts.push(spoken);
}
```

## Async Job Push via WebSocket (2026-05-18)

**Problem:** The old polling approach (browser checks `/jobs/{id}` every 15s) introduced unnecessary latency and Telegram notifications that the user didn't want.

**Solution:** WebSocket push — when Hermes finishes, the result is pushed instantly to the browser which injects it into Gemini Live.

### Flow

```
User speaks → Gemini Live → TOOL_CALL (voice_router)
  → Browser JS: fetch /api/voice-router → voice_router_service.py
  → Returns: { spoken_response, route, job_id?, ... }
  → sendToolResponse(result) back to Gemini Live
  → scheduleToolCompletionConfirmation() nudges Gemini to speak

[Async job runs in background]
  → voice_router_service.py: run_job() executes hermes chat
  → When done: POST /internal/job-complete → server.py
  → server.py: broadcasts to all WebSocket clients
  → app.js: handleJobPush() → sendTextMessage() → Gemini Live speaks
```

### Server-side (server.py)

```python
# WebSocket endpoint for browser clients
@app.websocket("/ws/jobs")
async def ws_jobs(websocket: WebSocket):
    await websocket.accept()
    app.state.ws_clients.add(websocket)
    # ... keep alive, cleanup on disconnect

# Internal endpoint called by voice_router when job completes
@app.post("/internal/job-complete")
async def job_complete(payload: dict = Body(default_factory=dict)):
    # Broadcasts to all connected WebSocket clients
    for ws in list(app.state.ws_clients):
        await ws.send_json(payload)
```

### voice_router_service.py

```python
async def push_job_result(job_data: dict[str, Any]) -> bool:
    """Push job result to voice-call server via WebSocket broadcast."""
    url = os.getenv("VOICE_CALL_INTERNAL_URL", "https://127.0.0.1:8765/internal/job-complete")
    async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
        resp = await client.post(url, json=job_data)
        return resp.status_code == 200
```
# In run_job(): replaces notify_telegram()
await push_job_result(sanitize_payload(job))
```

### Client-side (app.js)

```js
function connectJobWebSocket() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws/jobs`);
  ws.onmessage = (evt) => handleJobPush(JSON.parse(evt.data));
  ws.onclose = () => { /* reconnect if call active */ };
  state.jobWs = ws;
}

function handleJobPush(job) {
  if (!job.spoken_summary || !state.client?.connected) return;
  const label = job.status === "failed" ? "Le job a échoué. " : "";
  state.client.sendTextMessage(
    `Résultat du job async. Reformule en une phrase... ${label}${job.spoken_summary}`
  );
}
```

**Pitfall:** The WS connects when `connectClient()` is called (Gemini Live session start) and disconnects on `cleanupConnection()`. No polling timer needed.

**Pitfall (HTTPS):** `server.py` runs on HTTPS (TLS). Internal calls from `voice_router_service.py` must use `https://127.0.0.1:8765/internal/job-complete` with `httpx.AsyncClient(verify=False)`. Using `http://` silently fails — no error in voice-router logs, no request in voice-call logs.

## Conversation Buffer (2026-05-19)

**Problem:** When Gemini Live escalates to Hermes async, the voice_router only received the last utterance ("Mener une analyse approfondie") without the conversation context (the Microsoft 3D model question). Hermes had no idea what to analyze.

**Solution:** `ConversationBuffer` class in `voice_router_service.py` tracks the last 10 messages per `call_id`.

### Flow
```
User: "Tu as entendu parler du nouveau modèle 3D de Microsoft ?"
  → voice_router stores (call_id, "user", utterance) in buffer
  → Gemini responds via context_lookup

User: "Mener une analyse approfondie."
  → voice_router stores (call_id, "user", utterance) in buffer
  → Intent: hermes_async → build_deep_prompt() includes buffer context
  → Hermes receives:
      "Contexte de la conversation vocale en cours:
       Monsieur: Tu as entendu parler du nouveau modèle 3D de Microsoft ?
       W.Alter: [recall mémoire response]
       Monsieur: Mener une analyse approfondie."
  → Hermes knows WHAT to analyze
```

### Implementation
- `ConversationBuffer` class: `collections.deque(maxlen=10)` per call_id
- `add(call_id, role, content)` — stores user + assistant messages
- `get_context(call_id)` — returns formatted context string
- `route()` tracks user utterances automatically
- `route_endpoint()` tracks assistant responses after route returns
- `build_deep_prompt()` injects buffer as "Contexte de la conversation vocale en cours"
- `RouteRequest` model has `call_id` and `assistant_response` fields
- `app.js` `normalizeToolCallArgs()` passes `state.callId` to voice_router

**Pitfall:** The `call_id` must be passed from the browser to voice_router. If `normalizeToolCallArgs` doesn't inject it, the buffer is empty and Hermes gets no context. Verify `state.callId` is set in app.js.

## Transient Messages + Message Queue (2026-05-19)

**Problem:** During multi-step Hermes jobs (web research, service builds), the user heard nothing until the job completed. Also, if Gemini Live was speaking and a job result arrived, it would interrupt the current speech.

**Solution:** Two-part system — transient message streaming from voice_router + browser-side message queue.

### Part 1: Transient Message Streaming (voice_router)

`run_job()` now reads Hermes stdout **line by line** instead of waiting for completion:

```python
# Stream stdout line by line
collected_lines = []
async def read_stream(stream, collector):
    async for line in stream:
        text = line.decode(errors="ignore").rstrip()
        if text:
            collector.append(text)

stdout_task = asyncio.create_task(read_stream(proc.stdout, collected_lines))
stderr_task = asyncio.create_task(read_stream(proc.stderr, stderr_lines))
await asyncio.wait_for(asyncio.gather(stdout_task, stderr_task), timeout=DEFAULT_JOB_TIMEOUT)
```

Significant lines (containing 🔧, ✓, ✗, Running, Created, Done, Error, Failed, completed, started) are pushed via `push_transient_update()` to `server.py` at `/internal/transient-update`.

### Part 2: Browser Message Queue (app.js)

Messages are queued while Gemini Live is speaking and delivered after it finishes:

```js
// State additions
state.messageQueue = [];
state.isGeminiSpeaking = false;
state.queueDrainTimer = null;

// Queue management
function enqueueMessage(text, priority) { /* add to queue, try drain */ }
function drainQueue() { /* batch up to 3, sendTextMessage to Gemini */ }
function markGeminiSpeaking() { /* called on AUDIO response */ }
function markGeminiDone() { /* called on TURN_COMPLETE, INTERRUPTED */ }
```

### WebSocket message routing
```js
ws.onmessage = (evt) => {
  const data = JSON.parse(evt.data);
  if (data.type === "transient_update") {
    enqueueMessage(data.message, "normal");  // Queue it
  } else {
    handleJobPush(data);  // Job result → also queued now
  }
};
```

### Queue drain behavior
- Drains when Gemini finishes speaking (TURN_COMPLETE or INTERRUPTED)
- Batches up to 3 messages into one `sendTextMessage` call
- 800ms delay after Gemini finishes before draining (avoids rapid-fire)
- 10s safety timeout resets `isGeminiSpeaking` if TURN_COMPLETE doesn't fire
- Job results are queued with "high" priority

**Pitfall:** The transient update markers in stdout must match actual Hermes output patterns. If Hermes changes its output format, the markers need updating. The current markers are: 🔧, ✓, ✗, Running, Created, Done, Error, Failed, completed, started.

**Pitfall:** The `/internal/transient-update` endpoint must use HTTPS + `verify=False` (same as `/internal/job-complete`). The env var `VOICE_CALL_TRANSIENT_URL` defaults to `https://127.0.0.1:8765/internal/transient-update`.

## voice_router Routes

| Route | Behavior | Audio result path |
|-------|----------|-------------------|
| `direct_answer_flash_lite` | Gemini Flash Lite answers directly | `spoken_response` → tool response → Gemini speaks |
| `context_lookup` | Hindsight memory search + synthesis | `spoken_response` → tool response → Gemini speaks |
| `quick_web_brave` | Brave search + synthesis | `spoken_response` → tool response → Gemini speaks |
| `hermes_async` | Starts detached Hermes job | Initial ack spoken → WS push when done → Gemini speaks |
| `deep_web_async` | Starts deep research job | Same as hermes_async |
| `notify` | Sends to Telegram | `spoken_response` confirms send |
| `store_memory` | Writes to Hindsight | `spoken_response` confirms |
| `task_status` | Checks job status | `spoken_response` with status |

## Cache Busting

`index.html` loads `app.js` with a version query param. Update it when changing JS:
```html
<script src="/static/app.js?v=YYYYMMDD_feature" defer></script>
```

Browser needs hard refresh (Cmd+Shift+R) to pick up new static files.
