---
name: hermes-voice-module
category: devops
description: Add Gemini as STT and TTS provider in Hermes. Transcription with Gemini 3.1 Flash Lite, speech synthesis with Gemini 3.1 Flash TTS.
tags: [gemini, stt, tts, voice, telegram, hermes]
---

# Hermes Gemini Voice Setup

## Overview
Adds Gemini as a dual STT/TTS provider for Hermes Agent, enabling voice message transcription via Gemini 3.1 Flash Lite and speech synthesis via Gemini 3.1 Flash TTS.

**Status (2026-05-11):** This checkout (`/root/.hermes/hermes-agent/`) has the Gemini STT provider integrated into `tools/transcription_tools.py`. The manual patches in steps 3-4 describe what was added; they are already applied. Verify with `grep -c gemini tools/transcription_tools.py` — ≥8 matches means the provider is built in. The `_resolve_gemini_api_key()` function handles the three-source key resolution chain automatically.

## Architecture
```
Telegram Voice Message
  -> Gateway downloads OGG and caches it
  -> Gateway calls transcribe_audio() from tools/transcription_tools.py
  -> Provider gemini dispatches to _transcribe_gemini()
  -> Gemini 3.1 Flash Lite transcribes audio to text
  -> LLM processes response
  -> TTS tool calls text_to_speech() from tools/tts_tool.py
  -> Provider gemini dispatches to _generate_gemini_tts()
  -> Gemini 3.1 Flash TTS generates audio, saves as OGG
  -> Gateway sends voice back on Telegram
```

## Setup Steps

### 1. Install SDK
```bash
/root/.hermes/hermes-agent/venv/bin/python3 -m pip install google-genai -q
```

### 2. Set Gemini API key
Key should be in /root/.hermes/lancedb-gemini/config.json under api_key.
Also add GEMINI_API_KEY to ~/.hermes/.env

**Key resolution chain** (order of priority, as of `_resolve_gemini_api_key()`):
1. `stt.gemini.api_key` in `config.yaml`
2. `GEMINI_API_KEY` env var → `GOOGLE_API_KEY` env var
3. `/root/.hermes/lancedb-gemini/config.json` → `api_key` field (legacy fallback)

The key is used for `google-genai` SDK 1.x: `genai.Client(api_key=key)`.

### 3. Patch transcription_tools.py for STT

**Note:** These patches describe what was added. On this system (2026-05-11), they are already integrated.

Add gemini case in `_get_provider()` (inside `if explicit:` block, after the `xai` case, before `return provider`):
```python
        if provider == "gemini":
            try:
                from google import genai  # noqa: F401
                return "gemini"
            except ImportError:
                logger.warning(
                    "STT provider 'gemini' configured but google-genai package "
                    "not installed (pip install google-genai)"
                )
                return "none"
```

Add gemini case in `transcribe_audio()` (before the openai case):
```python
    if provider == "gemini":
        gemini_cfg = stt_config.get("gemini", {})
        model_name = model or gemini_cfg.get("model", "gemini-3.1-flash-lite-preview")
        return _transcribe_gemini(file_path, model_name)
```

Add `_transcribe_gemini()` function (before `_transcribe_openai()`):
```python
def _transcribe_gemini(file_path: str, model: str = "gemini-3.1-flash-lite-preview") -> Dict[str, Any]:
    try:
        from google import genai
        from hermes_constants import get_hermes_home
        import json

        try:
            config_path = os.path.join(str(get_hermes_home()), "lancedb-gemini", "config.json")
            with open(config_path) as f:
                gemini_config = json.load(f)
            api_key = gemini_config.get("api_key", os.getenv("GEMINI_API_KEY", ""))
        except Exception:
            api_key = os.getenv("GEMINI_API_KEY", "")

        if not api_key:
            return dict(success=False, transcript="", error="No Gemini API key", provider="gemini")

        client = genai.Client(api_key=api_key)

        with open(file_path, "rb") as f:
            audio_data = f.read()

        mime = "audio/ogg"
        if file_path.endswith(".mp3"): mime = "audio/mpeg"
        elif file_path.endswith(".wav"): mime = "audio/wav"
        elif file_path.endswith(".webm"): mime = "audio/webm"

        response = client.models.generate_content(
            model=model,
            contents=[
                dict(inline_data=dict(mime_type=mime, data=audio_data)),
                dict(text="Transcribe this audio verbatim. Return only the transcript, nothing else.")
            ],
        )

        transcript = response.text.strip()
        if transcript:
            return dict(success=True, transcript=transcript, provider="gemini")
        return dict(success=False, transcript="", provider="gemini")

    except ImportError:
        return dict(success=False, transcript="", error="google-genai not installed", provider="gemini")
    except Exception as e:
        return dict(success=False, transcript="", error=f"Gemini STT failed: {e}", provider="gemini")
```

