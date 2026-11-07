# Gemini TTS Control Parameters

Reference: https://ai.google.dev/gemini-api/docs/speech-generation

## Model

`gemini-3.1-flash-tts-preview` — single speaker and multi-speaker TTS.

## Audio Tags (inline in transcript)

Tags go in square brackets inside the text to be spoken. Use English tags even for non-English content.

### Emotion / Tone
| Tag | Effect |
|-----|--------|
| `[excitedly]` | Enthousiaste |
| `[bored]` | Ennuyé |
| `[sarcastic]` | Sarcastique |
| `[serious]` | Sérieux |
| `[amazed]` | Émerveillé |
| `[curious]` | Curieux |
| `[mischievously]` | Malicieux |
| `[panicked]` | Paniqué |
| `[reluctantly]` | À contrecœur |

### Volume / Delivery
| Tag | Effect |
|-----|--------|
| `[whispers]` | Chuchotement |
| `[shouting]` | Cri |
| `[trembling]` | Tremblant |

### Pace
| Tag | Effect |
|-----|--------|
| `[fast]` | **Sweet spot for W.Alter** — brisk, natural quick delivery |
| `[very fast]` | Rapid-fire, compressed — too fast for butler persona |
| `[very slow]` | Très lent |
| `[sarcastically, one painfully slow word at a time]` | Rythme sarcastique |

### Pace Calibration (user-tested, 2026-05-15)
| Config | Duration (weather bulletin ~200 words) | Verdict |
|--------|---------------------------------------|---------|
| pacing "brisk but unhurried" | ~30s | Too slow |
| pacing "quick and flowing" + `[fast]` tag | ~25s | ✅ Just right |
| pacing "very fast, rapid-fire" + `[very fast]` tag | ~18s | Too fast |

**Key insight:** Audio tags `[tag]` have a much bigger effect on actual delivery speed than the Director's Notes pacing description. The pacing description sets the mood; the audio tags override the instant delivery. Always use `[fast]` for W.Alter unless told otherwise.

### Non-verbal sounds
| Tag | Effect |
|-----|--------|
| `[cough]` | Toux |
| `[sighs]` | Soupir |
| `[gasp]` | Halètement |
| `[laughs]` | Rire |
| `[giggles]` | Ricanement |
| `[crying]` | Pleurs |
| `[yawn]` | Bâillement |

### Creative / Character
| Tag | Effect |
|-----|--------|
| `[like a cartoon dog]` | Voix de cartoon |
| `[like dracula]` | Voix de Dracula |
| `[short pause]` | Pause courte |

## Director's Notes (prompt-level control)

Use a structured prompt with these sections to control the overall performance:

### 1. Audio Profile
```
# AUDIO PROFILE: [Name]
## "[Role/Archetype]"
```

### 2. Scene
```
## THE SCENE: [Location]
[Description of environment, mood, vibe]
```

### 3. Director's Notes (most important)
```
### DIRECTOR'S NOTES
Style: [upbeat, calm, energetic, bored, etc.]
Pace: [fast, slow, energetic, "no dead air"]
Accent: [French, British, etc.]
```

### 4. Transcript
```
#### TRANSCRIPT
[actual text with inline audio tags]
```

## Usage in Hermes

### Via text_to_speech tool
The Hermes TTS tool sends text to Gemini with the configured voice (Algenib).
For control, prepend a brief instruction before the text:
```
Say in an excited podcast voice: "[excitedly] Bienvenue..."
```

### Via direct API (for podcast generation)
```python
from google import genai
from google.genai import types

client = genai.Client(api_key="...")

prompt = """# AUDIO PROFILE: W.Alter
## "The News Podcaster"

### DIRECTOR'S NOTES
Style: Professional but warm, like a French morning radio host
Pace: Brisk and energetic, no dead air
Accent: Natural French

#### TRANSCRIPT
[excitedly] Bienvenue dans le FirstFT Express...
"""

response = client.models.generate_content(
    model="gemini-3.1-flash-tts-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Algenib"
                )
            )
        ),
    )
)

pcm_data = response.candidates[0].content.parts[0].inline_data.data
# pcm_data is raw s16le at 24kHz mono — convert with ffmpeg
```

## 30 Available Voices

