## Deployed Components

### Asterisk (on Oracle Cloud VM)
- SIP port 5060 (UDP), ARI port 8088 (HTTP), AMI port 5038
- Trunk `linphone-walter` registered to `sip.linphone.org`
- Config files: `/etc/asterisk/pjsip.conf`, `extensions.conf`, `ari.conf`, `manager.conf`, `http.conf`
- Extension 200 routes to `Stasis(hermes_bridge)`
- Extensions 999 (echo), 888 (playback) for audio testing
- Context `from-linphone-walter` routes all incoming calls to Hermes bridge
- **Three transports:**
  - `transport-tailscale` — bind `100.91.35.121:5060` (Tailscale, for direct iPhone-to-Asterisk via Tailscale)
  - `transport-public` — bind `10.0.0.24:5060` with `external_media_address=129.150.52.60` + `external_signaling_address=129.150.52.60` (for linphone.org trunk, routes through Oracle NAT)
  - `transport-localhost` — bind `127.0.0.1:5060` (local only)
- The linphone.org trunk (`linphone-walter`, `linphone-walter-registration`) must use `transport=transport-public`, NOT `transport-tailscale`. See Pitfalls below.
- `match=176.31.149.179` in `[linphone-walter-identify]` — NOT `match=sip:sip.linphone.org` (SIP URI prefix breaks getaddrinfo)

### Python Bridge
- File: `/opt/openclaw/hermes_voice_bridge.py`
- Connects to Asterisk ARI via WebSocket
- On StasisStart: answers call, creates ExternalMedia channel, creates mixing bridge
- Bidirectional RTP audio: ulaw 8kHz ↔ PCM for Gemini
- Gemini Live exposed tools are intentionally narrow: native `google_search` + one proxy function `voice_router`
- `voice_router` calls local root-side service `http://127.0.0.1:12110/route`; it is the only path to Hindsight/Hermes/jobs from live voice
- Proactive outbound calls via AMI Originate
- Health endpoint on port 12100
- Systemd service: `hermes-bridge.service`
- Environment vars: `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BEEPER_TOKEN`, `ASTERISK_HOST`, `ARI_USER`, `ARI_PASS`, `AMI_USER`, `AMI_PASS`, `VOICE_ROUTER_URL`
- Service runs as `ubuntu` user — cannot read `/root/.hermes/.env` or call `vault` CLI. All secrets must be explicit env vars in the systemd unit. Root-only capabilities belong in `voice-router.service`, not the bridge.

### Linphone (iPhone)
- SIP Address: `sip:w.alter.ai@sip.linphone.org`
- Password: stored in vault, NOT in plaintext configs
- Transport: UDP, port 5060
- To call Hermes: dial 200
- To test echo: dial 999
- Verify registration before sending Lucas to Linphone: `asterisk -rx 'pjsip show registrations'`. If `linphone-walter` is `Rejected`, force re-register: `asterisk -rx "pjsip send register linphone-walter-registration"`. If still rejected after 10s, check transport (must be `transport-public`) and route to linphone.org (must go via VPS enp0s6, not Tailscale exit node).
- iPhone does NOT need Tailscale — calls route through sip.linphone.org → Asterisk (public IP)
- If iPhone IS on Tailscale, can also dial directly to `100.91.35.121` (extension 200) using the `lucas-iphone` endpoint

### Browser-direct voice-call server (PRODUCTION)
- **Public URL**: `https://call.walter-ai.cloud` (Cloudflare Tunnel, valid HTTPS cert, no Tailscale needed)
- **Voice default trap**: `geminilive.js` constructor sets `this.voiceName = "Algenib"` but if a new GeminiLiveAPI is created, the constructor default runs BEFORE `app.js` calls `setVoice()`. If these disagree, the constructor wins for the initial session. Always keep `geminilive.js` constructor default in sync with `app.js` `VOICE` constant.
- **AudioWorklet cache-busting**: Browsers aggressively cache AudioWorklet modules loaded via `addModule()`. Always append `?v=${Date.now()}` to the URL in `addModule()` calls in `mediaUtils.js`. Also cache-bust `<script>` tags in `index.html` on any JS change. See `references/browser-audio-jitter-buffer.md`.
- **Playback jitter buffer**: The playback worklet (`playback.worklet.js`) must implement a ring buffer with pre-buffering (~200ms at 24kHz = 4800 samples) to smooth out irregular Gemini Live audio chunk arrival. Without it, jitter causes audible gaps/crackling. See `references/browser-audio-jitter-buffer.md` for the full implementation.
- **Capture buffer sizing**: `capture.worklet.js` bufferSize=1024 (64ms at 16kHz) is the sweet spot. 512 (32ms) = too many WebSocket messages (~31/s), 2048 (128ms) = noticeable input latency. 1024 = ~16 msg/s with imperceptible latency.
- **Tailscale URL**: `https://w-alter.tail32cf1c.ts.net:8765/` (requires Tailscale on client)
- Service: `hermes-voice-call.service`
- Files: `/root/.hermes/voice-call/server.py`, `/root/.hermes/voice-call/static/app.js`, `/root/.hermes/voice-call/static/tools.js`
- **This is the current production call path** — iPhone opens the URL in Safari, taps mic, talks to W.Alter (Gemini Live). Works anywhere with internet, no app install needed.
- Cloudflare Tunnel config: `~/.cloudflared/config.yml`, entry `call.walter-ai.cloud` → `https://localhost:8765` with `originRequest.noTLSVerify: true` (origin cert is for Tailscale domain, not localhost)
- DNS: CNAME `call` → `<tunnel-id>.cfargotunnel.com` (proxied) in `walter-ai.cloud` zone
- The app exposes a same-origin `POST /api/voice-router` proxy to root-side `voice-router.service`, and client-side `VoiceRouterTool` exposes `voice_router` to Gemini Live.
- Voice-router call audit: latest tool call at `/root/.hermes/logs/voice-router/latest.json`; rolling JSONL history at `/root/.hermes/logs/voice-router/calls.jsonl`.
- Full browser-direct conversation persistence is enabled: client posts `call_start`, final input/output transcriptions, tool calls/responses, errors, interruptions, and `call_end` to `/api/calls/*`. Logs live under `/root/.hermes/logs/voice-call/conversations/<call_id>/` with `events.jsonl`, `transcript.md`, and `summary.json`.
- On `call_end`, the server asynchronously sends final user/assistant transcript turns to `write-worker.service` (`http://127.0.0.1:8890/process`) for durable fact extraction into Qdrant/Hindsight; debug/tool noise stays in logs and is not fed to memory extraction.
- Browser app now has deterministic post-tool completion confirmation: after side-effect tool results (`voice_router` notify/store_memory/async job, subscription create/delete), `app.js` waits briefly; if Gemini Live has not resumed speaking, it injects a short text nudge so the same Live voice tells Lucas the action completed. This fixes silent Telegram-send success during testing.
- Log/system-check utterances must route to `hermes_async`, not `task_status`; `voice_router_service.py` contains a guard for `LOG_CUES` to fix Live misroutes.
- Details and verification commands: `references/browser-direct-test-app.md`.

