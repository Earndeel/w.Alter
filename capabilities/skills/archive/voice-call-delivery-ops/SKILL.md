---
name: voice-call-delivery-ops
description: Operational patterns for delivering one-shot W.Alter voice messages and outbound call attempts with verified fallback.
category: devops
tags: [voice, call, tts, asterisk, delivery, fallback]
---

# Voice Call Delivery Ops

Use when Monsieur asks W.Alter to call him, say a short message aloud, or deliver a one-shot spoken confirmation.

## Principle

Never claim a call succeeded unless the telephony layer proves the call was answered or audio was delivered. Asterisk/SIP commands can return cleanly while the far end never answers — elegant like a trapdoor.

## One-shot spoken message workflow

1. Generate the requested spoken message as TTS first.
2. Keep the original `MEDIA:<path>` result as the fallback artifact.
3. If using Asterisk playback, convert the audio to mono 8 kHz PCM WAV under `/var/lib/asterisk/sounds/custom/`.
4. Originate playback to the target endpoint/trunk.
5. Verify delivery with real telephony evidence before reporting success.

## Verification checklist

- `core show channels concise` during the attempt: confirms whether a channel is still ringing/active.
- CDR tail: look for a fresh row with `ANSWERED`, not merely a channel creation.
- PJSIP history or Asterisk logs: look for SIP response codes, no-answer, busy, rejection, or lack of progress.
- If there is no answered call evidence, report the failed call attempt and deliver the prepared `MEDIA:` audio instead.

## Asterisk playback conversion pattern

```bash
SRC=/path/to/tts.mp3
DEST=/var/lib/asterisk/sounds/custom/walter-message.wav
ffmpeg -y -hide_banner -loglevel error -i "$SRC" -ar 8000 -ac 1 -sample_fmt s16 "$DEST"
chown asterisk:asterisk "$DEST" 2>/dev/null || true
asterisk -rx 'channel originate PJSIP/<endpoint> application Playback(custom/walter-message)'
```

## Pitfalls

- `channel originate` may print nothing useful even when the call fails to answer.
- A channel briefly appearing in `AppDial2((Outgoing Line))` is not proof of delivery.
- If Linphone/SIP does not answer, do not keep retrying blindly; deliver the prepared audio artifact and state the call path did not confirm pickup.
- For actual conversation rather than a one-shot message, prefer the working browser-direct call path when available; SIP/Linphone remains a telephony substrate that needs verification each time.
