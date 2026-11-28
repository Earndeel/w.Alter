---
name: seedance-video-prompts
description: Craft prompts for Jimeng Seedance 2.0 AI video generation.
version: 0.1.0
author: Hermes
metadata:
  hermes:
    tags:
      - Seedance
      - Video
      - Prompt-Engineering
      - Jimeng
---

# Seedance 2.0 Video Prompt Writing

Craft effective prompts for ByteDance's Jimeng Seedance 2.0 multimodal AI video model. Covers the `@` reference system for combining images, videos, and audio into a single generation. This skill authors prompts only — it does not call any video generation API.

## When to Use

- "Write a Seedance prompt for..."
- "Help me craft a Jimeng video with references"
- "How do I structure a Seedance 2.0 prompt?"
- "What camera terms work in Seedance?"
- "Make a product ad / short drama / dance video prompt"

## Prerequisites

- Access to the Jimeng Seedance 2.0 platform (ByteDance).
- Know your input assets: image count, video count, audio count.

## Input Constraints

| Input | Limit | Format | Max Size |
|---|---|---|---|
| Images | ≤ 9 | jpeg, png, webp, bmp, tiff, gif | 30 MB each |
| Videos | ≤ 3 | mp4, mov | 50 MB each, 2–15s total |
| Audio | ≤ 3 | mp3, wav | 15 MB each, ≤ 15s total |
| Total files | ≤ 12 combined | — | — |

- Output: 4–15s video, 480p–720p, with auto-generated sound effects / BGM.
- **No realistic human faces** in uploaded images/videos — platform blocks them.
- Video references cost slightly more than image-only.

## How to Run

Load this skill with `skill_view(name='seedance-video-prompts')`, then draft prompts interactively. Walk through the procedure below, ask the user what assets they have, and output the final prompt text.

## Quick Reference

### @ Reference Syntax

```
@Image1 as the first frame
@Image2's character as the subject
scene references @Image3
reference @Video1's camera movement
completely reference @Video1's effects and transitions
BGM references @Audio1
sound effects reference @Video3's audio
product details reference @Image3
wearing the outfit from @Image2
```

Every uploaded asset **must** have an explicit role. Never leave an `@ImageN` or `@VideoN` floating without purpose.

### Prompt Formula

```
[Subject/Character] + [Scene] + [Action/Motion] + [Camera Movement] +
[Timing Breakdown] + [Transitions/Effects] + [Audio Direction] + [Style/Mood]
```

### Camera Vocabulary

**Movements:** push in, pull back, pan left/right, tilt up/down, track/follow shot, orbit/revolve, one-take/oner.
**Advanced:** Hitchcock zoom (dolly zoom), fisheye lens, low angle, high angle, bird's eye/overhead, first-person POV, whip pan, crane shot.
**Shot sizes:** extreme close-up, close-up, medium close-up, medium shot, full shot, wide/establishing shot.

### Style Modifiers

**Visual:** `Cinematic quality, film grain, shallow depth of field`, `2.35:1 widescreen, 24fps`, `Ink wash painting style`, `Anime style`, `Photorealistic`, `4K medical CGI`.
**Mood:** `Tense and suspenseful`, `Warm and healing`, `Comedy with exaggerated expressions`.
**Audio:** `Background music: grand and majestic`, `Sound effects: footsteps, crowd noise`, `Beat-synced transitions matching music rhythm`.

## Procedure

### 1. Clarify the Goal

Ask: What type of video? (ad, short drama, music video, educational, vlog, dance, product showcase, scenery montage). Target duration?

### 2. Inventory Assets

Ask the user to list their images, videos, and audio files. Map each to a numbered `@` reference.

### 3. Assign Roles

For every asset, decide its purpose. Use the Quick Reference table above. Common assignments:

- **Character consistency:** `@Image1's character as the subject`
- **Camera replication:** `reference @Video1's camera movement`
- **Effects replication:** `completely reference @Video1's effects and transitions`
- **Scene/background:** `scene references @Image3`
- **Audio:** `BGM references @Audio1`
- **First/last frame:** `@Image1 as the first frame`

### 4. Structure the Prompt

Open with subject + scene setup. For videos > 8s, use time-segmented blocks:

```
0–3s: [opening scene, camera, action]
3–6s: [mid-section development]
6–10s: [climax or key action]
10–15s: [resolution, ending shot]
```

Then layer in camera movements, audio direction, and style modifiers.

### 5. Validate Constraints

- Total files ≤ 12.
- No realistic human faces described in uploads.
- Duration matches generation length selection.
- Every `@` reference has an explicit role — no dangling references.

### 6. Deliver the Prompt

Output the final prompt text. Briefly explain key structural choices.

## Capability Patterns

### Camera Replication

```
Reference @Image1's male character. He is in @Image2's elevator.
Completely reference @Video1's camera movements and the protagonist's
facial expressions. Hitchcock zoom during the fear moment, orbit shots
showing the elevator interior. Follow shot walking out.
```

### Effects Replication

```
Replace @Video1's character with @Image1. @Image1 as the first frame.
Reference @Video1's camera work — close orbit shot transitions from
third-person to character's subjective POV.
```

### Video Extension

```
Extend @Video1 by 15 seconds.
0–5s: [new opening content]
6–10s: [mid-section]
11–15s: [closing with branding/text]
```

When extending, set generation duration to match extension length. For reverse extension (prepending), use `Extend backward 10s.`.

### Video Editing (Plot Subversion)

```
Subvert @Video1's plot — [describe altered action, dialogue, expressions].
```

### Music Beat-Matching

```
@Image1 @Image2 @Image3 — match keyframe positions and overall rhythm
of @Video1 for beat-synced cuts. Characters should have more dynamic
movement. Visual style more dreamlike with strong visual tension.
```

### One-Take / Long Take

```
@Image1 @Image2 @Image3 — one-take tracking shot, following [subject]
from [location A] to [location B]. No cuts throughout.
```

### E-commerce / Product Showcase

```
Deconstruct the reference image. Static camera. Product suspended and
rotating mid-air. Ingredients/components gently separate while maintaining
shape. Smooth motion, no extra effects.
```

### Educational / Science

```
15-second [topic] clip.
0–5s: [context/visualization setup]
5–10s: [process/mechanism shown]
10–15s: [outcome/comparison, colors darken]
```

## Pitfalls

- **Vague references:** "reference @Video1" without specifying what (camera? action? rhythm?) produces poor results. Always qualify.
- **Conflicting directions:** "static camera" + "orbit shot" in same segment = contradictory.
- **Overloading:** Packing too many scene changes into 4–5s looks physically impossible.
- **Dangling assets:** Uploading 5 images but only referencing 3 — the model ignores the unused ones or misuses them.
- **Ignoring audio:** Sound design is auto-generated and improves with direction. Always include BGM/sound effect guidance.
- **Real faces:** Uploading real human photos triggers platform rejection.
- **Duration mismatch:** A 15-second prompt complexity selected for 4s generation will be truncated poorly.

## Verification

After drafting, run this mental checklist:

1. Every uploaded asset has an explicit `@` role assignment.
2. No segment under 2 seconds tries to cram multiple scene changes.
3. Camera directions are consistent within each segment.
4. Audio direction is present (BGM, sound effects, or voice tone).
5. Duration matches the planned generation length.
6. No real human faces in described assets.
7. Total file count ≤ 12.