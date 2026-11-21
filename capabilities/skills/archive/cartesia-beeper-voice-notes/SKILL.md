---
name: cartesia-beeper-voice-notes
description: Use Cartesia for TTS and Beeper voice notes.
version: 0.1.0
author: Lucas, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cartesia, tts, voice, beeper, messenger]
    related_skills: [beeper-messages, vault-lookup]
---

# Cartesia Beeper Voice Notes Skill

Use the configured Cartesia provider to generate speech, then package it as an OGG/Opus voice note for delivery through Beeper. This skill covers the proven Messenger path; it does not claim that a local Beeper acceptance proves Facebook has delivered the message remotely.

## When to Use

- Monsieur asks to send a voice message using Cartesia.
- A generated Cartesia voice must be sent as a Beeper/Messenger voice note.
- Monsieur asks to retry a voice note after a Beeper network/account reconnection.

Do not use for a plain text message, or for a voice platform whose API contract differs from Beeper's local REST API.

## Prerequisites

- The Hermes `text_to_speech` tool is available and the configured provider accepts `provider="cartesia"`.
- The Cartesia credential is stored in the vault under `cartesia/api_key`; never copy it into this skill, a prompt, a shell command, or a chat response.
- Beeper Desktop is running on the Mac and reachable at `http://100.127.150.1:23373`.
- The Beeper token is retrieved at runtime with `vault get beeper/token`.
- `ffmpeg` and `ffprobe` with libopus are installed on the execution host.
- Load `beeper-messages` for chat resolution, pagination, and Beeper safety rules.

## Quick Reference

**Voice requirement:** always use the configured Lucas voice ID `f0545137-edd6-4591-bd98-b68dafd315ea` at speed `1.0x`. The Hermes `text_to_speech` tool exposes the speed but not a per-call voice selector, so the provider configuration must pass this ID; never fall back to the adapter's unrelated default voice.

```text
text_to_speech(provider="cartesia", speed=1.0, text="<exact text>")
```

**Fast path:** after TTS, prefer one `execute_code` call to convert, probe, upload, send, and read back. Reuse a chat ID already validated in the same session after a lightweight `GET /v1/chats/{chat_id}`; paginate the full chat list only for a new or ambiguous recipient.

Convert the returned WAV to a voice-note file:

```bash
ffmpeg -y -loglevel error -i <input.wav> \
  -ar 48000 -ac 1 -c:a libopus -b:a 48k -vbr on \
  -application voip <output.ogg>
```

Beeper endpoints:

```text
GET  /v1/chats
GET  /v1/chats/{chat_id}
POST /v1/ + assets + /upload/ + base64
POST /v1/chats/{chat_id}/messages
GET  /v1/chats/{chat_id}/messages/{message_id}
```

## Procedure

1. **Resolve and validate the recipient.** Use the Beeper API and the `beeper-messages` procedure to search all private chats, including `title`, participant `fullName`, `username`, and `accountID`. For Facebook Messenger, require the matching private chat to identify as `facebookgo`. If several people or platforms match, ask Monsieur before sending; never guess from a display name.

   Completion criterion: one `type=single` chat ID and the intended network are identified.

2. **Preserve the message exactly.** Use Monsieur's wording verbatim, including accents, apostrophes, names, and punctuation. Do not silently polish or paraphrase it. For a retry, reuse the same intended wording and send at most one retry after the account/network is reported restored.

   Completion criterion: the final TTS text is visible in the tool call and matches the approved wording character-for-character.

3. **Generate through the Hermes TTS tool.** Call `text_to_speech(provider="cartesia", speed=1.0, text="...")`; the active provider configuration passes the Lucas voice ID `f0545137-edd6-4591-bd98-b68dafd315ea` to the adapter. Do not rely on `cartesia_tts.py`'s unrelated fallback voice, and do not call an invented Cartesia REST endpoint. The successful session path returned a WAV with `voice_compatible=false`; treat that as expected and continue to conversion.

   Completion criterion: a non-empty audio file path is returned by `text_to_speech`.

4. **Package for Beeper without extra round trips.** After TTS returns, prefer one `execute_code` call that runs ffmpeg, ffprobe, the asset upload, the send, and the read-back. Convert the WAV to mono OGG/Opus at 48 kHz with libopus and `-application voip`. Measure the real duration with `ffprobe`; do not hard-code it for a different message.

   Completion criterion: `ffprobe` reports `codec_name=opus`, `format_name=ogg`, `channels=1`, and a positive duration.

