# Gemini TTS Voice Tuning Guide

## The Golden Rule

**Audio tags control the voice. Director's Notes set the baseline.** Both are needed.

- **Director's Notes** (in the structured prompt): set the overall character, pacing, accent
- **Audio tags** (inline `[tag]` in text): override per-utterance — pace, emotion, delivery

Without Director's Notes, Gemini defaults to a melodic, sing-song delivery. Without audio tags, you can't fine-tune individual sentences.

## 2-Layer Architecture

W.Alter has 2 independent layers:
1. **Layer 1: AUDIO** — voice characteristics (tone, speed, rhythm) — see `references/2-layer-architecture.md`
2. **Layer 2: COMMUNICATION** — content style (humor, sarcasm, verbosity) — lives in `~/.hermes/SOUL.md`

**Key insight:** SOUL.md is the agent identity for Telegram/text responses. It's loaded fresh each message. For Gemini Live, Layer 2 is embedded in `COMMUNICATION_STYLE` constant.

## Voice Speed Hierarchy

Tested with Algenib voice on `gemini-3.1-flash-tts-preview` (May 2026):

| Tag | ~Duration (100 words) | Feel |
|-----|----------------------|------|
| `[very slow]` | ~45s | Dragging, theatrical |
| (no tag) | ~30s | Default melodic pace |
| `[fast]` | ~25s | **Sweet spot** — brisk but natural |
| `[very fast]` | ~18s | Rushed, hard to follow |

**User preference: `[fast]`** — natural brisk rhythm, not dragging, not rushing.

## Tuning Iteration Pattern

When user says voice is wrong, follow this sequence:

1. **"Trop lent"** → add `[fast]` audio tag, make pacing directive more aggressive
2. **"Trop chantant/mélodique"** → add "no voice amplitude, monotone" to style directive
3. **"Trop rapide"** → remove speed tag, use "natural brisk rhythm" in pacing
4. **"Trop robotique"** → you overcorrected the text; the audio tag should be in the TRANSCRIPT, not repeated in Director's Notes

**⚠️ PITFALL:** Changing the Director's Notes pacing description alone has minimal effect on speed. The `[fast]`/`[very fast]` audio tag inline in the text is what actually controls rate. Director's Notes set the *character*, tags control the *mechanics*.

## Current W.Alter Voice Profile (canonical)

```yaml
# config.yaml
tts:
  provider: gemini
  gemini:
    model: gemini-3.1-flash-tts-preview
    voice: Algenib
    system_prompt: |
      Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice, calm and collected, very precise diction, slightly sarcastic undertone, elegant and formal butler tone, smooth and authoritative.
      Pacing: quick and flowing. Natural brisk rhythm, like a confident briefing. No dragging, no rush. Steady clip with purpose.
      Accent: French-speaking, European polish.
```

## Effective Audio Tags Reference

### Speed
| Tag | Effect |
|-----|--------|
| `[very fast]` | Rapid-fire, hard to follow |
| `[fast]` | Brisk, natural quick pace |
| `[very slow]` | Dragging, dramatic |

### Tone / Emotion
| Tag | Effect |
|-----|--------|
| `[serious]` | Flat, authoritative — good default for butler |
| `[sarcastic]` | Adds ironic undertone |
| `[bored]` | Flat and uninterested |
| `[excitedly]` | Energetic, animated |

### Delivery
| Tag | Effect |
|-----|--------|
| `[whispers]` | Quiet, intimate |
| `[shouting]` | Loud, aggressive |
| `[short pause]` | Brief pause for emphasis |

### Non-verbal
| Tag | Effect |
|-----|--------|
| `[sighs]` | Audible exhale |
| `[laughs]` | Brief laugh |
| `[cough]` | Cough sound |

## Direct API Call (for testing without Hermes)

```python
from google import genai
from google.genai import types
import struct, subprocess

client = genai.Client(api_key="AIzaSy...")

prompt = """# AUDIO PROFILE: W.Alter
## "The Butler"

## THE SCENE
A private study at dawn. W.Alter speaks into a vintage brass microphone. Quiet, controlled, purposeful.

### DIRECTOR'S NOTES
Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice, calm and collected, very precise diction, slightly sarcastic undertone, elegant and formal butler tone, smooth and authoritative.
Pacing: quick and flowing. Natural brisk rhythm, like a confident briefing. No dragging, no rush. Steady clip with purpose.
Accent: French-speaking, European polish.

#### TRANSCRIPT
[fast] Your text goes here, Monsieur."""

response = client.models.generate_content(
    model="gemini-3.1-flash-tts-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Algenib")
            )
        ),
    ),
)

pcm_data = response.candidates[0].content.parts[0].inline_data.data

# Save as WAV
with open("/tmp/output.wav", "wb") as f:
    f.write(b"RIFF")
    f.write(struct.pack("<I", 36 + len(pcm_data)))
    f.write(b"WAVE")
    f.write(b"fmt ")
    f.write(struct.pack("<I", 16))
    f.write(struct.pack("<HHIIHH", 1, 1, 24000, 48000, 2, 16))
    f.write(b"data")
    f.write(struct.pack("<I", len(pcm_data)))
    f.write(pcm_data)

# Convert to OGG for Telegram
subprocess.run(["ffmpeg", "-y", "-i", "/tmp/output.wav", "-c:a", "libopus", "-b:a", "48k", "/tmp/output.ogg"])
```
