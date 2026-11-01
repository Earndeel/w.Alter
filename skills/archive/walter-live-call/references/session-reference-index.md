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
