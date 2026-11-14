---
name: hermes-remote-voice-debugging
description: "Use when Hermes Desktop remote voice or wake-word fails."
category: devops
tags: [hermes, desktop, voice, wake-word, microphone, stt, tts, speech-to-speech, remote]
---

# Hermes Remote Voice Debugging

Use this skill when Hermes Desktop voice behaves slowly, duplicates text and audio, cannot activate the wake word, or reports an STT/TTS provider that is configured but not registered. The central rule is to identify **which process owns the microphone** before changing providers, permissions, or model settings.

## Mental model: four different voice paths

Do not call every voice feature “speech-to-speech”. Trace the actual path first:

```text
1. Wake word
   local microphone -> wake detector -> wake.detected -> voice capture

2. Batch voice / voice replies
   completed audio -> STT request -> Hermes text+tools -> TTS request -> audio reply

3. Desktop push-to-talk
   Desktop/browser microphone -> gateway voice.record -> STT -> Hermes -> optional TTS

4. True realtime speech-to-speech
   local microphone <-> realtime WebSocket model -> optional router -> Hermes for tools/deep work
```

The batch path is a cascade, not a native speech-to-speech model. Its latency is additive: microphone capture/finalization, STT, Hermes reasoning/tool calls, TTS generation, audio conversion, and delivery. If the UI keeps the assistant text and also plays TTS, that is normally one `final_response` rendered twice, not two independent answers.

## First principle: microphone ownership

Hermes Desktop can be a local Mac renderer connected to a remote Linux backend. Backend RPCs such as `wake.start` are implemented in `tui_gateway/server.py`; the detector in `tools/wake_word.py` opens `sounddevice.InputStream` in the **backend process**. `wake_word.input_device` selects a PortAudio device on that backend; it cannot select the Mac microphone across SSH/Tailscale by name or index.

Therefore:

- A Mac microphone permission grant cannot repair a remote backend with no audio device.
- A remote backend may still pass dependency checks while failing when it opens the default input device.
- Desktop voice capture and backend wake-word capture can be different audio paths; one working does not prove the other works.
- The wake detector is on-device and should not call Gemini before detection; STT/TTS credentials are separate readiness gates after the wake event.

## Diagnostic sequence

### 1. Classify the topology

Before touching config, establish whether Desktop is using:

- a local Hermes backend on the same Mac,
- a remote `serve`/dashboard/TUI backend, or
- a messaging gateway.

Map the owning process and restart boundary. Reopening Electron refreshes the renderer, but does not reload Python modules in a remote dashboard or an already-running session worker. Do not restart a shared dashboard merely to refresh a label; determine blast radius first.

### 2. Query the backend truth

Use the backend’s wake RPC/status path when available:

- `wake.status` — requirements, configured surface, provider, input device, ownership, `audio_silent`.
- `wake.start` with the calling surface — exact refusal or stream-open failure.
- `wake.stop` in `finally` during direct probes.

The desktop renderer is a cache of backend truth. A blue/armed UI state is not proof that audio is arriving.

### 3. Run a safe Python probe

Run inside the Hermes runtime and never print credentials:

```python
from tools.wake_word import (
    check_wake_word_requirements,
    get_input_device_status,
    load_wake_word_config,
)

cfg = load_wake_word_config()
print(check_wake_word_requirements(cfg))
print(get_input_device_status(cfg))
```

Interpret the fields separately:

- `deps_available`: detector dependencies are present.
- `audio_available`: audio modules import; it does not guarantee a physical input device.
- `available`: all gates currently pass, but the final `InputStream` open remains authoritative.
- `input_device.error`: the configured/default PortAudio input cannot be resolved.
- `audio_silent: true`: stream opened but delivers only near-zero samples.

For the decisive stream-open test, use a disposable owner and always release it:

```python
from tools.wake_word import load_wake_word_config, start_listening, stop_listening

owner = object()
try:
    start_listening(lambda: None, owner=owner, config=load_wake_word_config())
    print("wake start: succeeded")
except Exception as exc:
    print(type(exc).__name__, str(exc))
    if exc.__cause__:
        print(type(exc.__cause__).__name__, str(exc.__cause__))
finally:
    stop_listening(owner=owner)
```