| Voice | Style | Voice | Style |
|-------|-------|-------|-------|
| Zephyr | Bright | Puck | Upbeat |
| Charon | Informative | Kore | Firm |
| Fenrir | Excitable | Leda | Youthful |
| Orus | Firm | Aoede | Breezy |
| Callirrhoe | Easy-going | Autonoe | Bright |
| Enceladus | Breathy | Iapetus | Clear |
| Umbriel | Easy-going | Algieba | Smooth |
| Despina | Smooth | Erinome | Clear |
| **Algenib** | **Gravelly** (default) | Rasalgethi | Informative |
| Laomedeia | Upbeat | Achernar | Soft |
| Alnilam | Firm | Schedar | Even |
| Gacrux | Mature | Pulcherrima | Forward |
| Achird | Friendly | Zubenelgenubi | Casual |
| Vindemiatrix | Gentle | Sadachbia | Lively |
| Sadaltager | Knowledgeable | Sulafat | Warm |

## Multi-speaker TTS

Up to 2 speakers per request. Define each speaker with `SpeakerVoiceConfig`:
```python
multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
    speaker_voice_configs=[
        types.SpeakerVoiceConfig(
            speaker='Joe',
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Kore')
            )
        ),
        types.SpeakerVoiceConfig(
            speaker='Jane',
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Puck')
            )
        ),
    ]
)
```

## User's Pre-Prompt: W.Alter Butler Voice (2-Layer Architecture)

W.Alter has **2 independent layers** for voice/communication:

### Layer 1: AUDIO (how it sounds)
Pure voice characteristics — tone, speed, pitch, rhythm, accent.
**Config key:** `tts.gemini.system_prompt` in config.yaml
**Live:** `AUDIO_STYLE` in app.js and hermes_voice_bridge.py
```
### DIRECTOR'S NOTES — AUDIO (Layer 1: Voice)
Style: no voice amplitude. Fast and efficient. mid-50s, deep resonant voice, calm and collected, very precise diction, slightly sarcastic undertone, elegant and formal butler tone, smooth and authoritative.
Pacing: quick and flowing. Natural brisk rhythm, like a confident briefing. No dragging, no rush. Steady clip with purpose.
Accent: French-speaking, European polish.
```

### Layer 2: COMMUNICATION (what is said)
Content style — personality, humor, sarcasm, verbosity, decision-orientation.
**Config key:** `tts.gemini.communication_style` in config.yaml + `~/.hermes/SOUL.md` for Telegram
**Live:** `COMMUNICATION_STYLE` in app.js and hermes_voice_bridge.py
```
### COMMUNICATION STYLE (Layer 2: Content)
Direct, no fluff. Slightly sarcastic, dry wit. Formal butler tone with a modern edge. 1-3 sentences unless asked for more. Never over-explain. Lead with the answer. Decision-oriented. French-speaking.
```

### Where each layer lives
| File | Layer 1 (Audio) | Layer 2 (Communication) |
|------|----------------|------------------------|
| `~/.hermes/SOUL.md` | — | ✅ (Telegram/text agent identity) |
| `config.yaml` → `tts.gemini.system_prompt` | ✅ | — |
| `config.yaml` → `tts.gemini.communication_style` | — | ✅ (reference only) |
| `app.js` → `AUDIO_STYLE` | ✅ | — |
| `app.js` → `COMMUNICATION_STYLE` | — | ✅ |
| `hermes_voice_bridge.py` → `AUDIO_STYLE` | ✅ | — |
| `hermes_voice_bridge.py` → `COMMUNICATION_STYLE` | — | ✅ |

**Voice:** Always `Algenib` for both TTS and Live.

## ⚠️ CRITICAL PITFALL: systemInstruction Does NOT Work for TTS

`payload["systemInstruction"]` has **ZERO effect** on Gemini TTS voice output. The only way to control voice style is through the Director's Notes format as the actual CONTENT/prompt sent to the API.

The `tts_tool.py` code in Hermes handles this automatically: when `tts.gemini.system_prompt` is set in config.yaml, it wraps the text in Director's Notes format as content (not systemInstruction).

## Long Text Segmenting (Podcast Workflow)

For texts >1500 chars, split into segments to avoid timeout:

1. Break at natural paragraph/sentence boundaries (each segment <1500 chars)
2. Generate each segment as a separate TTS call (via `text_to_speech` tool or API)
3. Concatenate with ffmpeg: `ffmpeg -y -f concat -safe 0 -i concat_list.txt -c copy output.mp3`
4. Send via Telegram `sendAudio` with `title` and `caption` metadata

Segment list file format:
```
file '/tmp/pod_seg_0.mp3'
file '/tmp/pod_seg_1.mp3'
...
```

## Limitations

- Context window: 32k tokens per TTS session
- No streaming support
- Quality drifts on outputs longer than a few minutes — split into chunks
- Occasional text token returns (500 error) — implement retry logic
- Vague prompts may trigger PROHIBITED_CONTENT rejection — add clear preamble
