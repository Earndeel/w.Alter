# SIP Bridge Overengineering Anti-Pattern (2026-05-23)

## What happened
Attempted to build a custom SIP-Gemini bridge (`/opt/sip-gemini-bridge/sip_bridge.py`) to bypass Asterisk ExternalMedia 8kHz. Raw SIP/UDP + Opus RTP + direct Gemini WebSocket.

## Why it failed
SIP is deceptively complex. Building a minimal stack required: message parsing, digest auth with qop=auth, proxy auth (407), To tag extraction, SDP negotiation, RTP Opus encode/decode, resampling (24kHz→48kHz), registrar registration, outbound INVITE routing. Each layer introduced bugs. Asterisk handles ALL of this natively with PJSIP.

## Key lesson
**Do not rebuild infrastructure that already exists.** The bottleneck is ExternalMedia quality (ulaw 8kHz), not SIP signaling. Focus effort on: (1) bridge resampling quality (scipy polyphase — done), (2) wider-band ExternalMedia in newer Asterisk, (3) FreeSWITCH media-only via ESL, or (4) accept 8kHz ceiling.

## What DID work
- SIP registration with qop=auth to sip.linphone.org: password `{{bw:9a13ec17-b3c5-4278-a6bc-a5e8517a5187:password}}` (NOT `h3rm3s_2026_s1p` from pjsip.conf)
- Outbound INVITE: 100/110/180/200 OK, Gemini Live connected, but 482 Loop Detected (both accounts on same proxy)
- DNS: `sip.linphone.org` resolves to IPv6 first. Use `176.31.149.179` on IPv4-only VPS.
