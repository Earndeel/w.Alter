---
name: audio-production-mastery
description: "Mastery of songwriting, AI music prompting, local synthesizer generation (AudioCraft, HeartMula), and acoustic spectrogram feature extraction."
version: 1.0.0
author: Orchestra Research
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Audio, Music, Songwriting, Suno, AudioCraft, HeartMula, Spectrogram, Sound]
---

# Audio Production & AI Music Mastery

A unified class-level skill covering the complete audio production lifecycle: from raw songwriting structures and Suno AI prompts to local machine learning sound synthesizers (AudioCraft, HeartMula) and audio analysis (spectrograms, MFCC features).

---

## 1. Songwriting & Lyrics Craft

Great music balances mathematical structure and raw emotional contrast.

### Structure Skeletons:
- **ABABCB:** Verse/Chorus/Verse/Chorus/Bridge/Chorus (Common Pop/Rock)
- **AABA:** Verse/Verse/Bridge/Verse (Refrains, Ballads)

### Rhyme, Meter, and Prosody:
- Use **slant rhymes** (had/glass) alongside **perfect rhymes** (lean/mean) to prevent a generic "nursery rhyme" feel.
- Match stressed syllables rather than strict word count.
- **Prosody:** Ensure lyrics align with the musical mood (unstable feelings with unresolved chords).

---

## 2. Suno AI Prompt Engineering

Suno utilizes natural language descriptions and performance directives.

### Style Formula:
```
Genre + Mood + Era + Instruments + Vocal Style + Production + Dynamics
```
- **Bad:** `"sad rock song"`
- **Good:** `"Cinematic orchestral spy thriller, smoky female vocalist, brass section with trumpets, sweeping strings, vintage analog warmth"`

### Performance Metatags:
Inject structural and performance directives inside `[brackets]` within your lyrics:
- `[Intro]`, `[Verse]`, `[Chorus]`, `[Bridge]`, `[Guitar Solo]`, `[Outro]`
- `[Whispered]`, `[Belted]`, `[Harmonized Chorus]`, `[Build-up]`, `[End]`

---

## 3. Local Generative Audio (AudioCraft & HeartMula)

When cloud APIs are unavailable, leverage local generative audio models:
- **AudioCraft (Meta):** MusicGen (text-to-music) and AudioGen (text-to-sound).
- **HeartMula:** A specialized local pipeline for structured lyric-to-audio rendering.

```bash
# Example local AudioCraft synthesis via Python CLI
python3 -m audiocraft.cli.synthesize --model musicgen-melody --prompt "Heavy metal riff with 808 sub" --duration 10
```

---

## 4. Acoustic Feature Analysis (Songsee)

To analyze and visualize existing audio files, generate visual spectrograms:
- **Mel Spectrograms:** Model human frequency perception.
- **MFCC (Mel-Frequency Cepstral Coefficients):** Capture timber and spectral envelope.
- **Chroma Vectors:** Map spectral energy into 12 semitones for chord detection.

```bash
# Inspect audio properties using local songsee tool
songsee analyze --file raw-vocals.wav --features mfcc,chroma
```

---

## Support Directory Map
- `references/songwriting-and-ai-music.md`: Comprehensive guide to song dynamics, parody writing, phonetic AI spelling, and Suno clerk auth.
- `references/audiocraft.md`: Local installation, model weights directory, and python code for running AudioCraft models.
- `references/heartmula.md`: Specifications for HeartMula local synthesizers and tagging.
- `references/songsee.md`: Command line documentation for audio spectral analysis and feature extractions.
