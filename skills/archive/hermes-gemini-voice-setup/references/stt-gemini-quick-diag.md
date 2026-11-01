# Gemini STT Quick Diagnostic

Run this to verify the full Gemini STT chain is healthy:

```bash
cd /root/.hermes/hermes-agent && venv/bin/python3 - <<'PY'
from tools.transcription_tools import transcribe_audio, _load_stt_config, _get_provider

# Use any recent cached audio file
import glob, os
files = sorted(glob.glob('/root/.hermes/audio_cache/audio_*.ogg'), key=os.path.getmtime, reverse=True)
path = files[0] if files else None

if not path:
    print("No cached audio files found in /root/.hermes/audio_cache/")
    exit(1)

cfg = _load_stt_config()
provider_cfg = cfg.get('provider')
provider_resolved = _get_provider(cfg)
result = transcribe_audio(path)

print(f"Config provider: {provider_cfg}")
print(f"Resolved provider: {provider_resolved}")
print(f"Success: {result.get('success')}")
print(f"Result provider: {result.get('provider')}")
print(f"Transcript ({len(result.get('transcript',''))} chars): {result.get('transcript','')[:200]}")
print(f"Error: {result.get('error', 'none')}")

# Diagnose common failure modes
if provider_resolved == 'gemini' and not result.get('success'):
    err = result.get('error', '')
    if 'No STT provider' in err:
        print("\n→ PROBLEM: gemini resolved but no dispatch branch in transcribe_audio()")
        print("  Fix: add 'if provider == \"gemini\":' case before the final error return")
    elif 'GEMINI_API_KEY' in err:
        print("\n→ PROBLEM: Gemini API key not found")
        print("  Fix: check _resolve_gemini_api_key() sources: config.yaml stt.gemini.api_key, GEMINI_API_KEY env, lancedb-gemini/config.json")
    elif 'google-genai' in err:
        print("\n→ PROBLEM: google-genai package not installed")
        print("  Fix: pip install google-genai in the hermes venv")
PY
```

## Expected healthy output
```
Config provider: gemini
Resolved provider: gemini
Success: True
Result provider: gemini
Transcript (NN chars): <transcribed text>
Error: none
```

## Common failure modes and their fixes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `Resolved: gemini` but `No STT provider available` | `_get_provider()` returns `gemini` but `transcribe_audio()` has no `provider == "gemini"` dispatch branch | Add the dispatch case in `transcribe_audio()` |
| `Resolved: gemini` but `GEMINI_API_KEY not set` | Key not found in any of the 3 resolution sources | Check `stt.gemini.api_key` in config.yaml, `GEMINI_API_KEY` in .env, `lancedb-gemini/config.json` |
| `Resolved: none` despite `provider: gemini` in config | `_get_provider()` doesn't handle `provider == "gemini"` case | Add the case in `_get_provider()` |
| `google-genai not installed` | Package missing from venv | `venv/bin/pip install google-genai` |
| `msg=''` in gateway log after `Cached user voice` | Transcription returned empty; check the provider dispatch chain | Run this diagnostic script |
