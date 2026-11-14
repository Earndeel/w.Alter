---
name: walter-live-call
category: devops
description: W.Alter voice calls via Asterisk SIP + Gemini Live audio bridge to Hermes/OpenClaw. Deployed on Oracle Cloud VM.
tags: [voice, sip, asterisk, gemini, walter, live-call, openclaw]
created: 2026-04-16
---

# W.Alter Live Call — SIP/Asterisk ↔ Gemini Live ↔ Hermes

## Always-on rules

Gemini Live is the outer conversational surface of W.Alter: fast, concise, preference-aware, and good at handoffs.
It may answer simple requests and call safe proxy tools, but it must not make deep business/system decisions or execute dangerous tools directly.
Complex work is escalated server-side to Hermes/OpenClaw, which returns either a short spoken summary or a background job status.
The live layer may decide to request context, but the backend remains the final policy router.
Prefer one proxy tool such as `context_lookup` / `route_request` over exposing raw dangerous tools.
Spoken output rule: deep results must return `spoken_summary` + `decision` + `next_action` separately from the full TUI/Telegram report; never read long raw orchestrator output aloud.
Never put business logic or tool dispatch on the Gemini/browser side.
For long work, use a fast proxy tool (`start_hermes_async`) that immediately returns `job_id/status`, while Hermes continues in the background.
The user values pragmatism over perfection.

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

## Voice Context Routing

The live layer may decide to request context, but the backend remains the final policy router. Prefer one proxy tool such as `context_lookup` / `route_request` over exposing raw dangerous tools.

Fast read-only decisions that Gemini Live can initiate:
- Hindsight quick recall when Lucas says cues like “tu te souviens”, “rappelle-moi”, “on avait parlé”, “j’ai oublié”, or mentions a known person/project with missing context.
- Combined memory lookup for vague past-discussion/project recall: Hindsight semantic facts + session transcript search; if still ambiguous, ask one short clarifier.
- Google Search grounding for simple current facts.
- Hermes deep research when the request needs comparison, multi-source synthesis, current pricing/news/docs, high confidence, or a decision recommendation.

Spoken output rule: deep results must return `spoken_summary` + `decision` + `next_action` separately from the full TUI/Telegram report; never read long raw orchestrator output aloud.

## Related Skills
- `hermes-voice-module` — Async voice messages (Telegram STT/TTS). Different from live calls.
- `himalaya` — Email management (used by read_emails tool)
- `cloudflare-tunnel-named` — General Cloudflare Tunnel setup guide. Voice-call specific setup in `references/cloudflare-tunnel-voice-call.md`.
- `cloudflare-tunnel-persistent` — Persistent tunnel setup with systemd.

## References (read with skill_read(name, file_path=...))

- `references/2026-05-23-extended-session.md` — Read for the extended FreeSWITCH ARM64 investigation, SIP bridge abandonment, and recorded preference for pragmatic solutions.
- `references/browser-and-router-pitfalls.md` — Read when changing browser client defaults or diagnosing voice-router follow-ups that lose conversation context.
- `references/browser-audio-jitter-buffer.md` — Read when browser playback crackles or gaps, or when changing AudioWorklet buffering and cache busting.
- `references/browser-direct-test-app.md` — Read when operating or verifying the browser-direct call app, its tools, persistence, and completion confirmations.
- `references/browser-live-call-regressions-2026-05-18.md` — Read for browser runtime-load smoke tests, cache busting, voice source tagging, confirmation timing, and health probes.
- `references/cloudflare-tunnel-voice-call.md` — Read when exposing the browser call server through Cloudflare or diagnosing ingress, DNS, and origin TLS failures.
- `references/components-and-live-config.md` — Read for component inventory, service configuration, Gemini tool exposure, voice-router APIs, and audio/tool flow.
- `references/externalmedia-rtp-no-send.md` — Read when Asterisk ExternalMedia sends no RTP or when investigating RTP ports, socket handling, and bridge technology.
- `references/freeswitch-side-by-side-opus.md` — Read when reviewing the side-by-side FreeSWITCH/Opus experiment, ARM64 build pitfalls, or mod_audio_stream playback.
- `references/lessons-and-regression-checklist.md` — Read before implementation changes or when troubleshooting recurring browser, SIP, RTP, routing, tool, or deployment failures.
- `references/linphone-ios-outbound-push.md` — Read when outbound iOS calls stall at push delivery with AppDial2 and no answer.
- `references/oracle-cloud-tailscale-sip.md` — Read when SIP registration or incoming calls fail because of Tailscale routing, public transport configuration, or cloud filtering.
- `references/outbound-calls-and-oracle-routing.md` — Read when diagnosing outbound calls and linphone.org traffic taking the wrong Oracle/Tailscale route.
- `references/outbound-linphone-regression-2026-05-23.md` — Read before declaring Linphone unsuitable; compare successful CDRs, reproduce Asterisk prompts, and review recent regressions.
- `references/session-reference-index.md` — Read to locate the original session notes and their recorded debugging scope.
- `references/sip-482-loop-detected-same-provider.md` — Read when same-provider outbound INVITEs return 482 despite successful authentication.
- `references/sip-architecture-audio-and-operations.md` — Read for dated SIP architecture findings, outbound-call procedures, audio limitations, latency debugging, and FreeSWITCH experiments.
- `references/sip-bridge-overengineering-anti-pattern.md` — Read before replacing working SIP infrastructure or pursuing another standalone bridge architecture.
- `references/sip-bridge-troubleshooting.md` — Read when calls connect without audio; check ARI authentication, ExternalMedia duplication, RTP reuse, 488 responses, and cloud filtering.
- `references/sip-gemini-direct-bridge.md` — Read when investigating the raw SIP/UDP and Opus bridge that bypasses Asterisk ExternalMedia.
- `references/sip-gemini-live-webrtc-parity-2026-05-23.md` — Read when comparing SIP and browser audio quality or investigating packetization, activity markers, and PCMU limitations.
- `references/sip-python-direct-approach.md` — Read when reviewing the direct Python SIP approach as an alternative to the Asterisk bridge.
- `references/voice-router-conversation-context-fix.md` — Read when follow-up requests lose personal context or incorrectly switch from a tool route to a generic direct answer.
