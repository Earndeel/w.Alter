---
name: walter-live-call
category: devops
description: W.Alter voice calls via Asterisk SIP + Gemini Live audio bridge to Hermes/OpenClaw. Deployed on Oracle Cloud VM.
tags: [voice, sip, asterisk, gemini, walter, live-call, openclaw]
created: 2026-04-16
---

# W.Alter Live Call — SIP/Asterisk ↔ Gemini Live ↔ Hermes

## Architecture

**Gemini Live = outer realtime communication layer of W.Alter, not the deep brain.** It knows Lucas's communication preferences, handles fast/simple spoken interaction, and escalates complex work to Hermes/OpenClaw. Hermes remains the deep orchestrator/decision engine.

```
iPhone (Linphone)  ←→  SIP/UDP  ←→  Asterisk (Oracle VM)
                                        ↓
                                   ARI ExternalMedia (RTP)
                                        ↓
                              Python bridge (hermes_voice_bridge.py)
                                   ↓           ↓
                              Gemini Live    OpenClaw tools
                              (audio only)   (memory, tasks,
                                              emails, messages,
                                              proactive)
                                        ↓
                              Audio back via RTP → Asterisk → iPhone
```

Key principle: Gemini Live is the outer conversational surface of W.Alter: fast, concise, preference-aware, and good at handoffs. It may answer simple requests and call safe proxy tools, but it must not make deep business/system decisions or execute dangerous tools directly. Complex work is escalated server-side to Hermes/OpenClaw, which returns either a short spoken summary or a background job status.

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

## Voice Context Routing

The live layer may decide to request context, but the backend remains the final policy router. Prefer one proxy tool such as `context_lookup` / `route_request` over exposing raw dangerous tools.

Fast read-only decisions that Gemini Live can initiate:
- Hindsight quick recall when Lucas says cues like “tu te souviens”, “rappelle-moi”, “on avait parlé”, “j’ai oublié”, or mentions a known person/project with missing context.
- Combined memory lookup for vague past-discussion/project recall: Hindsight semantic facts + session transcript search; if still ambiguous, ask one short clarifier.
- Google Search grounding for simple current facts.
- Hermes deep research when the request needs comparison, multi-source synthesis, current pricing/news/docs, high confidence, or a decision recommendation.

Spoken output rule: deep results must return `spoken_summary` + `decision` + `next_action` separately from the full TUI/Telegram report; never read long raw orchestrator output aloud.

## Tool Call Flow
1. User speaks to iPhone → SIP → Asterisk → ExternalMedia RTP → bridge
2. Bridge sends PCM audio to Gemini Live via `session.send_realtime_input()`
3. Gemini processes audio, may emit a FunctionCall
4. Bridge intercepts FunctionCall, dispatches to OpenClaw tool implementation
5. Bridge sends FunctionResponse back to Gemini
6. Gemini speaks the result back as audio
7. Bridge converts audio to mu-law RTP → Asterisk → SIP → iPhone speaker

## SIP-Gemini Direct Bridge (TESTED — 2026-05-23, has issues)

Built raw SIP/UDP server at `/opt/sip-gemini-bridge/sip_bridge.py`. Systemd service `sip-gemini-bridge.service` on port 5062.

**What works:**
- SIP registration with sip.linphone.org (digest auth, qop=auth with nc+cnonce)
- Correct password: `«secret:vault»` (from FreeSWITCH config, not the Asterisk one)
- Inbound calls from Linphone → bridge → Gemini Live → audio back

**What doesn't work:**
- Outbound INVITE to earndeel@sip.linphone.org → 482 Loop Detected (same provider, proxy sees loop between w.alter.ai and earndeel)
- Routing through Asterisk ARI originate → Stasis race condition (call disappears before bridge attaches Gemini)
- Auth header parsing: must strip "Digest " prefix before splitting params; initial parser only read first param due to `split(",", 1)[0]` bug

**Conclusion:** Overengineering. Asterisk handles SIP perfectly. The real bottleneck is ExternalMedia quality, not SIP handling. The bridge is disabled (`systemctl disable sip-gemini-bridge`).

## Pitfalls
- **Constructor vs setter for GeminiLiveAPI config.** `geminilive.js` sets defaults in the constructor (e.g. `this.voiceName = "Algieba"`). When `app.js` calls `client.setVoice("Algenib")` AFTER construction, it works — BUT if anyone creates a new `GeminiLiveAPI` without calling `setVoice()`, the constructor default wins. Always keep constructor defaults in `geminilive.js` in sync with constants in `app.js`. Same applies to `temperature`, `thinkingLevel`, etc.
- **Voice router conversation context missing in `decide_fast_route()`.** (Fixed 2026-05-26) The fast-route decision function `decide_fast_route()` was not injecting `conversation_buffer.get_context()` into the Flash Lite prompt. This caused follow-up questions within the same voice call to be answered generically. Example: user asks "check mes mails" → hermes_async ✅, then "les spam, ils viennent d'où ?" → `direct_answer_flash_lite` with a generic spam lecture instead of understanding it was about HIS emails. Fix: inject `conversation_buffer.get_context(call_id, last_n=6)` into the decide_fast_route prompt AND add a constraint: "if conversation shows a topic requiring tools (emails, messages, personal data), follow-ups must use the same route (hermes_async), never direct_answer." See `references/voice-router-conversation-context-fix.md`.

