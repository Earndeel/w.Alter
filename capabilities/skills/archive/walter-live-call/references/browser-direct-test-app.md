# Browser-direct W.Alter call test app

Session note: 2026-05-07 — W.Alter realtime voice layer was upgraded so both SIP bridge and browser test app can reach the same safe `voice_router` proxy.

## Purpose

The browser app is the fast manual test surface for Lucas when Linphone/SIP is unavailable. It is not the preferred long-term telephony path, but it is useful for testing Gemini Live + tool routing from iPhone/Mac.

## Access

- URL: `https://w-alter.tail32cf1c.ts.net:8765/`
- Requires device on Lucas's Tailscale tailnet.
- If iPhone cannot open it, first open Tailscale on iPhone and verify it is connected.
- TLS cert on server: `/root/.hermes/voice-call/cert.pem`, SAN `w-alter.tail32cf1c.ts.net`.

## Deployed files and service

- Service: `hermes-voice-call.service`
- Working dir: `/root/.hermes/voice-call`
- Server: `/root/.hermes/voice-call/server.py`
- Client: `/root/.hermes/voice-call/static/app.js`
- Tools: `/root/.hermes/voice-call/static/tools.js`
- Health: `curl -sk https://127.0.0.1:8765/health`

## Voice-router integration

The app now has a same-origin proxy:

```text
POST /api/voice-router
  -> http://127.0.0.1:12110/route
```

Client-side Gemini Live exposes `voice_router` via `VoiceRouterTool` in `static/tools.js`.

Supported intents mirror the backend:

```text
route_request | context_lookup | quick_web | deep_web | hermes_async | task_status | store_memory | notify
```

The browser/Gemini client must never reach root-only services directly; it calls `/api/voice-router`, which forwards locally to root-side `voice-router.service`.

## Verification commands

```bash
systemctl show hermes-voice-call.service --property=ActiveState,SubState,MainPID,Result --no-pager
curl -sk https://127.0.0.1:8765/health | python3 -m json.tool
curl -sk -X POST https://127.0.0.1:8765/api/token | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("model"), d.get("mode"), bool(d.get("token")))'
curl -sk -X POST https://127.0.0.1:8765/api/voice-router \
  -H 'Content-Type: application/json' \
  -d '{"intent":"task_status","user_utterance":"status jobs"}' | python3 -m json.tool
node --check /root/.hermes/voice-call/static/app.js
node --check /root/.hermes/voice-call/static/tools.js
/root/.hermes/voice-call/.venv/bin/python -m py_compile /root/.hermes/voice-call/server.py
```

## Good manual test utterances

- `Rappelle-moi nos choix pour la couche vocale.` -> should call `voice_router` with `context_lookup`.
- `Les jobs vocaux en sont où ?` -> should call `voice_router` with `task_status`.
- `Fais une recherche profonde sur Gemini Live vs OpenAI Realtime.` -> should route to deep/Hermes async rather than giving a shallow grounded answer.

## SIP/Linphone note

The SIP path remains:

```text
Linphone account sip:w.alter.ai@sip.linphone.org
Dial 200 for Hermes, 999 for echo
```

But in the 2026-05-07 check Asterisk showed:

```text
linphone-walter-registration/sip:sip.linphone.org  Rejected
```

So do not tell Lucas to use Linphone first unless registration is verified OK with:

```bash
asterisk -rx 'pjsip show registrations'
```

If rejected, send Lucas to the browser app first and repair SIP separately.