### 4. Patch tts_tool.py for TTS

Add dispatcher case in `text_to_speech_tool()` (before neutts case):
```python
        elif provider == "gemini":
            logger.info("Generating speech with Gemini TTS...")
            _generate_gemini_tts(text, file_str, tts_config)
            voice_compatible = file_str.endswith(".ogg")
```

Add `_generate_gemini_tts()` function (before `_generate_neutts()`):
```python
def _generate_gemini_tts(text, output_path, tts_config):
    import json as _json
    from google import genai
    from google.genai import types

    try:
        from hermes_constants import get_hermes_home
        config_path = os.path.join(str(get_hermes_home()), "lancedb-gemini", "config.json")
        with open(config_path) as f:
            gemini_config = _json.load(f)
        api_key = gemini_config.get("api_key", os.getenv("GEMINI_API_KEY", ""))
    except Exception:
        api_key = os.getenv("GEMINI_API_KEY", "")

    if not api_key:
        raise ValueError("No Gemini API key found")

    gemini_cfg = tts_config.get("gemini", {})
    model = gemini_cfg.get("model", "gemini-3.1-flash-tts-preview")
    voice = gemini_cfg.get("voice", "Algieba")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice
                    )
                )
            )
        )
    )

    parts_data = []
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                parts_data.append(part.inline_data.data)

    if not parts_data:
        raise ValueError("Gemini TTS returned no audio data")

    audio_bytes = b"".join(parts_data)
    raw_path = output_path + ".raw"
    with open(raw_path, "wb") as f:
        f.write(audio_bytes)

    ext = output_path.rsplit(".", 1)[-1].lower() if "." in output_path else "mp3"
    if ext in ("ogg", "opus"):
        conv_cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                     "-i", raw_path, "-c:a", "libopus", "-b:a", "48k", output_path]
    else:
        conv_cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                     "-i", raw_path, output_path]

    subprocess.run(conv_cmd, check=True, capture_output=True, timeout=30)
    os.remove(raw_path)
    return output_path
```

### 5. Configure in config.yaml
```yaml
stt:
  enabled: true
  provider: gemini
  gemini:
    model: gemini-3.1-flash-lite-preview
tts:
  provider: gemini
  gemini:
    model: gemini-3.1-flash-tts-preview
    voice: Algenib
    system_prompt: "Speak like an elegant butler in their mid-50s: deep resonant voice, calm and measured tone, precise diction, slightly sarcastic undertone, formal authority."
```

### 6. Restart gateway
Kill old gateway, clean stale telegram sessions in state.db, remove gateway_state.json and gateway.pid, then:
```bash
cd /root/.hermes && nohup /root/.local/bin/hermes gateway run --replace > /tmp/hermes_gateway.log 2>&1 &
```

## Available Voices
Gemini TTS voices: Achernar, Achird, **Algenib** (default, Gravelly), Algieba, Aoede, Charon, Callirrhoe, Despina, Enceladus, Erinome, Fenrir, Gacrux, Iapetus, Kore, Laomedeia, Leda, Orus, Pulcherrima, Puck, Rasalgethi, Sadachbia, Sadaltager, Schedar, Sulafat, Umbriel, Vindemiatrix, Zephyr, Zubenelgenubi. Case sensitive. **User preference: Algenib** — always use this voice.