## Confirmed production architecture (2026-05-23)

Two-path design with current hardware (ARM64 Oracle Cloud):

| Direction | Path | Quality |
|-----------|------|---------|
| **Inbound** (Monsieur calls W.Alter) | Linphone → sip.linphone.org → SIP bridge (port 5062) → Gemini Live | Opus 48kHz |
| **Outbound** (W.Alter calls Monsieur) | Bridge AMI → Asterisk → PJSIP/earndeel → sip.linphone.org → Linphone | ulaw 8kHz |

- Inbound: SIP bridge handles SIP signaling + Opus RTP directly, bypasses ExternalMedia entirely
- Outbound: Must go through Asterisk because sip.linphone.org Flexisip proxy returns 482 Loop Detected when both caller (w.alter.ai) and callee (earndeel) share the same provider domain — the proxy sees the INVITE as a loop
- Asterisk AMI originate credentials: `hermes-ami` / `hermesami2026`, port 5038
- Outbound channel: `PJSIP/earndeel` with `Application: Stasis`, `Data: hermes_bridge`

### SIP 482 Loop Detected — same-provider outbound calls
When both From and To users are on the same SIP domain (e.g., `w.alter.ai@sip.linphone.org` → `earndeel@sip.linphone.org`), the Flexisip proxy returns 482 Loop Detected even with valid Proxy-Auth. The auth succeeds (407 → digest → passes) but the routing triggers loop detection. This is a Flexisip-specific behavior for intra-domain calls when the INVITE comes from outside the proxy's registration context. **Fix:** route outbound calls through Asterisk, which has its own registration and proper Route headers that the proxy trusts.

## FreeSWITCH pivot note (DEAD END on ARM64)

When Asterisk ExternalMedia/RTP quality or Gemini turn-taking becomes fragile, evaluate a side-by-side FreeSWITCH path before more Asterisk surgery. Keep Asterisk as rollback, run FreeSWITCH on separate SIP/RTP ports, first validate plain SIP/Opus to Linphone, then attach Gemini through `mod_audio_stream`. See `references/freeswitch-side-by-side-opus.md` for the ARM64 Docker/build pitfalls and the WebSocket playback response shape.

**ARM64 status (2026-05-23):** FreeSWITCH SIP is dead on ARM64. sofia-sip from HEAD fails with `nua handle creation failed`. **Tag v1.13.17 fixes handle creation** (image `walter/freeswitch-modern:arm64` rebuilt successfully with tagged sofia-sip) but UDP send silently fails — zero packets leave the container on any interface. Tested with --privileged, IPv4 direct IP, all interfaces tcpdump. The library's su_sendmsg is fundamentally broken on ARM64. System sofia-sip 1.12.11 is too old for FS 1.10.12 (missing sdp_bw_tias, sdp_proto_msrp, sdp_media_text). FreeSWITCH mod_audio_stream and mod_opus compile fine, but the SIP stack can't send packets. **Only viable on x86_64.**

## Audio quality

### SIP path (Asterisk)
PCMU/8kHz from Asterisk ExternalMedia — this is the current ceiling. **scipy.signal.resample_poly** replaces audioop.ratecv for better quality resampling (polyphase filter vs linear interpolation). ExternalMedia slin16/slin48 breaks inbound audio (tested 3x, Asterisk 20.6 confirmed limitation).

### Browser-direct path (call.walter-ai.cloud)
PCM 16kHz in / 24kHz out via Gemini Live WebRTC — no SIP/Asterisk bottleneck. Quality issues come from WebSocket jitter (irregular chunk arrival). Fixed with a 200ms pre-buffer ring buffer in `playback.worklet.js`. See `references/browser-audio-jitter-buffer.md`.

## Debugging
- Check bridge health: `curl` to `127.0.0.1:12100/health`
- Bridge logs: `journalctl -u hermes-bridge -f`
- Asterisk SIP: `asterisk -rx "pjsip show registrations"`
- Asterisk CLI verbose: `asterisk -rx "core set verbose 5"` then `asterisk -rvvv`
- ARI test: query `127.0.0.1:8088/ari/channels` with ARI user credentials
- AMI test: Python socket connect to port 5038, login with AMI credentials

