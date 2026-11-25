## Workflow

### 1. Resolve creative asset roles before probing

Map the brief to ordered roles before trusting filenames or the latest generated prompt: for example, `0–10 s = agriculteur` and `10–20 s = femme`. Verify each candidate by decoded start, middle, and end frames, and keep an explicit role → path mapping. A file named `continuation` may have been generated from a reference clip and must not automatically become the first half. Reject an all-one-subject montage when the brief requires a subject change. Then run `ffprobe` on every selected input and confirm duration, resolution, frame rate, codecs, frame count, and audio presence. Reject HTML/error downloads and incomplete/pending candidates.

Generated web apps may expose a preview/media ID while a job is still rendering and a different completed asset afterward. Re-scan the completed card/result before downloading the final candidate.

### 2. Inspect representative frames

Extract first, last, and middle frames from each input. Check:

- continuity of subject, clothing, camera framing, lighting, and background;
- the intended product/panel/action shot;
- whether the overlay is fixed in screen coordinates or follows the subject;
- the cleanest local background for reconstruction.

For two segments, inspect the last frame of A and the first frame of B side by side before concatenation.

### 3. Choose the least destructive overlay cleanup

For a small fixed overlay:

1. Prefer a shape-aware grayscale mask that follows the overlay silhouette plus a small antialiased halo; do not default to a broad rectangle over textured clothing, seams, zippers, hands, or foliage.
2. Apply FFmpeg `removelogo` with the mask and inspect enlarged crops from every selected role. Reuse a previously validated clean mask/recipe when the provider overlay and framing match; do not silently substitute a coarser rectangle.
3. Expand the mask only until the full halo disappears. A rectangle can remove the sparkle while leaving a visible smooth patch; a precise star/diamond mask usually preserves surrounding fabric detail better.
4. Use a crop only when reconstruction is visibly worse and the user accepts the framing change.

Do not assume all FFmpeg builds expose the same `delogo` options. Check `ffmpeg -h filter=delogo`; a missing option is a syntax/version issue to work around, not a reason to stop.

For complex or moving overlays, use a real frame-wise inpainting/patch workflow and inspect temporal stability; a single static patch can swim or freeze against moving content.

### 4. Concatenate video and audio explicitly

Normalize timestamps with `setpts=PTS-STARTPTS` and `asetpts=PTS-STARTPTS`, apply the cleanup filter to each video stream, then use the `concat` filter with `n=<segment_count>:v=1:a=1`. Map both resulting streams explicitly.

A reliable delivery encode is H.264 (`libx264`, CRF 18–20, `yuv420p`) plus AAC audio, with `-movflags +faststart` for browser/mobile playback. Re-encode video when a filter is applied; do not claim a stream copy preserved filtered frames.

### 4a. Add word-synchronised highlight subtitles when requested

