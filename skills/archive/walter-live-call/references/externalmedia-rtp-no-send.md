# ExternalMedia RTP No-Send Issue — ROOT CAUSE CONFIRMED (2026-05-23)

## Problem
Asterisk creates ExternalMedia channel, bridge has 2 channels (PJSIP + UnicastRTP) both "Up"/"sendrecv", but **zero RTP packets** sent to `external_host`.

## Root cause
**Asterisk 20.6.0~dfsg on Debian hardcodes `simple_bridge` for ARI bridges.** `simple_bridge` does NOT forward RTP to ExternalMedia.

Evidence:
- `tcpdump -i lo -n 'udp port 12000'` → **0 packets** during active call
- Manual UDP test packet to port 12000 → **received** (socket works, Asterisk doesn't send)
- `bridge.conf` `technology=softmix` → **ignored** by ARI
- `type=mixing` via ARI → still `simple_bridge`
- `bridge_softmix` loaded, use count always 0 for ARI bridges
- Formats `ulaw`/`opus`/`slin16`, hosts `127.0.0.1`/`10.0.0.24` → all zero

## Exhaustive test matrix (all zero RTP)
1. sock_recvfrom auto-discovery — works for manual packets, receives nothing from Asterisk
2. SO_REUSEADDR on recv socket — no effect
3. bridge.conf forced softmix (`[mixing] type=bridge technology=softmix`) — ARI ignores
4. ConfBridge — creates `softmix` internally but NOT accessible via ARI bridge API
5. pyVoIP 1.6.8 — registration FAIL on linphone.org (socket OSError)
6. `direct_media=yes` on endpoint — no effect
7. `direct_media=no` on endpoint — no effect (was already set)
8. Removed `external_media_address` from pjsip.conf — no effect
9. Codec reduction: opus only, ulaw only, slin16 — all zero
10. Port range 12000-12012, `10.0.0.24` and `127.0.0.1` — none received
11. EAGI fd3 — reads caller audio correctly, but `STREAM FILE` playback introduces ~200ms+ latency per chunk (unsuitable for real-time conversation)
12. `chan_rtp.so` loaded, `bridge_native_rtp.so` loaded, `bridge_softmix.so` loaded — all use count 0 for ARI bridges

## SIP signaling findings
- AMI Originate `Context`+`Exten` creates 2 legs → immediate BYE. Fix: `Application: Stasis` + `Data: hermes_bridge`
- Linphone iOS 6.0.3 sends `488 Not acceptable here` for plain RTP → set "Media encryption" to "None" in Linphone settings
- Earndeel password `{{bw:account.appen.com (lucas.jouvencon@gmail.com):password}}` → 403 Forbidden (wrong password for SIP registration)
- pjsip.conf missing `[section-name]` headers cause options to bleed into adjacent sections → `auth_type` parse errors
- SIP registration works: `w.alter.ai@sip.linphone.org` registered via `transport-public` (10.0.0.24:5060)
- SIP outbound works: `PJSIP/earndeel` → iPhone rings, answers (200 OK), BYE comes from iPhone after ~15s of silence
- Two SIP accounts on same provider (linphone.org) need separate auth/registration sections

## Viable solutions (ranked by reliability)
1. **FreeSWITCH** — industry standard for SIP→AI audio bridging. mod_audio_stream for real-time. Not in Ubuntu 24.04 repos, needs SignalWire repo or compilation.
2. **Asterisk 21+** — newer version may fix simple_bridge ARI hardcoding. Unverified.
3. **SIP Python direct** — bypass Asterisk entirely. `/opt/sip-venv/` has pyVoIP + aiosip + opuslib. pyVoIP registration fails; need custom SIP stack or aiosip.
4. **Kamailio + RTPEngine** — SIP proxy (available in repos) + separate RTP media engine. Complex but proven.
5. **EAGI + AGI** — read audio via fd3, play via STREAM FILE/pipe. Works but high latency (~200ms per chunk).

## Current production workaround
Browser-direct: `https://call.walter-ai.cloud` (Cloudflare Tunnel, valid HTTPS, WebSocket works). iPhone opens in Safari, taps mic, talks to W.Alter via Gemini Live. SIP infrastructure remains in place (registration OK, calls connect) for future audio bridge resolution.