### SIP voice-response latency checklist
When the user complains SIP feels slow (e.g. 3–5 s), optimize the bridge before blaming Gemini creativity:
1. Shorten VAD onset: lower `SIP_VAD_MIN_START_FRAMES` (default 2) and `SIP_VAD_PREBUFFER_MAX` (default 10).
2. Detect end of speech sooner: lower `SIP_VAD_MIN_END_FRAMES` (default 12 frames, ~240 ms) instead of keeping ~700 ms silence.
3. Avoid redundant capture while STT runs: once `stt_fallback_turn` is queued, stop forwarding audio for that pending turn.
4. **Use direct audio mode** (`SIP_DIRECT_AUDIO_TO_GEMINI=1`): Gemini Live processes PCMU/8 kHz directly with activity markers. This is faster than STT→text→Gemini. Do NOT run both direct audio AND STT fallback simultaneously — the STT sends duplicate text turns and Gemini repeats itself.
5. Loop `session.receive()` if using a long-lived Gemini Live socket; a single async iterator dies at `turn_complete` and leaves the bridge deaf after the greeting.
6. Log both STT text-to-Gemini timing and Gemini output transcription timing; if STT is fast but Live is slow, the bottleneck is the Live session/model behavior, not capture.
7. Suppress VAD during model speech (`model_speaking_until`): ExternalMedia in a mixing bridge feeds outbound audio back into the inbound path. Without this guard, Gemini hears itself, fires caller activity, and interrupts its own response.

When direct audio mode works, expected latency benchmarks: speech_end → Gemini input transcription ~0.2s, speech_end → first output audio ~1.8s. If significantly slower, check for Gemini session errors or spending cap issues.

When direct audio mode works, expected latency: speech_end → Gemini input transcription ~0.2s, speech_end → first output audio ~1.8s.

## Outbound Calls (W.Alter → Monsieur)
**Current fallback method**: Send `https://call.walter-ai.cloud` link via Telegram with a notification. Monsieur opens the link and talks. Not a phone call, but audio works reliably.

**Current SIP state**: Ubuntu Asterisk 20.6 + Hermes ARI/ExternalMedia bridge can originate Linphone calls, produce Gemini audio, and receive caller RTP. On 2026-05-23, two root causes were found and fixed: (1) the Python `session.receive()` iterator is per-turn, so a long-lived bridge must wrap it in `while True` or Gemini answers only the greeting, and (2) `SIP_DIRECT_AUDIO_TO_GEMINI=1` with activity markers (`ActivityStart`/`ActivityEnd`) now works — Gemini Live processes PCMU/8 kHz audio directly and produces input transcriptions and voiced responses. Stable path: local RMS VAD on SIP RTP, explicit `activity_start`/`activity_end` sent to Gemini, direct audio via `send_realtime_input(audio=...)`. Latency from speech end to first Gemini output transcription: ~1.8s. STT fallback (transcribe → `send_client_content` text turn) remains available as backup but must be DISABLED when direct audio is on (causes repetition). Audio quality is limited to PCMU/8 kHz by Asterisk ExternalMedia; FreeSWITCH/Opus is the path to WebRTC-quality audio. **NEW (2026-05-23):** SIP-Gemini direct bridge (`sip-gemini-bridge.service`, port 5062) bypasses Asterisk for Opus 48kHz. Pending real-call validation.

**Outbound Linphone iOS caveat — treat as regression, not instant architecture verdict**: AMI Originate → `PJSIP/earndeel` via linphone.org can sometimes stop at `100 Trying` → `110 Push sent`, with the Asterisk channel stuck in `AppDial2((Outgoing Line))`, `answer=0`, and no `Stasis` event. However, do **not** conclude Linphone is unusable before checking history: earlier successful CDRs showed `Playback(hello-world)`, `BackGround(demo-congrats)`, and even `Stasis(hermes_bridge)` as `ANSWERED` on the same `PJSIP/earndeel` path. User correction “it worked before, I heard the female Asterisk voice” is a regression marker. First reproduce pure Asterisk `Playback(hello-world)` and/or the stock demo `Context=default, Exten=s`, compare CDR/logs, and rollback recent changes (Asterisk major-version swap, SRTP/media settings, Originate shape) before recommending PSTN/SIP provider replacement. Details: `references/outbound-linphone-regression-2026-05-23.md`; earlier push-failure evidence: `references/linphone-ios-outbound-push.md`.

**Recommended long-term production path**: only move to a reliable PSTN/SIP trunk or phone-number provider after the known-good Linphone/Asterisk prompt path has been re-tested and shown unsuitable. Keep Linphone as a valid test substrate while its pure Asterisk prompt path can still be made to answer.

