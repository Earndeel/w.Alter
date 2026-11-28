# Remote Desktop wake-word diagnostic — session evidence

This reference records the verified failure pattern from 2026-07-30. It is evidence for the general procedure in `SKILL.md`, not a claim that every installation has the same host or device state.

## Observed topology

Hermes Desktop is a Mac surface connected to a Linux Hermes backend. The wake-word RPC is implemented by the backend's `tui_gateway/server.py`, and the listener calls `tools.wake_word.start_listening()` → `sounddevice.InputStream` in that backend process.

## Safe probe

Run from the Hermes runtime, without printing secrets:

```bash
python3 - <<'PY'
import platform
from tools.wake_word import (
    check_wake_word_requirements,
    get_input_device_status,
    load_wake_word_config,
)

cfg = load_wake_word_config()
print('platform:', platform.platform())
print('config:', {k: cfg.get(k) for k in (
    'enabled', 'surface', 'provider', 'phrase', 'input_device'
) if k in cfg})
print('requirements:', check_wake_word_requirements(cfg))
print('input device:', get_input_device_status(cfg))
PY
```

## Verified result

The backend reported the following safe configuration values:

```text
enabled: true
surface: auto
provider: openwakeword
phrase: hey hermes
input_device: null
```

The requirements probe reported dependencies and STT/TTS readiness as available, but the input-device probe returned:

```text
{'selector': None, 'error': 'Error querying device -1'}
```

The decisive start/stop probe was:

```bash
python3 - <<'PY'
from tools.wake_word import load_wake_word_config, start_listening, stop_listening

owner = object()
try:
    start_listening(lambda: None, owner=owner, config=load_wake_word_config())
    print('wake start: succeeded')
except Exception as exc:
    print('wake start: failed')
    print(type(exc).__name__, str(exc))
    if exc.__cause__:
        print('cause:', type(exc.__cause__).__name__, str(exc.__cause__))
finally:
    stop_listening(owner=owner)
PY
```

Observed failure:

```text
wake word: failed to open microphone: Error querying device -1
wake start: failed
RuntimeError Failed to open the wake-word microphone.
cause: PortAudioError Error querying device -1
```

`audio_available: true` in the requirements result only meant that the audio libraries imported. It did not prove that the remote backend had a physical/default input device.

## Correct interpretation

This was not an STT provider or Gemini API failure. The remote Python process attempted to open its own default PortAudio input. The Mac microphone was not forwarded into that process, so changing `stt.provider`, granting Mac permissions, or choosing a remote device index could not make the wake word hear the Mac.

Durable remedies are:

- run the relevant Hermes backend locally on the Mac;
- implement the wake detector in a local Electron/native helper and send a wake event remotely; or
- add a deliberate, supervised audio-forwarding transport.

When none is available, disable the wake-word toggle and use Desktop push-to-talk or a genuine realtime voice path.

## Related provider lesson

The same session also exposed a separate distinction: `tts.provider: gemini` did not imply a registered `stt.provider: gemini`. A user plugin under `~/.hermes/plugins/gemini-stt` was enabled and verified with a generated audio round trip; the successful STT test does not repair a missing remote microphone because wake detection happens before STT.
