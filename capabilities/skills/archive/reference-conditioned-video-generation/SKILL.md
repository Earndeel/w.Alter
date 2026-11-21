---
name: reference-conditioned-video-generation
description: Use for videos from character/environment reference sheets.
---

# Reference-conditioned video generation

Use this skill when a user supplies character sheets, environment boards, or reference images and asks for a short cinematic video that preserves identity across multiple shots. The workflow is provider-agnostic, with concrete guidance for native FLUX 3 / BFL image-to-video jobs.

## Core principle

Reference sheets are **identity and design references**, not timeline frames. A model sheet contains labels, swatches, pose studies, and typography that must not appear in the finished clip. Separate the reference-conditioning stage from the video timeline:

```text
reference sheets -> clean cinematic anchor image -> image-to-video -> exact-duration master -> technical + visual QA
```

## Workflow

1. **Inventory the references.** Identify which image is environment, which images are characters, and which visual markers are load-bearing: silhouette, face geometry, hair, costume colors, tattoos, props, footwear, and lighting palette. Do not assume the upload order; inspect the images.
2. **Create a clean anchor frame.** Use an image-generation/editing model with all references attached and an explicit negative instruction: do not reproduce the reference board, labels, names, diagrams, color swatches, typography, or page layout. Compose the intended opening shot with the required characters in the actual environment.
3. **Inspect the anchor before spending video credits.** Confirm the requested number of characters, recognizable identity markers, full-body usability when the shot list needs it, correct environment, no text/watermark, and no extra person or duplicated anatomy.
4. **Preserve the user's prompt.** If the user says “keep everything” or asks to add time, retain the original shot list, camera, style, and audio text verbatim. Append a clearly labelled timed extension block instead of rewriting the earlier prompt. Start the extension from the final pose of the original timeline; never restart the scene at the extension boundary.
5. **Resolve early final-frame contradictions.** If the original prompt says “final frame,” “bass drop,” or “near-silence” at the old end time, add a continuity note that moves only that final-tail timing to the true end while preserving the other audio and visual instructions.
6. **Submit one native I2V job.** Animate the clean anchor with the requested whole-second duration, aspect ratio, resolution, and audio setting. Do not pass character sheets to a keyframe/storyboard API unless the user explicitly wants those sheets shown as frames; pinned keyframes are not reference-only conditioning.
7. **Poll by job ID.** Reuse the submitted job ID until it is ready or fails. Do not resubmit merely because the provider is still rendering. Save the returned artifact locally and deliver the saved path, not a speculative URL.
8. **Normalize the master.** FLUX 3's native 720p “16:9” result may measure 1280×704. If strict 16:9 is required, trim to the requested duration and pad equally to 1280×720 with `setsar=1`; do not stretch the artwork. Preserve or re-encode audio as required for exact trimming.
9. **Perform artifact QA.** Check `ffprobe` metadata, full decode, audio presence and levels, a full 1-fps storyboard, and a higher-rate storyboard of the appended interval. Use scene detection as a diagnostic, not as proof that the model obeyed the shot list. Distinguish **N shots = N−1 transitions** when reporting cut counts.
10. **Deliver concisely.** Include the native file-delivery marker with the verified absolute MP4 path and only the essential verified specs/caveats.

## Extension design rules

- Preserve the original timeline boundaries and add the new seconds after the existing ending.
- State the exact start pose and camera continuity at the boundary.
- Keep character identities, environment, palette, style, and choreography constraints explicit in the extension.
- For action, specify readable cause-and-effect: advance, evade/block, counter, recovery/reset.
- Keep impacts non-graphic unless the user explicitly requests otherwise; avoid introducing weapons or extras absent from the original prompt.
- Extend audio elements through the new interval and reserve the final impact/silence for the actual end.

## Verification checklist

- [ ] Final duration equals the requested duration, not merely “about” it.
- [ ] Final dimensions and sample aspect ratio are mathematically the requested ratio.
- [ ] Video and audio decode without errors.
- [ ] The anchor identity markers survive close-ups, motion blur, and the extension.
- [ ] No reference-board residue, labels, subtitles, logos, watermarks, extra characters, or accidental weapons.
- [ ] The requested extension is visibly present in its own storyboard.
- [ ] Cut reporting distinguishes prompt intent, sampled shots, and measured hard transitions.

## Support reference

See `references/reference-conditioned-20s-qa.md` for the reusable anchor prompt pattern, timed-extension template, provider-shape notes, and FFmpeg/ffprobe verification recipe.

## Pitfalls

- Passing a character sheet directly as a keyframe can burn the sheet into the clip.
- Calling a prompt “20 cuts” does not prove the model produced 20 cuts; inspect the rendered result.
- A provider's aspect-ratio label is not a substitute for checking width, height, and SAR.
- Padding is preferable to stretching when identity geometry matters.
- A successful job submission is not a successful deliverable until the returned file is saved and decoded.
