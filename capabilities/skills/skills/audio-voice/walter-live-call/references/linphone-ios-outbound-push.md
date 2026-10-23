# Linphone iOS outbound push failure pattern

## Symptom

When W.Alter originates an outbound call via Asterisk/AMI to `PJSIP/earndeel` through `sip.linphone.org`, the iPhone may show an incoming Linphone call but Asterisk never receives a stable answered SIP dialog.

Observed trace pattern:

```text
INVITE sip:earndeel@sip.linphone.org
SIP/2.0 407 Proxy Authentication Required
ACK
INVITE sip:earndeel@sip.linphone.org  # authenticated
SIP/2.0 100 Trying
SIP/2.0 110 Push sent
# sometimes a transient 200 OK appears in later traces, but the channel stays AppDial2/Down, answer=0
CANCEL sip:earndeel@sip.linphone.org
Reason: Q.850;cause=19
```

Asterisk channel detail during the failure:

```text
Application: AppDial2 (Outgoing Line)
State: Down
answer=0
Bridge ID: (Not bridged)
```

So the Hermes/Gemini bridge never starts; this is not an RTP bridge failure.

## What was tested

- Asterisk 22.9.0 source build with ARI/ExternalMedia working.
- Hermes bridge corrected to set RTP remote from `UNICASTRTP_LOCAL_ADDRESS/PORT`.
- Audio resampling corrected: caller PCMU/8 kHz -> Gemini PCM16/16 kHz; Gemini PCM16/24 kHz -> PCMU/8 kHz.
- Plain RTP outbound to Linphone.
- SRTP/SDES offer on the outbound endpoint:

```ini
[earndeel]
media_encryption=sdes
media_encryption_optimistic=yes
```

SRTP adds `a=crypto` to the SDP but does not fix the push-answer reliability issue.

## Interpretation

`110 Push sent` means Flexisip/Linphone.org accepted the INVITE and sent an iOS push notification, but the Linphone iOS app did not complete a stable SIP answer path back to Asterisk before the call was cancelled. Treat this as an outbound reachability/provider/app reliability issue, not a Gemini or RTP issue.

## Future workflow

1. Before debugging audio, confirm the outbound call reached `Stasis(hermes_bridge)` and the bridge logs show `Call start`.
2. If the channel remains `AppDial2 (Outgoing Line)` with `answer=0`, do not debug RTP; inspect SIP response flow.
3. For reliable proactive calls to Monsieur, prefer a real PSTN/SIP trunk to the phone number (or a SIP client/account known to keep a live registration), not Linphone iOS push as the primary production path.
4. Keep Linphone useful for inbound tests and SIP experimentation, but do not treat it as the long-term outbound-call substrate unless it produces stable `180 Ringing`/`200 OK` and enters Stasis repeatedly.
