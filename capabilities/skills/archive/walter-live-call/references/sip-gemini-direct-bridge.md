# SIP-Gemini Direct Bridge

**Created:** 2026-05-23

## Problem

Asterisk ExternalMedia forces PCMU 8kHz regardless of SIP codec negotiation. The SIP leg already uses Opus (48kHz) but ExternalMedia transcodes everything to 8kHz. slin16/slin48 break inbound audio completely (Asterisk 20.6 limitation). FreeSWITCH SIP is dead on ARM64 (sofia-sip UDP send broken).

## Solution

Raw SIP/UDP server in Python that accepts Linphone calls and bridges audio directly to Gemini Live via WebSocket. No Asterisk, no ExternalMedia, no transcoding beyond Opus↔PCM.

## Architecture

```
Linphone (iPhone)
    │ SIP/UDP (INVITE, REGISTER, ACK, BYE)
    ▼
sip_bridge.py (port 5062)
    │ SIP signaling (raw UDP socket)
    │ Opus RTP (opuslib encode/decode)
    │ Gemini Live WebSocket (aiohttp)
    ▼
Gemini Live (gemini-3.1-flash-live-preview)
    │ PCM16 24kHz audio response
    ▼
sip_bridge.py
    │ Resample 24kHz→48kHz (scipy.signal.resample_poly)
    │ Encode to Opus (opuslib)
    │ Send as RTP to Linphone
    ▼
Linphone (iPhone) ← RTP/Opus
```

## Key Components

### SIP Message Parser
Raw SIP parsing — no library needed. SIP is text-based over UDP:
- INVITE: parse SDP for Opus codec, RTP port, IP
- REGISTER: respond 200 OK (accept all)
- ACK: start Gemini session
- BYE: cleanup
- OPTIONS: respond 200 OK

### RTP Session
- opuslib.Decoder/Encoder at 48kHz mono, APPLICATION_VOIP
- Raw UDP socket with proper RTP headers (V=2, PT, seq, ts, ssrc)
- 20ms Opus frames (960 samples at 48kHz)
- Dynamic payload type (111 or negotiated)

### Gemini Live Session
- Server-side WebSocket to `wss://generativelanguage.googleapis.com/ws/...`
- Send: PCM16 48kHz via `realtimeInput.mediaChunks` (mimeType: `audio/pcm;rate=48000`)
- Receive: base64 PCM16 24kHz in `serverContent.modelTurn.parts[].inlineData`
- Resample 24kHz→48kHz with scipy polyphase filter before Opus encode

## Linphone Configuration

| Setting | Value |
|---------|-------|
| SIP Proxy | `sip:129.150.52.60:5062;transport=udp` |
| Username | `walter` |
| Password | (empty — bridge accepts all) |
| Display Name | `W.Alter` |
| Media Encryption | None |

## Systemd Service

`/etc/systemd/system/sip-gemini-bridge.service` with:
- `EnvironmentFile=/root/.hermes/.env` (for GEMINI_API_KEY)
- `SIP_PORT=5062`, `EXTERNAL_IP=129.150.52.60`
- `GEMINI_MODEL=gemini-3.1-flash-live-preview`
- `GEMINI_VOICE=Algenib`

## Firewall

```bash
iptables -I INPUT -p udp --dport 5062 -j ACCEPT
iptables -I INPUT -p udp --dport 20000:20100 -j ACCEPT
```

## Trade-offs

| Aspect | Asterisk + ExternalMedia | SIP-Gemini Direct |
|--------|--------------------------|-------------------|
| Audio quality | PCMU 8kHz | Opus 48kHz |
| Inbound audio | ✅ (ulaw only) | ✅ (Opus) |
| Outbound audio | ✅ (ulaw) | ✅ (Opus) |
| Latency | ~1.8s | TBD (likely similar) |
| Gemini tools | ✅ (voice_router) | TBD (add voice_router proxy) |
| Proactive outbound | ✅ (AMI Originate) | ❌ (not yet) |
| STT fallback | ✅ (Groq Whisper) | ❌ (Gemini native STT) |
| Code complexity | ~1000 lines (ARI + RTP) | ~500 lines (SIP + RTP) |
| Dependencies | Asterisk, ARI, AMI | opuslib, scipy, aiohttp |
| ARM64 compatible | ✅ | ✅ |

## Adding Gemini Tools

To add voice_router proxy to the SIP bridge:
1. Import httpx in the bridge
2. On Gemini FunctionCall, POST to `http://127.0.0.1:12110/route`
3. Send FunctionResponse back to Gemini
4. Same pattern as hermes_voice_bridge.py

## Debugging

```bash
journalctl -u sip-gemini-bridge -f
# Check SIP messages arriving:
tcpdump -i any -n port 5062
# Check RTP flowing:
tcpdump -i any -n 'udp portrange 20000-20100'
```

## Pitfalls

- **Opus frame size must match.** opuslib encoder expects exactly `FRAME_SAMPLES` (960) samples per call. Gemini's 24kHz output resampled to 48kHz produces variable-length chunks. Must chunk into 960-sample frames before encoding.
- **SIP Via header must be preserved.** Responses must echo the exact Via from the request, or Linphone drops the response.
- **Linphone requires REGISTER before INVITE.** Even though the bridge accepts all INVITEs, Linphone won't let you make calls without a successful registration first.
- **RTP SSRC must be consistent.** Use a random SSRC per call, not per packet.