### Voice Router / Outer Router Service
- File: `/root/.hermes/services/voice_router_service.py`
- Service: `voice-router.service` (root)
- Port: `127.0.0.1:12110`
- Logs/jobs: `/root/.hermes/logs/voice-router/`
- Health: `curl http://127.0.0.1:12110/health`
- Version after multi-channel upgrade: `voice-router-v1.1-multilayer`
- API:
  - `POST /route` with `intent=route_request|context_lookup|quick_web|deep_web|hermes_async|task_status|store_memory|notify`
  - `GET /jobs/<job_id>`
- `route_request` is now the shared fast decision layer for voice/browser/Telegram. It calls Gemini `gemini-3.1-flash-lite-preview` to choose one route: `direct_answer`, `context_lookup`, `quick_web`, `deep_web`, `hermes_async`, `task_status`, or `store_memory`.
- Direct/simple answers are produced by Gemini Flash Lite in `spoken_response` (`route=direct_answer_flash_lite`) and do **not** spin up the full Hermes AIAgent.
- Context lookup: calls Hindsight hybrid search `http://127.0.0.1:8889/recall` with `bank_id=walter`, `budget=low`, `compile_context=true`, then returns `spoken_response`, `decision`, `next_action`, and `full_report` separately.
- Deep/long tasks: starts detached Hermes CLI job (`hermes chat -Q -q ... --source voice-router`) and immediately returns `job_id`; the job stores raw output + synthesized `spoken_summary` and notifies Telegram when done.
- Quick web: Brave Search if `BRAVE_SEARCH_API_KEY` is available; otherwise returns a short instruction/fallback to live grounding or Hermes deep research.
- Safety: service redacts secret-like strings in reports/logs and keeps dangerous tools behind backend policy. Gemini Live / Telegram outer routing never sees terminal/files/vault/deploy tools directly.

### Telegram multi-layer fast path
- Gateway module: `/root/.hermes/hermes-agent/gateway/outer_router.py`
- Gateway patch point: `gateway/run.py` after inbound text preparation and before `_run_agent()`.
- Config:
  ```yaml
  outer_router:
    enabled: true
    enabled_platforms: [telegram]
    url: http://127.0.0.1:12110/route
    timeout: 18
    desired_output: decision_brief
    platforms:
      telegram:
        enabled: true
  ```
- Plain Telegram text and transcribed voice messages first call `voice-router.service` with `source=telegram` and a short `recent_context`. If handled, the gateway persists the user/assistant turn and returns immediately.
- Images/documents/skill slash commands bypass the outer router and still go to full Hermes because they need normal media/file/tool handling.
- If `voice-router.service` is unavailable or returns a fallback route, Telegram falls back to the full Hermes gateway AIAgent.

## Gemini Live Config
- Model: `gemini-3.1-flash-live-preview`
- Response modality: AUDIO only
- Voice: Puck
- System prompt: defined in bridge code, French, concise, decision-oriented
- Tool calling: supported, but **Gemini 3.1 Flash Live only supports synchronous function calling**. For long work, use a fast proxy tool (`start_hermes_async`) that immediately returns `job_id/status`, while Hermes continues in the background. Gemini 2.5 Flash Live supports native async/non-blocking function calls if that becomes preferable.
- Tools defined server-side: native `google_search` plus proxy `voice_router` only. Historical direct handlers (`query_memory`, `store_memory`, `execute_task`, etc.) may remain in bridge code for compatibility but must not be exposed in `GEMINI_TOOLS`.
- `read_beeper` has two actions: `list_chats` (shows unread) and `read_chat` (reads messages by chat_id)

## Tool Call Flow
1. User speaks to iPhone → SIP → Asterisk → ExternalMedia RTP → bridge
2. Bridge sends PCM audio to Gemini Live via `session.send_realtime_input()`
3. Gemini processes audio, may emit a FunctionCall
4. Bridge intercepts FunctionCall, dispatches to OpenClaw tool implementation
5. Bridge sends FunctionResponse back to Gemini
6. Gemini speaks the result back as audio
7. Bridge converts audio to mu-law RTP → Asterisk → SIP → iPhone speaker
