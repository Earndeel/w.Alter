# Asterisk/Linphone proactive call rings but silent after answer

## Symptom
- The handset rings and the user answers.
- No audio is heard.
- The bridge service logs show no call-start marker for that attempt.
- Health checks may still pass, which only proves the bridge process is alive.

## Root cause pattern
The AMI Originate target can be valid enough to trigger provider-side ringing but still wrong for the final audio bridge.

Observed faulty shape:

```text
Channel: PJSIP/linphone-walter
Context: from-linphone-walter
Exten: 200
Priority: 1
```

This aimed at the registered trunk endpoint, not the remote Linphone user behind the trunk. The result was a call-shaped event with no useful bridge audio.

## Fix pattern
Compose the remote user via the registered trunk endpoint:

```text
Channel: PJSIP/<target-user>@linphone-walter
Context: from-linphone-walter
Exten: 200
Priority: 1
Async: yes
```

Bridge-side pattern:

```python
target = os.environ.get("SIP_CALL_TARGET", "earndeel")
channel = os.environ.get("SIP_CALL_CHANNEL", f"PJSIP/{target}@linphone-walter")
```

## Verification
- Restart the bridge service after patching the originate code.
- Confirm the bridge health endpoint or service status is healthy.
- Place one test call.
- Watch for a bridge call-start marker. If absent, the channel still did not enter ARI/Stasis.
- Confirm the Asterisk app path is the intended bridge or playback/echo test app.

## Lesson
When a call rings but there is silence and no bridge call-start event, routing is the suspect. Do not burn time on Gemini, VAD, RTP packetization, or codec changes until the channel is proven to enter the bridge.