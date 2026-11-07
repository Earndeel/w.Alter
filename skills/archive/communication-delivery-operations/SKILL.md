---
name: communication-delivery-operations
description: Use for voice, telephony, and message delivery.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [voice, telephony, sip, telegram, delivery, notifications]
---

# Communication Delivery Operations

Use this class-level skill for SIP/telephony debugging, voice-call delivery, Telegram or message delivery, and notification result handling. Treat signaling, media, application logic, and recipient delivery as separate layers.

## Always-on rules

- Establish the call/message identity, route, destination, provider/account, and consent boundary before sending or mutating anything.
- Keep credentials and phone/chat identifiers out of logs and reports; use correlation IDs and redacted traces.
- Separate accepted/submitted, queued, ringing/connected, media delivered, application completed, and recipient-visible success.
- Use idempotent delivery records, bounded retries, monotonic state transitions, and explicit timeout/unknown outcomes; never duplicate a call or message after unknown completion without checking the provider state.
- Read back the exact external record or recipient-facing artifact before claiming delivery.

## SIP and telephony diagnosis

Trace DNS/network, SIP registration, transport/TLS, authentication, dialplan, RTP/media, codec, and application handoff separately. Verify both signaling and media paths; a 200 OK or connected call does not prove two-way audio or correct TTS/STT behavior.

Use correlation across call ID, SIP dialog, provider job, media stream, and application task. Capture timestamps and response codes, classify transient versus configuration/auth failures, and stop repeated retries when the error class is non-transient.

## Voice-call delivery

- Define the audio contract: codec, sample rate, channel layout, framing, duration, and provider expectations.
- Verify TTS/STT ownership and prevent duplicate workers, wake events, callbacks, or synthesis.
- Keep batch, realtime, push-to-talk, and wake-word paths distinct because their lifecycle and latency evidence differ.
- On a timeout after dispatch, query the call/job status before retrying; report unknown completion when status cannot be read.
- Confirm the recipient-visible result, not merely local audio generation or a provider acceptance response.

## Message and Telegram delivery

- Validate destination, formatting/media constraints, reply/thread context, and user approval before sending.
- Treat API acceptance, queue state, message ID, attachment upload, and visible chat appearance as separate checks.
- Preserve ordering and deduplicate retries by an idempotency key; do not resend a message because a local network call timed out until the remote state is checked.
- Report partial delivery explicitly when text succeeds but media, buttons, or rich formatting fails.

## Verification

A completed delivery report names the exact route and state observed, the evidence for recipient-visible success, any unknown or partial component, and the remaining retry/cleanup action. Never convert a process exit code into proof that the user received the communication.