Treat active-word subtitles as a deterministic timing task, not a decorative text animation. Transcribe the actual delivered audio with word timestamps, add each concatenated clip's master-timeline offset, merge ASR-split French clitics such as `d` + `'agriculteurs`, and generate ASS events where only the currently spoken word changes colour.

Use `scripts/build_word_highlight_ass.py` rather than hand-authoring dozens of events. Keep 4–5 words of context when possible, measure the real font width, cap blocks at two lines, and preserve silent gaps. Burn the ASS file into a separate MP4 with `-c:a copy`; verify representative active words, a 1 fps full-timeline contact sheet, and matching decoded-audio MD5 values. See `references/word-synchronised-highlight-subtitles.md` for the full recipe, colour format, offsets, and QA gates.

### 4b. Add branding and a light music bed without damaging the end card

Before scaling a supplied RGBA logo, remove negligible alpha dust and crop to the real alpha content; otherwise transparent margins make the mark undersized and stray pixels may appear over video. Test the cleaned overlay at full resolution on several backgrounds, using a subtle contrast plate only when the artwork needs it.

Audit the last seconds separately. If the end card already owns the logo's usual region, disable or relocate the added mark at the designed transition rather than covering campaign branding. Add a second ASS style with a different vertical margin when the final spoken sentence overlaps an occupied CTA/end-card layout, while preserving the same font, outline, colours, and active-word behavior.

For a subtle dialogue-led music mix, render or select a licensed bed at the master sample rate and duration, keep it well below speech, and sidechain-compress it from the original voice track so it returns naturally in pauses. Re-encode audio when mixing, measure intro/speech/gap/outro separately, and retain peak headroom. Decoded-audio MD5 equality applies only to intentionally unchanged audio; it must not be used as a success criterion after music, gain, ducking, fades, or limiting.

When the approved master is already voice-only and the requested revision is **music only**, use the approved MP4 as the source of truth: stream-copy its video and rebuild only the audio (`-c:v copy`). Do not rerun the visual assembly/upscale, which wastes time and can introduce needless visual drift. Verify the copied video stream independently, and re-run ASR on the final mix to prove the bed did not mask words.

See `references/branded-overlays-and-dialogue-music.md` for the full overlay, end-card, ASS, audio-only fast path, filter-graph, and QA recipe.

### 4c. Build a numbered voice-over variant from a client pack

When the request names a numbered deliverable (`video 3`, `last video for <client>`, etc.), resolve the number and exact script from the named client’s direct brief or conversation before choosing local assets. Do not infer that “last” means the most recently edited file; campaign similarity is not identity.

For a voice-over variant, inventory approved clean footage by visual function, then assemble only compliant B-roll. Measure the exact rendered narration at a natural speaking rate before locking the master duration. If exact copy does not fit naturally, do not force it with aggressive TTS rate or time compression: extend the master unless duration is a hard delivery constraint, or shorten the script only with approval.

Align the end-card start to the actual first CTA word in the rendered narration, retime a static card to fill the remaining duration when needed, and disable any added corner logo that collides with the card. Keep the CTA visually exclusive: one promise, one primary action, no duplicate subtitle copy, and no competing paragraphs or badges. If spoken CTA accessibility captions are required, place a minimal non-duplicative line in a verified empty band rather than reproducing the full call to action over the card.

A 1 fps storyboard can miss 0.1–0.3 second presenter transitions at trim boundaries. Probe source boundaries every 0.10–0.25 s, trim to the first fully safe frame, and stretch a clean detail shot slightly rather than exposing an unwanted face/body. Finish with a full-program 4 fps contact sheet when the brief requires presenter-free B-roll. See `references/numbered-client-brief-voiceover-broll.md` for the full source-resolution, narration-fitting, end-card, mixing, and QA recipe.

### 4d. Correct rushed narration or an unpleasant background

Treat user feedback about noisy/phasey audio or rushed speech as a release failure even when decode, ASR, and loudness checks pass. Technical audio metrics cannot establish listening quality.

1. Solo voice, bed, and combined mix before applying any restoration. Center-cancel, karaoke, and phase-inversion extractions are diagnostic/emergency stems, not release-ready music beds; replace a defective bed with a clean licensed/generated instrumental or deliver voice-only.
2. If narration is too fast, fix copy length before processing speed. Do not stack an aggressive TTS rate with `atempo` to force a long script into a hard duration. Regenerate the complete voice at a natural rate, then rebuild word timestamps from that rendered file.
3. Re-time picture beats and deterministic captions to the new words. Price, aid, benefit, offer, and CTA visuals must occur with their spoken claims; changing audio alone is incomplete.
4. Probe every source clip before assigning a target segment duration. If a mostly static clean clip is shorter than its slot, use deliberate `setpts=(target/available)*(PTS-STARTPTS)` and inspect the motion; regenerate rather than heavily stretching people or expressive action.
5. Verify video-stream duration and frame count independently of `format.duration`. A 15-second audio stream can hide a shorter video stream, especially after `overlay=shortest=1`. Pad only rounding-frame gaps with `tpad`, trim to the target, and require the expected frame count.
6. Audition opening, dialogue, pauses, and ending in addition to measuring LUFS/peak, pause noise, ASR, and subtitle sync. Never label subjective audio PASS from meters alone.

For a validated correction recipe, pace baselines, clean voice-only graph, exact-duration trap, and release commands, see `references/short-form-ad-audio-revision.md`.

### 5. Verify the deliverable

Run:

```bash
ffmpeg -hide_banner -loglevel error -i final.mp4 -f null -
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames \
  -of json final.mp4
```

Then create a storyboard with:

- the role-labeled end of segment A and the role-labeled first frame of segment B;
- the first 1–2 frames of segment B at native cadence, checking for a white card, black frame, duplicate, or morphing defect;
- one or more middle action/product frames;
- the final frame;
- enlarged crops of the former overlay area at the start, seam, and end.

For an exact two-by-ten-second delivery, trim or encode each source to `10.000` seconds before concat, then verify the final duration. Filter concat can introduce timestamp rounding (for example `20.010` seconds); if the brief requires exactly 20 seconds, trim both streams after concat with `trim=duration=20,setpts=PTS-STARTPTS` and `atrim=duration=20,asetpts=PTS-STARTPTS`, then re-probe.

Run `ffprobe -count_frames` and a full `ffmpeg -loglevel error -f null` decode. Probe the audio stream independently and measure each half with `volumedetect` or `astats`; nonzero samples and comparable levels are a useful guard against a silently dropped or broken soundtrack. If Monsieur explicitly supplies a `delogo` rectangle, honor that requested recipe but inspect an enlarged before/after crop and disclose any localized smoothing; otherwise prefer the smallest shape-aware mask.

If the brief contains exact spoken copy, treat script compliance as a separate release gate: preserve one canonical script, transcribe the generated audio from the actual delivered file (not the prompt or generation UI), normalize harmless punctuation/diacritics, and compare the ordered transcript across clip boundaries. A prompt containing the script is not evidence that the provider rendered it. If ASR is unavailable or the transcript is missing/mismatched, report the video as script-unverified/non-compliant and do not deliver it as final; use deterministic TTS or regenerate as appropriate.

Only report success after the file decodes without errors, metadata matches the requested format, audio is present and measured on both halves, any exact spoken script is verified against the actual audio, the ordered subject roles match the brief, the seam is acceptable, and the overlay is absent in decoded frames.
