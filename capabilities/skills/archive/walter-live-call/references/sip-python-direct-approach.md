# SIP Python Direct Bridge — Skeleton (2026-05-23)

## Purpose
Bypass Asterisk ExternalMedia (broken in v20.6.0) by handling SIP/RTP directly in Python.

## Dependencies (installed in /opt/sip-venv/)
- `pyVoIP==1.6.8` — SIP/RTP library (registration FAILS on linphone.org, but may work with raw sockets)
- `aiosip==0.2.0` — Async SIP library
- `opuslib==3.0.1` — Opus codec bindings
- `websockets` — Gemini Live connection

## Architecture
```
iPhone (Linphone) ←→ SIP/UDP ←→ Python SIP server (port 5060)
                                      ↓
                                 RTP handler (port 13000+)
                                      ↓
                                 Gemini Live (WebSocket)
                                      ↓
                                 Audio back via RTP → iPhone
```

## Key challenge
SIP registration with linphone.org requires proper digest auth (MD5 nonce handling). pyVoIP's implementation fails. Need raw SIP socket implementation or fix pyVoIP's auth.

## Skeleton exists at
`/opt/openclaw/sip_direct_bridge.py` — includes SIPClient class, register(), listen_for_calls(), and Gemini Live session bridging. Not yet tested end-to-end.

## Next steps
1. Test raw SIP REGISTER with proper digest auth
2. Handle SIP INVITE (incoming calls)
3. Implement bidirectional RTP with proper headers (seq, timestamp, SSRC)
4. Convert between ulaw (RTP) and PCM16 (Gemini Live)
5. Add AMI Originate capability for outbound calls