A `PortAudioError` while querying device `-1` means the backend has no usable default input; changing STT models will not help.

### 4. Choose the fix at the correct layer

For a remote Desktop backend, the durable options are:

1. Run the Hermes backend locally on the Mac and grant the local runtime microphone access.
2. Implement a local wake detector in Electron/a local helper and send only a wake event to the remote backend.
3. Build an explicit, supervised microphone/audio forwarding path from Mac to backend.

Do not present a backend `input_device` index as a cross-machine microphone solution. If local wake detection is not available yet, disable the wake-word toggle and use Desktop push-to-talk or a realtime voice surface instead.

## STT provider registration is independent from TTS

A configured name is not a provider implementation. `tts.provider: gemini` does not register `stt.provider: gemini`, and a successful TTS call does not prove STT dispatch exists.

When Hermes reports that an STT provider name is not registered:

1. Inspect the provider registry and the `_get_provider()`/dispatch path.
2. Prefer the extension route for user-specific providers: a plugin implementing the transcription-provider contract or a configured command provider.
3. Enable the plugin, start a fresh runtime, and verify `hermes plugins list`.
4. Exercise `transcribe_audio()` end-to-end with a non-sensitive generated/test audio file; do not stop at an import test.
5. Keep API-key resolution in the existing secret/config helpers and never print keys.

Do not patch core provider dispatch merely because a user config contains a new string; preserve the core narrow waist unless the provider is intended for the base product.

## Realtime architecture recommendation

For natural conversation, use a realtime audio model as the **interface**, not as a replacement for Hermes’ orchestration:

```text
local mic <-> realtime audio model
                  |
                  +-- simple, safe, short reply: speak immediately
                  +-- tools/memory/research/code: one voice_router call -> Hermes
                                               |
                                               +-> concise result -> realtime audio
```

Keep the realtime model’s tool surface narrow. It should not receive direct terminal, filesystem, billing, or other critical tools. The bridge must preserve the user’s exact utterance when routing to Hermes, and async results should be pushed back into the live session rather than polled.

Use `voice_only` when the user wants conversation. Use `text_and_voice` only when a visible transcript is useful; otherwise the same answer appearing as text and audio feels like a duplicate response. A batch STT → Hermes → TTS mode remains useful for dictating long prompts or retaining the full Hermes transcript, but it is not the right default for low-latency conversation.

## Common pitfalls

- **“Microphone permission denied” diagnosis without topology:** permission on the Mac is irrelevant if `sounddevice` is running on a remote Linux backend.
- **`audio_available` treated as a device proof:** importing `sounddevice` is weaker than opening `InputStream`.
- **Wake detector and voice recorder fight for one mic:** use the shared owner/pause/resume lease; never open two input streams concurrently.
- **Auto-arm versus explicit enable confused:** passive auto-arm should not persist config; an explicit toggle may persist `wake_word.enabled`.
- **Old process assumed refreshed:** restart only the process that owns the stale state, and respect shared dashboard/session blast radius.
- **TTS/STT conflated:** provider registration and credentials are separate for each direction.
- **Live model given every Hermes tool:** preserve the router boundary and let Hermes remain the tool orchestrator.
- **A test that only imports code:** verify the real RPC/stream path and, for providers, a real transcription round trip.

## Verification checklist

Before declaring voice fixed, verify all relevant layers:

- [ ] The microphone owner is local to the intended device.
- [ ] `wake.status` reports a resolved input device, not merely imported audio libraries.
- [ ] A disposable `wake.start` opens the stream and is stopped cleanly.
- [ ] The UI state reflects backend ownership and does not claim “listening” when audio is silent.
- [ ] STT provider resolution and dispatch agree on the same registered name.
- [ ] A real STT round trip returns a non-empty transcript.
- [ ] TTS output is tested separately from STT.
- [ ] Voice mode does not unnecessarily render and vocalize the same response twice.
- [ ] Realtime routing keeps simple dialogue fast and delegates complex work to Hermes.

See `references/remote-wakeword-diagnostic.md` for the concrete remote-backend failure signature and the validation sequence used in the originating session.
