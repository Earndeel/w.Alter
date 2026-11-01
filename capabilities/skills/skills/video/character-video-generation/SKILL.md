---
name: character-video-generation
description: Generate short character-centric videos while preserving identity, facial geometry, and dentition across I2V and reference-to-video models.
version: 1.0.0
metadata:
  hermes:
    tags: [video, character-consistency, image-to-video, reference-to-video, seedance, grok]
---

# Character Video Generation

Use this skill when animating a known person or designed character from one or more reference images, especially when facial identity, teeth, or expression continuity matters.

## Core workflow

1. Identify the fidelity priority: exact opening composition, or identity continuity through motion.
2. Verify the provider-native model ID and current request schema before submitting.
3. Choose the correct conditioning mode:
   - **Reference-to-Video** for identity, face, and dentition continuity.
   - **First-frame I2V** when the exact opening frame matters more than biometric consistency.
   - Do not combine mutually exclusive conditioning modes.
4. Show the user the exact motion prompt before any paid generation when approval is requested or cost control matters.
5. Generate at the native requested duration. Do not generate a longer sparse-motion clip and trim its opening unless the model lacks the requested duration.
6. Verify the artifact before delivery:
   - model/task metadata;
   - dimensions, FPS, and duration;
   - source versus frame 0;
   - several evenly spaced frames for identity and dental drift;
   - visible action cadence rather than merely trusting “no slow motion” in the prompt.

## Multi-character reference-to-multi-shot workflow

When the inputs are character sheets rather than clean stills, do not use the sheets directly as video keyframes: the model may reproduce the board, labels, and pose studies in the film. Treat every sheet as an identity/costume reference, first generate a clean cinematic anchor frame containing all requested characters, inspect that frame, then use it as the sole first-frame I2V input.

For a multi-shot brief, write a timed shot list before submission: one visible action and one camera change per shot, explicit hard-cut language, continuity anchors for every character, and exclusions for reference-board residue, text, logos, watermarks, extra people, duplicate limbs, and weapon escalation. A request for “20 cuts” should be verified as 20 distinct sampled shot compositions; scene detection is evidence, not a substitute for visual review.

Prefer first-frame I2V when the group composition and environment are load-bearing. Preserve the four characters’ identity anchors in the motion prompt, but do not mix first-frame and reference-array conditioning unless the provider explicitly supports both.

## Measured-format and cut-count QA

Never trust a provider’s aspect-ratio or resolution label. Run `ffprobe` on the delivered file and verify measured pixels, SAR, frame count, duration, codecs, and audio. Some FLUX 3 “16:9 / 720p” outputs measure 1280×704; when an exact 16:9 deliverable is required, pad to 1280×720 with `pad=1280:720:0:8:color=black,setsar=1`, preserve the audio stream with `-c:a copy` when it is intentionally unchanged, and re-run the full decode.

For a 20-second multi-shot clip, generate a 1-fps `tile=5x4` storyboard and inspect all 20 cells visually. Use FFmpeg scene detection around threshold 0.10 (`select=gt(scene\\,0.10),showinfo`) to find candidate transitions; 19 measured transitions correspond to 20 shots, while stricter thresholds such as 0.25 can undercount subtle cuts. If the brief requires exactly 20 seconds, trim both streams to `20.000` seconds and verify video `nb_frames` independently of container duration.

See `references/multi-character-multishot-qa.md` for the anchor prompt pattern, timed-shot template, exact-ratio correction, scene-detection commands, and release checklist.

## Conditioning choice

### Reference-to-Video

Prefer this mode for a recurring character. Supply the character image through the provider's reference array, such as `reference_image_urls`. It gives the model an identity reference without requiring the video to reproduce the source as frame zero.

### First-frame I2V

Use only when exact opening pose, framing, lighting, and background are load-bearing. It can preserve the first frame yet reinterpret facial geometry during animation.

### Mutual exclusivity

First-frame, first-and-last-frame, and multimodal reference modes are often mutually exclusive. Never include their fields together unless the current provider documentation explicitly permits it.

## Natural-speed motion prompts

Negative instructions do not control timing by themselves. Give enough distinct action to occupy the native duration and state when actions complete.

Good four-second structure:

> The person moves at natural real-life speed. They immediately blink once, raise their eyebrows, shift their head slightly, return to center, and complete one quick breath. All movements are distinct, responsive, and completed within four seconds, with normal acceleration and no lingering pauses. No slow motion or temporal stretching.

Avoid assigning only one or two tiny micro-movements to a long clip. Models commonly stretch sparse action even when the prompt says “no slow motion.” Avoid unnecessary technical camera language; describe visible action and timing.

## Identity verification

A successful task state is not proof that conditioning worked. Extract and compare:

- frame 0 against the source for first-frame I2V;
- frames at roughly 25%, 50%, 75%, and 95% for face shape, eyes, eyebrows, nose, jaw, beard, ears, complexion, lips, and teeth;
- pose, clothing, and background when those must remain stable.

If frame 0 already depicts another person, treat the request as text-to-video fallback or ignored image conditioning—not ordinary late-frame drift.

## Provider-specific notes

See `references/kie-character-animation.md` for verified Kie.ai Seedance 2 Mini and Grok Imagine Video 1.5 Preview payload details and pitfalls.

## Pitfalls

- Do not claim “no slow motion” from prompt wording or 24 fps metadata; inspect actual movement cadence.
- Do not silently substitute a similarly named model.
- Do not deliver before checking that the input image was actually honored.
- A resolution label such as `480p` can be a provider tier rather than a literal pixel dimension; report measured output dimensions.
- Preserve the exact user-approved prompt when changing model or resolution unless the user requests prompt changes.