5. **Upload without exposing credentials.** With `execute_code` or a short `terminal`-driven Python script, read the Beeper token from `vault get beeper/token`, base64-encode the OGG in memory, and `POST /v1/ + assets + /upload/ + base64` with explicit fields:

   ```json
   {
     "content": "<base64 audio>",
     "fileName": "<name>.ogg",
     "mimeType": "audio/ogg"
   }
   ```

   Require HTTP 200 and a non-empty `uploadID`. Never print the token, the Cartesia key, or the base64 payload.

   Completion criterion: an `uploadID` is returned and is not logged as a credential.

6. **Send as a voice note.** Post to `/v1/chats/{chat_id}/messages` using the resolved chat ID and an explicit attachment:

   ```json
   {
     "attachment": {
       "uploadID": "<uploadID>",
       "mimeType": "audio/ogg",
       "fileName": "<name>.ogg",
       "type": "voice-note",
       "duration": <measured_seconds>
     }
   }
   ```

   Require HTTP 200 and a non-empty `pendingMessageID`.

   Completion criterion: Beeper returns a pending message ID for the intended private chat.

7. **Verify locally with short polling, then report the boundary honestly.** Poll `GET /v1/chats/{chat_id}/messages/{pendingMessageID}` immediately, then with a short backoff (for example 0.5 s, 1 s, 2 s, up to a bounded timeout), stopping as soon as the message is readable. Verify `isSender=true` (or the equivalent outgoing flag) and an attachment with `type=audio`, `mimeType=audio/ogg`, and `isVoiceNote=true`. This proves Beeper accepted and recorded an outgoing voice note; it does not, by itself, prove Facebook Messenger relayed it to the recipient.

   Completion criterion: the read-back contains the outgoing OGG voice-note attachment, or the failure is reported without claiming delivery.

## Retry After a Disconnected Messenger Account

When Monsieur says Facebook/Messenger was not connected:

1. Read the target chat and the most recent messages first with a lightweight preflight; do not paginate the whole chat list again when the chat ID is already validated in the current session.
2. Check whether the earlier attempt already appears as an outgoing `audio/ogg` voice note.
3. If it exists and the wording is unchanged, reuse the existing OGG instead of regenerating TTS. If no remote relay is confirmed, explain that the local copy is not proof of Messenger delivery, then perform exactly one retry.
4. Combine the preflight decision, upload, send, and short read-back polling in one `execute_code` call whenever possible.
5. Verify the retry by its new message ID and distinguish `Beeper accepted locally` from `Facebook delivered remotely`.

Never blindly repeat a voice note on every retry request: the first session showed that a locally recorded outgoing message can remain present while the Facebook account is disconnected.

## Pitfalls

- **Do not store or repeat the Cartesia API key.** The vault is the only credential source. The skill only documents the vault key name.
- **Cartesia output is not necessarily platform-ready.** A WAV can be valid audio while still being unsuitable for a voice-note attachment; convert it to OGG/Opus.
- **Use `audio/ogg` and `type=voice-note`.** Sending the WAV or omitting the voice-note type can produce a file attachment instead of a native voice note.
- **Messenger identity matters.** `facebookgo` is the account identifier observed for the Messenger chat; do not send to a WhatsApp or Instagram match with a similar name.
- **Local success is not remote delivery.** A successful upload, POST, and read-back only establish Beeper's local outgoing state. Do not say “Facebook received it” without a remote delivery/receipt signal.
- **Do not hard-code duration.** Measure every generated file; duration changes with the text.
- **Do not claim a remote relay merely because `lastActivity` changed.** It can reflect local activity or another event.
- **Do not duplicate after an uncertain API result.** Re-read the pending message or recent chat before retrying; if the account was disconnected, one deliberate retry is the limit.
- **Do not expose tokens in logs.** Build JSON in Python and pass it to `urllib`/`execute_code`; avoid interpolating credentials into visible shell output.

## Verification

A completed run must have all of these evidence points:

- The recipient is a unique private chat on the requested network.
- The Cartesia call returned a non-empty WAV path.
- `ffprobe` confirmed OGG/Opus, mono, 48 kHz, and positive duration.
- The asset upload returned an `uploadID`.
- The send call returned a `pendingMessageID`.
- Read-back showed an outgoing audio attachment marked as a voice note.
- The final report states whether only local Beeper acceptance was proven or remote Messenger relay was independently confirmed.
