---
name: video-postproduction
description: Assemble generated video segments, preserve and join audio, remove fixed overlays or watermarks with mask-based cleanup, and verify the final MP4 visually and technically.
version: 1.6.0
---

# Video Post-Production

Use this skill when the user asks to join two or more video segments, continue a generated clip, remove a fixed watermark/overlay, preserve audio, or deliver a verified final MP4.

This is a post-production skill, not a generation skill: it starts from local video assets and ends with a playable, inspected deliverable.

## Always-on rules

- Work from the actual completed media files, not a pending browser preview or a guessed asset ID.
- Preserve the source framing and resolution unless the user explicitly asks for a crop or resize.
- Prefer a localized mask-based cleanup over a broad crop when a fixed overlay is small and the surrounding image can be reconstructed.
- Keep audio explicit in the filter graph; never let a video-only filter silently drop the soundtrack.
- Technical metadata is necessary but insufficient: inspect decoded frames at the seam and at the former overlay location.
- If removal would damage important content, state the trade-off instead of pretending the result is perfect.
- A technically valid concat is not automatically a commercial edit: for an ad/premium brief, creative coherence is a release criterion.
- Verify each candidate by decoded start, middle, and end frames, and keep an explicit role → path mapping.
- Run `ffprobe` on every selected input and confirm duration, resolution, frame rate, codecs, frame count, and audio presence.
- Reject HTML/error downloads and incomplete/pending candidates.
- Re-encode video when a filter is applied; do not claim a stream copy preserved filtered frames.
- Run `ffprobe -count_frames` and a full `ffmpeg -loglevel error -f null` decode.
- If the brief contains exact spoken copy, treat script compliance as a separate release gate: preserve one canonical script, transcribe the generated audio from the actual delivered file (not the prompt or generation UI), normalize harmless punctuation/diacritics, and compare the ordered transcript across clip boundaries.
- If ASR is unavailable or the transcript is missing/mismatched, report the video as script-unverified/non-compliant and do not deliver it as final; use deterministic TTS or regenerate as appropriate.
- Only report success after the file decodes without errors, metadata matches the requested format, audio is present and measured on both halves, any exact spoken script is verified against the actual audio, the ordered subject roles match the brief, the seam is acceptable, and the overlay is absent in decoded frames.

## Operating principles

- Work from the actual completed media files, not a pending browser preview or a guessed asset ID.
- Preserve the source framing and resolution unless the user explicitly asks for a crop or resize.
- Prefer a localized mask-based cleanup over a broad crop when a fixed overlay is small and the surrounding image can be reconstructed.
- Keep audio explicit in the filter graph; never let a video-only filter silently drop the soundtrack.
- Technical metadata is necessary but insufficient: inspect decoded frames at the seam and at the former overlay location.
- If removal would damage important content, state the trade-off instead of pretending the result is perfect.
- A technically valid concat is not automatically a commercial edit: for an ad/premium brief, creative coherence is a release criterion.

## References (read with skill_read(name, file_path=...))

- `references/assembly-and-delivery-workflow.md` — Read for the full procedure for selecting and probing clips, cleaning overlays, joining video and audio, and verifying the rendered master.
- `references/autonomous-media-agent-integration-audit.md` — Read when wiring or auditing an autonomous media agent’s runtime, asynchronous rendering, QA, correction, and release path.
- `references/branded-overlays-and-dialogue-music.md` — Read for the premium-ad creative gate, verified end cards, logo placement, dialogue-led music, or a music-only revision.
- `references/google-flow-assembly-cleanup.md` — Read for the validated Google Flow 720×1280 mask-and-concat recipe or to troubleshoot asset selection, seams, overlays, subtitles, branding, audio, and duration.
- `references/numbered-client-brief-voiceover-broll.md` — Read when resolving a numbered client deliverable or building a voice-over variant with compliant B-roll and a narration-timed end card.
- `references/script-compliance-and-fallback.md` — Read when exact spoken copy is required, ASR is unavailable or finds a mismatch, or generated logos and text need glyph-level cleanup.
- `references/short-form-ad-audio-revision.md` — Read when correcting rushed narration or an unpleasant music bed while preserving picture timing, caption sync, and exact duration.
- `references/word-synchronised-highlight-subtitles.md` — Read when building or verifying active-word subtitles from actual audio, including master-timeline offsets, ASS layout, and unchanged-audio checks.