## Pricing
- STT: $0.10 per 1M tokens input, audio input ~$0.000125 per second
- TTS: $0.10 per 1M tokens input, $1.50 per 1M chars output
- Typical voice exchange: $0.003 to $0.01

## Verification (MANDATORY after setup)

Always verify patches were applied — config alone is not enough. Quick diagnostic script: `references/stt-gemini-quick-diag.md`

### Check STT code exists
```bash
grep -c "gemini" /root/.hermes/hermes-agent/tools/transcription_tools.py
# Should return ≥9 (constants, spec check, _get_provider + auto-detect, _resolve_gemini_api_key, mime helper, _transcribe_gemini, dispatch)
```

### Check TTS code exists
```bash
grep -c "gemini" /root/.hermes/hermes-agent/tools/tts_tool.py
# Should return ≥3
```

### Test STT end-to-end
```bash
cd /root/.hermes/hermes-agent && venv/bin/python3 - <<'PY'
from tools.transcription_tools import transcribe_audio, _load_stt_config, _get_provider
result = transcribe_audio('/root/.hermes/audio_cache/audio_e938f1ee542a.ogg')
cfg = _load_stt_config()
print(f'Configured: {cfg.get("provider")}, Resolved: {_get_provider(cfg)}')
print(f'Provider: {result.get("provider")}, Success: {result["success"]}')
print(f'Transcript: {result.get("transcript", "")[:100]}')
print(f'Error: {result.get("error")}')
PY
```
Expected healthy output: `Configured: gemini, Resolved: gemini`, `Success: True`, and a non-empty transcript. If `Resolved: gemini` but the result says `No STT provider available`, the Gemini dispatch branch is missing in `transcribe_audio()`.

### Test TTS end-to-end
```bash
cd /root/.hermes/hermes-agent && python3 -c "
import json
from google import genai
from google.genai import types
with open('/root/.hermes/lancedb-gemini/config.json') as f: key = json.load(f)['api_key']
client = genai.Client(api_key=key)
r = client.models.generate_content(model='gemini-3.1-flash-tts-preview', contents='Test',
    config=types.GenerateContentConfig(response_modalities=['AUDIO'],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Algieba')))))
print(f'TTS OK: {len(r.candidates[0].content.parts)} audio parts')
"
```

### Test Gemini API key validity
```bash
python3 -c "
import json, urllib.request
with open('/root/.hermes/lancedb-gemini/config.json') as f: key = json.load(f)['api_key']
resp = urllib.request.urlopen(f'https://generativelanguage.googleapis.com/v1beta/models?key={key}', timeout=10)
data = json.loads(resp.read())
tts = [m['name'] for m in data['models'] if 'tts' in m['name'].lower()]
stt = [m['name'] for m in data['models'] if 'flash-lite' in m['name'].lower()]
print(f'TTS: {tts}')
print(f'STT: {stt}')
"
```

