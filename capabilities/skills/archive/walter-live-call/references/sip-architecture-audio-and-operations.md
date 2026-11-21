## SIP-Gemini Direct Bridge (TESTED — 2026-05-23, has issues)

Built raw SIP/UDP server at `/opt/sip-gemini-bridge/sip_bridge.py`. Systemd service `sip-gemini-bridge.service` on port 5062.

**What works:**
- SIP registration with sip.linphone.org (digest auth, qop=auth with nc+cnonce)
- Correct password: `{{bw:9a13ec17-b3c5-4278-a6bc-a5e8517a5187:password}}` (from FreeSWITCH config, not the Asterisk one)
- Inbound calls from Linphone → bridge → Gemini Live → audio back

**What doesn't work:**
- Outbound INVITE to earndeel@sip.linphone.org → 482 Loop Detected (same provider, proxy sees loop between w.alter.ai and earndeel)
- Routing through Asterisk ARI originate → Stasis race condition (call disappears before bridge attaches Gemini)
- Auth header parsing: must strip "Digest " prefix before splitting params; initial parser only read first param due to `split(",", 1)[0]` bug

**Conclusion:** Overengineering. Asterisk handles SIP perfectly. The real bottleneck is ExternalMedia quality, not SIP handling. The bridge is disabled (`systemctl disable sip-gemini-bridge`).

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
