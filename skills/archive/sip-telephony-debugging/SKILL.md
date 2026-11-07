---
name: sip-telephony-debugging
category: devops
description: Class-level troubleshooting patterns for SIP/Asterisk/Linphone telephony paths, especially calls that ring but have no audio or never enter the media bridge.
tags: [sip, asterisk, linphone, rtp, ari, ami, telephony, debugging]
created: 2026-06-29
---

# SIP Telephony Debugging

Use this skill when a SIP/Linphone/Asterisk call rings, answers, hangs up unexpectedly, has one-way/no audio, or fails to enter an ARI/ExternalMedia voice bridge.

## Core principle
Separate the failure plane before changing media settings:

1. **Signaling** — did INVITE/100/180/200/ACK happen?
2. **Application routing** — did the answered channel enter the intended Asterisk application (`Stasis`, `Playback`, `Echo`, etc.)?
3. **Media negotiation** — was SDP/codecs/RTP address negotiation sane?
4. **RTP flow** — are packets flowing in both directions?
5. **Bridge/model logic** — only after the channel is inside the bridge should Gemini/VAD/STT/tool logic be suspected.

A phone ringing is not proof that the ARI bridge is in the call. Ringing only proves signaling reached something. Telephony, naturally, enjoys this kind of little joke.

## Rings but silence after answer
If the user reports “it rang, I answered, but nothing,” first check whether the bridge received the call:

- In bridge/service logs, look for `StasisStart`, `Call start`, or the bridge-specific call-open marker.
- In Asterisk channel/CDR output, verify the application path is the expected app (`Stasis(bridge_app)` for live bridge, `Playback(...)` for audio-file tests, `Echo()` for loopback tests).
- If the bridge has no call-start event, do **not** debug Gemini, RTP packetization, VAD thresholds, or audio codecs yet. The call did not enter the bridge.

## AMI Originate routing traps
AMI Originate has two common shapes:

### Persistent bridge call
Prefer an originate shape that places the answered outbound leg directly into the long-lived bridge application, or into a dialplan extension whose only job is to enter that bridge.

### One-shot audio test
Use a plain playback/echo dialplan extension to isolate Asterisk/SIP audio from the external bridge.

### Trunk endpoint vs remote user
When using PJSIP through a registered provider trunk, do not assume the bare trunk endpoint dials the remote user. A channel aimed at the trunk itself can ring or create provider-side behavior without placing the final answered channel into the intended bridge.

For providers like linphone.org, the safe pattern is:

```text
PJSIP/<remote-user>@<registered-trunk-endpoint>
```

Example pattern:

```python
target = os.environ.get("SIP_CALL_TARGET", "remote_user")
trunk = os.environ.get("SIP_TRUNK_ENDPOINT", "linphone-trunk")
channel = os.environ.get("SIP_CALL_CHANNEL", f"PJSIP/{target}@{trunk}")
```

Then originate `Channel: {channel}` and route the answered leg into the bridge/dialplan.

## Debug sequence
1. Capture the exact attempted channel target and app/context/exten used by Originate.
2. Confirm provider registration/contact availability.
3. Trigger a controlled test call.
4. Compare three observations:
   - SIP signaling reached the handset.
   - Asterisk says the channel entered the intended app.
   - The bridge logs a call-start event.
5. Only if all three are true should RTP/codec/media debugging begin.

## Regression heuristic
If a pure Asterisk prompt or echo test worked previously, treat a new silent answer as a routing/config regression first, not as proof that the whole SIP architecture is invalid. Reproduce the simplest known-good prompt before proposing a provider or architecture replacement.

## Extra pitfalls observed
- If AMI Originate routes through a dialplan that already `Answer()`s before `Stasis()`, ARI `POST /channels/{id}/answer` may return HTTP 412. Treat 412 / “already answered” as non-fatal and continue ExternalMedia/RTP bridge setup; otherwise the user answers and hears silence.
- Linphone display name may not come from AMI `CallerID` when endpoint `from_user` is set. Set endpoint `callerid="W.Alter" <walterai>`, `send_pai=yes`, and `trust_id_outbound=yes`, then verify the INVITE contains `P-Asserted-Identity: "W.Alter" ...`.

## References
- `references/asterisk-linphone-proactive-silent-answer.md` — concrete pattern: Linphone call rang but no bridge audio because Originate targeted the trunk endpoint instead of the remote user through the trunk.