## Pitfalls
1. **Config ≠ code**: Setting `stt.provider: gemini` in config.yaml does NOT work without the gemini dispatch code in `transcription_tools.py`. Three things must be present: (a) `_get_provider()` must handle `provider == "gemini"`, (b) `transcribe_audio()` must have a `provider == "gemini"` dispatch branch, (c) `_transcribe_gemini()` must exist. On this checkout as of 2026-05-11, all three are built in. Always verify with `grep -c gemini tools/transcription_tools.py`.
2. In `_get_provider`, the gemini case MUST return the string `"gemini"`, not call `_transcribe_gemini()` directly. The dispatch happens later in `transcribe_audio()`.
3. `transcribe_audio()` must include a `provider == "gemini"` branch. A real failure mode is: `_get_provider()` resolves to `gemini`, but no dispatch branch exists, so it falls through to the generic "No STT provider available" error even though config and key are valid.
4. Gemini 3.1 Flash Live only supports `bidiGenerateContent` (WebSocket), not `generateContent`. Use `gemini-3.1-flash-lite-preview` for STT with `generate_content`.
5. **SDK version matters:** With google-genai ≥1.50, use `types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg")` + `types.Part.from_text(text="...")`. The older `dict(inline_data=...)` pattern is deprecated and may break. Always check the SDK version with `python3 -c "import google.genai; print(google.genai.__version__)"`.
6. Gemini TTS returns raw PCM, not an audio file. Must convert via ffmpeg to OGG for Telegram.
7. Voice names are case sensitive: "Algieba" not "algieba".
8. Gateway restart required after code changes; direct Python import tests can pass while the running gateway still uses the old module.
9. Do NOT nest response_modalities and speech_config under generation_config dict. Pass them directly as GenerateContentConfig kwargs or you get Extra inputs not permitted.
10. **Symptom of broken STT**: Voice messages on Telegram show `msg=''` in agent.log (`Cached user voice` followed by `inbound message: msg=''`). This means the Telegram adapter downloaded audio but `_enrich_message_with_transcription()` produced no transcript. Reproduce directly with:
```bash
cd /root/.hermes/hermes-agent && venv/bin/python3 - <<'PY'
from tools.transcription_tools import transcribe_audio, _load_stt_config, _get_provider
p='/root/.hermes/audio_cache/audio_ef7ba73d27c6.ogg'
cfg=_load_stt_config()
print('configured', cfg.get('provider'), 'resolved', _get_provider(cfg))
print(transcribe_audio(p))
PY
```
If output is `resolved gemini` but then `No STT provider available`, add/fix the `provider == "gemini"` dispatch branch.
11. **Gemini TTS timeout on long text**: The `_generate_gemini_tts()` function has a hardcoded `timeout=60` on the `requests.post()` call (line 687 of `tts_tool.py`). For long texts (~2000+ chars), the Gemini TTS API can occasionally take >60s during congestion, causing a `Read timed out` error. **Diagnostic**: test the API directly with a short text (`curl` or Python `urllib` to `:generateContent` endpoint) — if it responds in <10s, the provider code is fine and it was a transient slowdown. **Mitigation**: truncate text before TTS or split into chunks. The `PROVIDER_MAX_TEXT_LENGTH["gemini"]` default is 5000 chars — override via `tts.gemini.max_text_length` in config.yaml to a lower value (e.g., 2000) for more reliable generation.
12. **Gemini TTS for all languages**: Always use Gemini TTS regardless of language. The user explicitly requires Gemini 3.1 Flash TTS + Algenib voice for ALL content, including French. Never fall back to Edge TTS, OpenAI, xAI, or ElevenLabs — even if Gemini's French accent isn't perfect. If Gemini quota is exceeded, inform the user rather than switching providers.
13. **Long text segmentation**: Gemini TTS times out on texts >~1500 chars (the `text_to_speech` tool has a 60s HTTP timeout). Split text into chunks of ~400-500 chars at sentence boundaries, generate each chunk separately with `text_to_speech`, then concatenate with `ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy output.mp3`. Full implementation in `references/tts-long-text-segmentation.md`.
14. **User pre-prompt (W.Alter butler voice)**: Two approaches, prefer (a):
    **(a) Config-level systemInstruction (preferred):** Set `tts.gemini.system_prompt` in `config.yaml`. The patched `_generate_gemini_tts()` reads it and injects as `systemInstruction` in the Gemini API payload — works at the API level without modifying the input text. Requires the code patch (already applied 2026-05-15):
    ```python
    system_prompt = str(gemini_config.get("system_prompt", "")).strip()
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    ```
    **(b) Inline in text (fallback):** Embed as `### DIRECTOR'S NOTES` above `### TRANSCRIPT`. Gemini TTS supports natural-language style control — see [prompting guide](https://ai.google.dev/gemini-api/docs/speech-generation#prompting-guide). Audio tags like `[excitedly]`, `[whispers]`, `[slightly sarcastic]` work inline.
    **Canonical pre-prompt:** *"Speak like an elegant butler in their mid-50s: deep resonant voice, calm and measured tone, precise diction, slightly sarcastic undertone, formal authority."*