## Lessons Learned (critical)
- **Never put business logic or tool dispatch on the Gemini/browser side.** Gemini Live must be pure voice I/O. All intelligence lives server-side in Hermes/OpenClaw.
- **ARI ExternalMedia** is the clean way to bridge SIP audio to an external process. Don't try to use browser-based approaches for telephony. **HOWEVER**: Asterisk 20.6.0 on Debian has a confirmed bug where `simple_bridge` (hardcoded for ARI) sends zero RTP to ExternalMedia. This blocks the entire SIP bridge path. Solutions: upgrade Asterisk, use FreeSWITCH, or build SIP Python direct.
- **Asterisk HTTP server** must be explicitly enabled (`http.conf: enabled=yes`) before ARI works, even if `ari.conf` has `[general] enabled=yes`.
- **RTP ulaw to PCM conversion** needs `audioop.lin2ulaw()` / `audioop.ulaw2lin()`. Note: `audioop` is deprecated in Python 3.13+.
- **AMI Originate** for proactive outbound calls. Use `Async: yes` and the correct `Context/Exten/Priority`.
- **AMI Originate through a SIP trunk: use endpoint name, NOT SIP URI.** `PJSIP/earndeel@sip.linphone.org` fails with `endpoint 'sip.linphone.org' was not found`. PJSIP interprets the part before `@` as an endpoint name. Correct: `PJSIP/<endpoint-name>` where the endpoint's AOR contact points to the SIP URI. Example: endpoint `earndeel` with `aors=earndeel-aor` and AOR `contact=sip:earndeel@sip.linphone.org`.
- **Multiple SIP accounts on same provider require separate auth + registration.** Each account (e.g. `w.alter.ai` and `earndeel` on linphone.org) needs its own `[auth]`, `[aor]`, `[endpoint]`, and `[registration]` sections. Sharing auth between accounts fails with 403 Forbidden.
- **403 Forbidden on SIP registration = wrong password.** The auth credentials are invalid. Do NOT trust manual SIP digest tests (Python `hashlib.md5` implementations often produce false 401s due to stale nonce handling). The reliable test is `asterisk -rx "pjsip send register <name>"` + wait 10s + check status.
- **Linphone.org free SIP service.** Accounts like `w.alter.ai@sip.linphone.org` and `earndeel@sip.linphone.org` are free. Both need to be registered (iPhone via Linphone app, Asterisk via pjsip registration) for calls to route between them. linphone.org acts as SIP proxy — it forwards INVITEs to the registered contact address.
- **Browser-direct via Cloudflare Tunnel is the current production call path.** The ARI-based SIP bridge has an unresolved ExternalMedia RTP no-send issue (see `references/externalmedia-rtp-no-send.md`). The browser-direct voice-call server (port 8765) exposed via Cloudflare Tunnel at `https://call.walter-ai.cloud` is the working production solution. SIP/Linphone infrastructure remains in place (registration OK, calls arrive) for future resolution.
- **audioop deprecation**: Python 3.13+ removes `audioop`. Need `audiocodecs` or manual mu-law encoding for future compatibility.
- **Oracle Cloud + Tailscale SIP routing**: VPS behind Tailscale exit node causes SIP traffic to route through Mac's IP. Fix: `tailscale set --exit-node=`, create `transport-public` bound to VPS private IP (10.0.0.24:5060) with `external_media_address=129.150.52.60`, add route `ip route add 176.31.149.179/32 via 10.0.0.1 dev enp0s6 table 52`. Persist in `/etc/rc.local`. See `references/outbound-calls-and-oracle-routing.md`.
- **pjsip identify match**: Must be IP/hostname, NOT SIP URI. `match=sip:sip.linphone.org` causes `getaddrinfo` error. Use `match=176.31.149.179`.
- **Linphone iOS 488 rejection**: Linphone iOS 6.0.3 sends `488 Not acceptable here` for plain RTP. Fix: in Linphone app settings, set "Media encryption" to "None" (or "Disabled"). If no such setting is visible, the version may require SRTP on the Asterisk side.
- **ARI REST calls require Basic Auth.** The bridge's ARI WebSocket connects with `api_key=<user>:<pass>` in the URL, but REST API calls (`POST /ari/channels/{id}/answer`, `/ari/channels/externalMedia`, etc.) need explicit Basic Auth on the `aiohttp.ClientSession`. Without it, Asterisk returns `401 Authentication required` and the bridge silently fails to answer calls. Fix: `aiohttp.ClientSession(auth=aiohttp.BasicAuth(ARI_USER, ARI_PASS))`.
- **ExternalMedia StasisStart duplication.** When the bridge creates an ExternalMedia channel (via `/ari/channels/externalMedia`), Asterisk sends a `StasisStart` event for that channel too. If `handle_event` doesn't filter it, the bridge treats it as a new incoming call → creates another ExternalMedia → infinite loop of leaked sessions and "Address already in use" on RTP ports. Fix: check `channel.get("name", "")` and skip if it contains `"UnicastRTP"` or `"ExternalMedia"`.
- **RTP port reuse after failed calls.** When a call fails mid-setup (e.g. port conflict), the socket may not be released. Add `SO_REUSEADDR` to the RTP recv socket: `self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)`.
- **Browser-direct test app is the current production call path.** If Lucas asks "how do I call Walter?", send him to `https://call.walter-ai.cloud`. Works on iPhone Safari without Tailscale or any app install. SIP/Linphone infrastructure remains in place for future RTP resolution.
- **The browser app also needs the safe proxy pattern.** Do not leave it with only local/proactive tools while the SIP bridge has `voice_router`; keep `/api/voice-router` + `VoiceRouterTool` so both call paths share Hindsight/Hermes routing.
- **CRITICAL — Tool implementations must be real, not stubs.** The bridge ships with stub handlers that return empty data (`{"messages": []}`, `{"emails": []}`). Gemini will call them and report "no messages" even when messages exist. Always verify `_read_messages`, `_read_emails`, `_send_notification`, `_read_beeper` are actually calling APIs (Telegram Bot API, himalaya/Gmail API, Beeper Desktop API). If a user reports "tool use doesn't work during calls", check the implementations first.
- **Browser `get_inbox_digest` real inbox routing.** Do not let `source=messages&session_source=beeper` hit Hermes `state.db`; that only searches Hermes session logs and returns zero. Browser voice-call must expose real sources: `source=email` → Gmail API `in:anywhere -in:trash -in:spam`, `source=beeper` → Beeper Desktop API, `source=all` → email+Beeper aggregate. For follow-ups like “ouvre la conversation”, “lis le dernier message exact”, or “lis l’historique d’aujourd’hui”, use the dedicated browser tool `get_beeper_conversation` backed by `/api/beeper/conversation`; do **not** route those to Hindsight `context_lookup`, which cannot read live Beeper chats. Keep `/root/.hermes/voice-call/proactive.py`, `server.py`, `static/tools.js`, `static/app.js`, and cache-busted `index.html` in sync; restart `hermes-voice-call.service` and verify `/health` shows `beeper` + `email` OK plus `/api/beeper/conversation` returns the expected chat.
- **Browser tool-result confirmation timing.** A 500 ms post-tool `sendTextMessage()` nudge can interrupt Gemini Live's own tool-response turn, producing `response_interrupted` and no audible summary. Delay the nudge (~2.2s) and skip it if audio/output already resumed. Also finalize partial input transcriptions on `TURN_COMPLETE` and immediately before tool calls so logs capture the user's utterance and client-side routing can force `source=all` when Lucas asks for mails + Beeper together.
- Voice-router async jobs must never return raw HTTP 500 to Gemini Live. If `/route` raises, return a JSON `RouteResponse(status="error")` so the browser proxy can parse it and speak a useful failure. Regression probe: `POST /route` with `intent=hermes_async` must return `status=started` + `job_id`; then `GET /jobs/<job_id>` and `/api/voice-router/jobs/<job_id>` must both show queued/running/done. A past bug used `CODE_CUES.search(utterance)` before defining `utterance` in `start_async_job`, which broke all Hermes async handoffs with `NameError` and made Live report `Voice router unavailable: Expecting value`.
- **Beeper tool (`read_beeper`)**: Calls Beeper Desktop API at `http://100.127.150.1:23373` via Tailscale. Token from vault (`beeper/token`). Two-step flow: `list_chats` → get chat_id → `read_chat`. Token can expire if Beeper Desktop re-authenticates.
- **Telegram `read_messages`** uses Bot API `getUpdates` — only works if no other consumer is draining updates (Hermes gateway may consume them first). May return empty if the bot's webhook is active.
- **Oracle Cloud + Tailscale exit node = SIP routing conflict.** Tailscale's routing policy (rule 5270: `from all lookup 52`) sends ALL traffic through `tailscale0` when table 52 has a default route. If the Mac is advertised as exit node (`ExitNode=True`, `AllowedIPs=['0.0.0.0/0']`), SIP registration to `sip.linphone.org` goes through the Mac's public IP (124.120.206.170), not the VPS (129.150.52.60). Even with `tailscale set --exit-node=` to clear the preference, the cached route may persist in table 52. Fix: clear exit node (`tailscale set --exit-node=`) + add explicit route `ip route add 176.31.149.179/32 via 10.0.0.1 dev enp0s6 table 52` + use `transport-public` bound to VPS's own interface IP (10.0.0.24). Persist the route in `/etc/rc.local`.
- **pjsip transport not hot-reloadable.** `external_media_address`, `external_signaling_address`, `bind`, and protocol changes require full `systemctl restart asterisk`, NOT `module reload res_pjsip`. The log will say "Transport 'X' is not fully reloadable, not reloading."
- **pjsip.conf `match` field must NOT use `sip:` URI prefix.** `match=sip:sip.linphone.org` causes `getaddrinfo("sip", "sip.linphone.org", ...): Servname not supported for ai_socktype` and the identify rule silently fails. Use bare IP (`match=176.31.149.179`) or hostname (`match=sip.linphone.org`).
- **pjsip.conf section headers must never be removed during cleanup.** When removing sections (e.g. earndeel-auth, earndeel-registration) from pjsip.conf with sed/grep, always verify the `[section-name]` headers remain. A missing header causes the next section's options to bleed into the previous one — e.g. `type=auth` without a header gets parsed as part of `[earndeel-identify]`, causing `Could not find option suitable for category 'earndeel-identify' named 'auth_type'`. Always `grep "^\[" /etc/asterisk/pjsip.conf` after editing to verify section structure.
- **ExternalMedia RTP remote-port + audio timing fix (2026-05-23).** The silent-call root cause was not only `simple_bridge`: the Python bridge waited to auto-discover Asterisk's RTP source from the first inbound packet, so outbound Gemini audio had no valid destination when W.Alter spoke first. Fix: after creating the ExternalMedia channel, read ARI channel variables `UNICASTRTP_LOCAL_ADDRESS` and `UNICASTRTP_LOCAL_PORT`, then call `rtp.set_remote(address, port)` before launching Gemini. Also resample audio correctly: caller PCMU/8 kHz → PCM16/16 kHz before `send_realtime_input`; Gemini PCM16/24 kHz → PCM16/8 kHz → μ-law before RTP. Outbound Gemini chunks must then be packetized/paced as 20 ms PCMU RTP frames (160-byte payload + 12-byte RTP header). Do not send a whole Gemini audio chunk as one RTP packet; it produces dirty/broken audio.
- **Gemini Live over SIP needs explicit activity markers, but not `explicit_vad_signal`.** Unlike browser/WebRTC, raw SIP/RTP does not provide the Live API with browser-side activity handling. If W.Alter speaks but never responds to the caller, verify `RTP first inbound packet`, `Gemini input audio chunks`, RMS levels, `activity_start/activity_end`, and input transcription logs. Current Python Live API accepts `activity_start=types.ActivityStart()` / `activity_end=types.ActivityEnd()` in `send_realtime_input`, but rejects `explicit_vad_signal=True` with `explicit_vad_signal parameter is not supported in Gemini API`; do not set that flag. `AudioTranscriptionConfig(language_codes=[...])` is also rejected; use `AudioTranscriptionConfig()` with no language_codes.
- **CRITICAL — `session.receive()` is a per-turn iterator.** In the Python `google-genai` SDK, `session.receive()` returns an async iterator that ends at `turn_complete`. A long-lived bridge that calls `receive()` once will hear exactly one Gemini response (the greeting) and then silently ignore all later responses. Fix: wrap in `while True: async for response in session.receive(): ...`. This was the root cause of "W.Alter speaks once then goes silent" across multiple debugging sessions.
- **Never run STT fallback and direct audio simultaneously.** When `SIP_DIRECT_AUDIO_TO_GEMINI=1`, the STT fallback task must be disabled (`if not SIP_DIRECT_AUDIO_TO_GEMINI`). Running both sends audio AND duplicate text turns to Gemini, causing W.Alter to repeat itself.
- **ExternalMedia `slin16` only works outbound.** Setting `EXTERNAL_MEDIA_FORMAT=slin16` sends 16 kHz audio from Asterisk to the bridge, but the bridge receives NO inbound RTP from the SIP leg — "RTP first inbound packet" never appears and no speech is detected. Only `ulaw` works bidirectionally. Do not switch to `slin16` without testing inbound audio. For higher quality, use FreeSWITCH with Opus instead.
- **FreeSWITCH on Oracle Cloud: public IP is NAT'd, cannot bind.** FreeSWITCH Sofia profiles must bind to the private IP (10.0.0.24) with `ext-rtp-ip`/`ext-sip-ip` set to the public IP (129.150.52.60). Setting `rtp-ip=129.150.52.60` fails with "IP not local to this system." See `references/freeswitch-side-by-side-opus.md` for full config pattern.
- **FreeSWITCH gateways must be in separate XML files under the profile subdirectory.** Defining a `<gateway>` inside the profile XML (`external.xml`) is unreliable. Place each gateway in its own file (e.g. `sip_profiles/external/linphone-walter.xml`) and include via `<gateways><X-PRE-PROCESS cmd="include" data="external/*.xml"/></gateways>` inside the profile.
- **FreeSWITCH XML preprocessor variables are NOT resolved in Sofia profiles.** `${external_sip_ip}`, `${global_codec_prefs}` etc. remain as literal strings when Sofia creates the SIP UA. Hardcode values in profile XML files. Keep `vars.xml` for dialplan and other sections.
- **Oracle Cloud Security List vs iptables.** iptables/nftables rules control VM-level filtering. The Oracle VCN Security List controls cloud-level filtering separately. If SIP registration sends packets but gets no response (0 counter packets on dport), the security list may be blocking the port. Standard ports (5060) are usually open; non-standard ports (5090) may not be.
- **FreeSWITCH Docker: always use `-nf -nonat`.** The default CMD (`freeswitch -nc`) daemonizes and the container exits immediately. Use `--entrypoint /usr/local/freeswitch/bin/freeswitch ... -nf -nonat` for foreground mode.
- **SIP quality limitation is architectural, not a bug.** Asterisk ExternalMedia forces PCMU 8kHz in both directions regardless of SIP codec negotiation. The path Gemini (24kHz) → resample 8kHz PCMU → Asterisk → SIP → Linphone and back adds latency, artifacts, and "holes" in the response audio. FreeSWITCH with `mod_audio_stream` + Opus is the only path to WebRTC-comparable quality. **UPDATE (2026-05-23):** The SIP-Gemini direct bridge (`/opt/sip-gemini-bridge/sip_bridge.py`) bypasses Asterisk entirely for Opus 48kHz quality.
- **ExternalMedia slin16/slin48 breaks inbound audio (Asterisk 20.6 confirmed).** Setting `EXTERNAL_MEDIA_FORMAT=slin16` or `slin48` sends higher-quality audio FROM Asterisk TO the bridge (outbound ✅), but the bridge receives NO inbound RTP from the SIP leg — "RTP first inbound packet" never appears. Tested with slin16 (2x) and slin48 (1x). The SIP leg already negotiates Opus → slin48 natively, but ExternalMedia does not forward inbound audio for non-ulaw formats. Only `ulaw` works bidirectionally. Root cause: Asterisk 20.6 UnicastRTP channel does not transcode/forward inbound audio when ExternalMedia format differs from the SIP leg's native format.
- **Opus IS negotiated on SIP leg.** Despite ExternalMedia forcing ulaw, the PJSIP channel uses Opus natively: `NativeFormats: (opus)`, `ReadFormat: slin48`, `WriteFormat: slin48`. The bottleneck is ExternalMedia, not the SIP negotiation.
- **scipy.signal.resample_poly replaces audioop.ratecv.** Polyphase filter resampling (scipy) is significantly better quality than audioop's linear interpolation. Installed scipy 1.17.1 system-wide. Use `hq_resample(pcm_bytes, from_rate, to_rate)` in the bridge for inbound (8kHz→16kHz) and outbound (24kHz→8kHz) resampling.
- **sip.linphone.org DNS resolves to IPv6 first.** On IPv4-only VPS, `getent hosts sip.linphone.org` returns `2001:41d0:303:b0d2::4`. FreeSWITCH sofia-sip tries IPv6, fails silently. Fix: hardcode IPv4 address `176.31.149.179` in gateway proxy config instead of `sip:sip.linphone.org`.
- **Asterisk pjsip.conf must have `transport-public` for linphone.org.** Without it, the endpoint references a non-existent transport and PJSIP falls back to `transport-tailscale` (100.91.35.121). sip.linphone.org never responds to packets from the Tailscale IP. Fix: create `[transport-public]` bound to `10.0.0.24:5060` with `external_media_address=129.150.52.60` and `external_signaling_address=129.150.52.60`.
- **pjsip.conf duplicate sections break all transports.** If `[transport-public]` appears twice (e.g. from a failed sed edit), Asterisk loads zero transports and all endpoints fail. Always `grep '^\[' /etc/asterisk/pjsip.conf | sort | uniq -d` after editing.
- **FreeSWITCH ARM64 sofia-sip: handle creation fixed but UDP send broken.** sofia-sip from `HEAD` (latest commit) fails with `nua_common.c:121 nh_create_handle() failed`. Tag `v1.13.17` fixes this. But UDP send silently fails — zero packets on any interface (tested with tcpdump on any, lo, docker0). The issue is in sofia-sip's su_sendmsg on ARM64. `--privileged` doesn't help. **Dead end for ARM64 SIP.**
- **FreeSWITCH Docker: external profile port conflict.** If Asterisk is on 5060, FreeSWITCH external profile must use a different port (5090). Port conflict causes `Error Creating SIP UA for profile: external`.
- **FreeSWITCH Docker: always use `-nf -nonat`.** The default CMD (`freeswitch -nc`) daemonizes and the container exits immediately. Use `--entrypoint /usr/local/freeswitch/bin/freeswitch ... -nf -nonat` for foreground mode.
- **Asterisk version note.** Asterisk 22.9.0 source build was tested but rolled back to Ubuntu Asterisk 20.6 after outbound Linphone regressions. The source build needs `Type=simple` systemd override because it does not emit Debian's `Type=notify` readiness signal. Keep the old note: `simple_bridge` still ignores `bridge.conf` technology settings, and tcpdump on the external_host port may show 0 packets until the bridge sends audio first, because Asterisk's useful receive port is `UNICASTRTP_LOCAL_PORT`, not necessarily the external_host port.
- **AMI Originate 2-leg trap.** `Context`+`Exten` in Originate creates a second leg. If the second leg fails or completes instantly, BYE is sent. Fix: `Application: Stasis` + `Data: hermes_bridge` for persistent calls, or `Application: Playback` + `Data: hello-world` for one-shot audio.
- **pjsip.conf section header corruption.** When editing pjsip.conf with sed/grep, missing `[section-name]` headers cause options to bleed into adjacent sections (e.g. `type=auth` parsed as part of `[earndeel-identify]`). Always verify with `grep '^\[' /etc/asterisk/pjsip.conf` after edits.
- **pyVoIP 1.6.8 unreliable for linphone.org.** Registration fails with socket errors. Not a viable Asterisk replacement for SIP.
- **Linphone iOS SRTP.** If iPhone sends `488 Not acceptable here`, set Media encryption to "None" in Linphone settings.
- **sock_recvfrom works in asyncio.** `loop.sock_recvfrom()` correctly returns (data, addr) for UDP sockets. Useful for RTP source auto-discovery if Asterisk ever sends packets.
- **Cloudflare Tunnel for voice-call exposure.** The browser-direct voice-call server (port 8765, HTTPS/TLS) can be exposed publicly via Cloudflare Tunnel when Tailscale is not available on the client. Add hostname (e.g. `call.walter-ai.cloud`) to `~/.cloudflared/config.yml` pointing to `https://localhost:8765`. **Critical**: the origin uses a Tailscale/Let's Encrypt cert for `w-alter.tail32cf1c.ts.net`, NOT for `localhost`. Cloudflare tunnel will reject the TLS handshake unless `originRequest.noTLSVerify: true` is set on the ingress entry. Cloudflare supports WebSocket (required for Gemini Live). The tunnel proxies with its own cert, so users see a valid `walter-ai.cloud` certificate.
- **Oracle Cloud iptables vs Security List.** iptables rules are controlled by the VM (open UDP 5060 + 10000-20000). The Oracle Security List at the VCN/subnet level is SEPARATE and may block inbound UDP even if iptables allows it. If registration works (outbound + response) but incoming calls don't arrive (no INVITE in logs), the Security List needs opening via OCI console or API. Persist iptables with a systemd service (`iptables-restore.service`) pointing to `/etc/iptables/rules.v4`.
- **SIP registration "Rejected" after long uptime.** Asterisk's registration to linphone.org expires silently after days. `pjsip send register linphone-walter-registration` usually fixes it. If it stays `Unregistered`, check transport route: `ip route get 176.31.149.179` must go via VPS interface (enp0s6), not tailscale0. See `references/oracle-cloud-tailscale-sip.md`.
- **User preference: ship what works.** When the user says "je comprends pas ce que t'essaye de faire" or "on peut pas trouver une solution avec notre matos", it means stop trying 15 different approaches, use what already works, and iterate. The user values pragmatism over perfection. If Asterisk handles SIP and the bridge handles Gemini, that's the answer — even at 8kHz. Don't rebuild SIP from scratch, don't chase FreeSWITCH on ARM64, don't build standalone SIP servers when the existing infrastructure works.
- **SIP digest auth: always strip "Digest " prefix first.** The `split(",", 1)[0]` pattern only reads the first parameter (realm), losing nonce/qop/opaque. Fix: strip prefix, then split each comma-separated param individually.
- **Correct Linphone password: `«secret:vault»`.** The Asterisk pjsip.conf has `h3rm3s_2026_s1p` but the working password (verified with SIP REGISTER → 200 OK) is `«secret:vault»`.

