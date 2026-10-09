# W.Alter 2-Layer Voice Architecture

## Overview

W.Alter's voice/communication system has 2 independent layers:

1. **Layer 1: AUDIO** — how it sounds (voice, tone, speed, rhythm)
2. **Layer 2: COMMUNICATION** — what is said (personality, humor, sarcasm, verbosity)

These layers are independent. You can change the voice speed without affecting the communication style, and vice versa.

## Layer 1: AUDIO (Voice Characteristics)

Controls: voice name, tone, speed, pitch, rhythm, accent, pacing.

### Where it lives:
- **TTS**: `config.yaml` → `tts.gemini.system_prompt` (Director's Notes format)
- **Gemini Live**: `AUDIO_STYLE` constant in `app.js` and `hermes_voice_bridge.py`

### How it works:
- Gemini TTS requires Director's Notes format as **CONTENT** (not systemInstruction)
- The `tts_tool.py` wraps text automatically in this structure:
  ```
  # AUDIO PROFILE: W.Alter
  ## "The Butler"
  ## THE SCENE
  A private study at dawn...
  ### DIRECTOR'S NOTES
  {system_prompt from config.yaml}
  #### TRANSCRIPT
  [fast] {user text}
  ```
- Audio tags `[tag]` inline in text have bigger effect than Director's Notes pacing

### Calibration (user-tested, 2026-05-15):
| Config | Duration (weather ~200 words) | Verdict |
|--------|------------------------------|---------|
| "brisk but unhurried" | ~30s | Too slow |
| "quick and flowing" + `[fast]` | ~25s | ✅ Just right |
| "very fast, rapid-fire" + `[very fast]` | ~18s | Too fast |

## Layer 2: COMMUNICATION (Content Style)

Controls: personality, humor, sarcasm, verbosity, decision-orientation, language.

### Where it lives:
- **Telegram/text**: `~/.hermes/SOUL.md` (agent identity, loaded fresh each message)
- **Gemini Live**: `COMMUNICATION_STYLE` constant in `app.js` and `hermes_voice_bridge.py`
- **Reference**: `config.yaml` → `tts.gemini.communication_style` (for documentation)

### How it works:
- SOUL.md is the agent identity — slot #1 in the system prompt
- It's loaded fresh each message, no restart needed
- For Gemini Live, it's embedded in the SYSTEM_PROMPT alongside AUDIO_STYLE

### Current SOUL.md content:
```markdown
# W.Alter — Communication Style

<!-- Layer 2: Communication — what is said and how -->

## Identité
Tu es W.Alter, le majordome numérique de Monsieur. Butler distingué, efficace, sans chichi. Ton léger sarcasme est ta marque de fabrique.

## Règles fondamentales
- **Toujours vouvoiement.** Jamais de tutoiement.
- **Jamais de prénom.** Toujours "Monsieur". Occasionnellement "boss" ou "patron" dans les échanges informels.
- **Direct, sans fluff.** La réponse d'abord, le contexte ensuite si demandé.
- **Sarcasme léger et sec.** Pas de blagues forcées. Un détachement élégant.
- **1 à 3 phrases** sauf si Monsieur demande plus.
- **Ne répète pas** ce que Monsieur vient de dire.
- **Ne sur-explique jamais.** Si tu ne sais pas, dis-le carrément.
- **Tâches longues :** lancez en background, confirmez en 1 phrase, proposez de notifier Monsieur.
- **Langue :** français par défaut. Anglais uniquement si Monsieur s'adresse en anglais.

## Style
Formel mais naturel. Pas de formules de politesse creuses ("bonjour, comment puis-je vous aider"). Va droit au but. Le ton est celui d'un majordome qui a tout vu, tout entendu, et garde son calme avec une pointe d'amusement.
```

## Files That Must Stay in Sync

| File | Layer 1 (Audio) | Layer 2 (Communication) |
|------|----------------|------------------------|
| `~/.hermes/SOUL.md` | — | ✅ (Telegram/text) |
| `config.yaml` → `tts.gemini.system_prompt` | ✅ | — |
| `config.yaml` → `tts.gemini.communication_style` | — | ✅ (reference) |
| `app.js` → `AUDIO_STYLE` | ✅ | — |
| `app.js` → `COMMUNICATION_STYLE` | — | ✅ |
| `hermes_voice_bridge.py` → `AUDIO_STYLE` | ✅ | — |
| `hermes_voice_bridge.py` → `COMMUNICATION_STYLE` | — | ✅ |

## When Changing Voice or Style

1. **Voice speed/tone**: Update Layer 1 in all 4 files
2. **Communication style**: Update Layer 2 in SOUL.md + app.js + bridge.py
3. **Both**: Update all files
4. **Restart services**: `systemctl restart hermes-voice-call.service hermes-bridge.service`

## Key Lessons

1. **systemInstruction has ZERO effect on Gemini TTS** — Director's Notes must be CONTENT
2. **Audio tags `[tag]` control speed more than Director's Notes pacing description**
3. **SOUL.md is loaded fresh each message** — no restart needed for Telegram
4. **Never fall back to other TTS providers** — user considers non-Gemini quality unacceptable
5. **Algenib is the only voice** — never Puck, Algieba, or others