## Session References

- `references/sip-bridge-troubleshooting.md` — "Call connected but no audio" debugging flow: ARI auth, ExternalMedia duplication, RTP port reuse, 488 rejections, Oracle Security List.
- `references/externalmedia-rtp-no-send.md` — Asterisk ExternalMedia zero-RTP debugging: sock_recvfrom, SO_REUSEADDR, bridge technology, UNICASTRTP_LOCAL_PORT, hypotheses and next steps (2026-05-23).
- `references/outbound-linphone-regression-2026-05-23.md` — session regression note: user-corrected evidence that outbound Linphone/Asterisk prompts worked earlier (`Playback hello-world`, `demo-congrats`, `Stasis` answered); workflow for checking CDRs, reproducing pure Asterisk prompts, and rolling back recent Asterisk/media/Originate changes before declaring Linphone unsuitable.
- `references/linphone-ios-outbound-push.md` — outbound Linphone iOS push failure pattern: `110 Push sent`, channel stuck in `AppDial2`, `answer=0`, optional SRTP/SDES does not make it production-reliable; prefer PSTN/SIP trunk for proactive calls.
- `references/cloudflare-tunnel-voice-call.md` — Cloudflare Tunnel setup for voice-call server: ingress config with noTLSVerify, DNS CNAME, verification commands, pitfalls.
- `references/browser-live-call-regressions-2026-05-18.md` — browser Gemini Live runtime-load smoke test, cache busting, `source="voice"`, confirmation timing, and health/probe sequence.
- `references/sip-gemini-direct-bridge.md` — SIP-Gemini direct bridge: raw SIP/UDP → Opus RTP → Gemini Live WebSocket. Bypasses Asterisk ExternalMedia for 48kHz Opus quality. Code at `/opt/sip-gemini-bridge/sip_bridge.py`.
- `references/sip-gemini-live-webrtc-parity-2026-05-23.md` — session note on SIP vs WebRTC quality: dead-iPhone false positive, PCMU/8 kHz limits, RTP packetization, Gemini Live `activity_start/activity_end` quirks, and when to stop tuning and move to wideband/Opus or native WebRTC.
- `references/oracle-cloud-tailscale-sip.md` — Oracle Cloud + Tailscale exit node SIP routing fix: transport-public config, iptables, Oracle Security List, route persistence.
- `references/sip-482-loop-detected-same-provider.md` — SIP 482 Loop Detected on same-provider outbound calls: Flexisip behavior, auth digest details, Asterisk as workaround.
- `references/2026-05-23-extended-session.md` — FreeSWITCH ARM64 findings, SIP bridge attempt and abandonment, user preference for pragmatism.

## Related Skills
- `hermes-voice-module` — Async voice messages (Telegram STT/TTS). Different from live calls.
- `himalaya` — Email management (used by read_emails tool)
- `cloudflare-tunnel-named` — General Cloudflare Tunnel setup guide. Voice-call specific setup in `references/cloudflare-tunnel-voice-call.md`.
- `cloudflare-tunnel-persistent` — Persistent tunnel setup with systemd.
