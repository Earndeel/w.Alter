---
name: video-postproduction
description: Assemble generated video segments, preserve and join audio, remove fixed overlays or watermarks with mask-based cleanup, and verify the final MP4 visually and technically.
version: 1.6.0
---

# Video Post-Production

Use this skill when the user asks to join two or more video segments, continue a generated clip, remove a fixed watermark/overlay, preserve audio, or deliver a verified final MP4.

This is a post-production skill, not a generation skill: it starts from local video assets and ends with a playable, inspected deliverable.

## Operating principles

- Work from the actual completed media files, not a pending browser preview or a guessed asset ID.
- Preserve the source framing and resolution unless the user explicitly asks for a crop or resize.
- Prefer a localized mask-based cleanup over a broad crop when a fixed overlay is small and the surrounding image can be reconstructed.
- Keep audio explicit in the filter graph; never let a video-only filter silently drop the soundtrack.
- Technical metadata is necessary but insufficient: inspect decoded frames at the seam and at the former overlay location.
- If removal would damage important content, state the trade-off instead of pretending the result is perfect.
- A technically valid concat is not automatically a commercial edit: for an ad/premium brief, creative coherence is a release criterion.

## Autonomous media-agent integration gate

When evaluating or wiring this workflow into an autonomous agent, distinguish six capabilities instead of treating “AI video agent” as one feature:

1. **Reasoning and planning** — can turn a brief into shots, clip roles, a timeline, and constraints.
2. **Provider generation** — can submit, poll, and reconcile independent image/video/audio jobs.
3. **Post-production execution** — exposes a callable tool whose handler reaches a runtime that can actually run FFmpeg or an equivalent renderer.
4. **Post-render QA** — propagates the completed output URL into real technical, visual, audio, and brief-compliance checks.
5. **Correction routing** — converts failed QA into a bounded retry of the exact generation or edit stage that caused the defect.
6. **Release sequencing** — delivers only after QA passes or an explicit human override/approval is recorded.

Never infer capabilities 3–6 from workflow labels, prompt text, documentation, or the mere presence of FFmpeg on another machine. Trace the complete runtime path: **tool schema → model exposure → dispatcher → handler → execution runtime → persisted artifact → async callback/resume → QA decision → delivery**. For edge runtimes that cannot spawn FFmpeg, use an authenticated media-worker/sidecar job API; a binary installed on an operator host is not automatically available to the agent.

The safe asynchronous order is: **provider completes → persist canonical outputs → enqueue assembly/post-production → probe and inspect rendered master → correct or request approval → deliver**. Sending provider output directly from its webhook before QA defeats the quality gate, even if a later workflow step is named `final_quality_control`.

See `references/autonomous-media-agent-integration-audit.md` for a dated capability-audit pattern, evidence checklist, media-worker contract, and acceptance tests.

## Premium-ad creative gate

When the user asks for a qualified advertisement, do not start by concatenating the requested role labels. First audit the available media as a visual set:

1. Build a contact sheet for every candidate with start, midpoints, last frame, and (for 10-second clips) roughly 0/2.5/5/7.5/last seconds. Score shot variety, product visibility, camera language, lighting, presenter continuity, and end-frame usability.
2. Do not mix a cinematic/generated product sequence with raw selfie/UGC footage merely because the subjects are different or the brief says `farmer + woman`. That creates a visibly amateur seam. Prefer a coherent same-presenter pair when the available assets make that the only commercial-looking option; otherwise report the trade-off and identify the missing bridge/regenerated shot needed to honor the subject change.
3. Treat provider-generated typography, logos, legal/certification claims, URLs, and end cards as untrusted image content. Never ship malformed generated text or invented claims. Replace the end card with deterministic typography/layout (Pillow, Remotion, or FFmpeg drawtext) using only verified copy supplied by the brief.
4. Wrap and size every end-card line for the actual 720×1280 canvas. Inspect the full-resolution card, not only a thumbnail, for right-edge clipping, CTA overflow, accent/diacritic errors, contrast, and safe margins.
5. Use an intentional transition grammar (hard cut, short fade-to-black, or a justified crossfade) instead of an accidental seam. If `xfade` is used, normalize every video input to the same frame rate and timebase first (`fps=24,settb=1/24` is a safe pattern for the common Flow exports).
6. Calculate video and audio durations independently. A crossfade reduces the sum by its duration; pad/fade the audio explicitly (`apad` + `atrim`) so the audio stream ends exactly with the video, including the final card.

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

## Known pitfalls

- **Pending asset confusion:** the first media URL seen in a rendering card may be a preview/progress asset, not the completed file.
- **Role mismatch:** a valid 20-second MP4 can still be wrong if the selected pair ignores the brief (for example, all-woman output when the requested order is farmer then woman); label and visually verify each input before concat.
- **Shape mismatch:** a broad rectangular mask may remove the provider sparkle but visibly smooth a jacket and erase a zipper; prefer the previously validated silhouette mask when the overlay geometry matches.
- **Mask too tight:** antialiased white edges remain visible; expand the mask slightly and recheck.
- **Mask too wide:** a broad reconstruction can create a visible rectangular blur or remove a zipper/seam; use the smallest shape-aware mask that fully covers the halo.
- **Audio loss:** a video-only concat or incorrect `-map` drops narration/music; map the concatenated audio stream explicitly.
- **Metadata-only QA:** `ffprobe` cannot prove watermark removal or visual continuity; decoded-frame inspection is mandatory.
- **Audio tail mismatch:** `acrossfade` shortens the combined audio by the crossfade duration; pad and trim it to the requested final duration, then probe the audio stream separately (not only `format.duration`).
- **End-card clipping:** a thumbnail can hide right-edge clipping; inspect the generated 720×1280 end-card at native/full resolution and keep copy within an explicit safe rectangle.
- **Forced-line subtitle overflow:** ASS margins do not automatically rewrap text around explicit `\\N` breaks. Measure every rendered line separately with the actual font, size, and bold weight; enforce a pixel-width assertion against the safe rectangle, then inspect one midpoint frame for every subtitle event before delivery.
- **Creative mismatch:** a role-correct farmer/woman pair can still look like two unrelated videos. Do not present a raw selfie continuation as premium without a visual bridge, consistent grade, or a deliberate design treatment.
- **Generated claims:** provider-rendered certification seals, legal copy, URLs, and brand text can be malformed or fabricated; rebuild them from verified text or remove them.
- **Timebase mismatch:** `xfade` fails when inputs retain different timebases (for example, encoded Flow media versus a 25-fps PNG loop); apply matching `fps` and `settb` to every xfade input.
- **Sample-aspect-ratio mismatch:** FFmpeg `concat` can reject streams with identical pixel dimensions when one branch retains an odd SAR (for example, a near-9:16 source after crop) and another reports square or undefined pixels. Apply `setsar=1` after every scale/crop branch, before concat, and normalize frame rate/pixel format at the same point.
- **Embedded-caption reuse:** a reused source segment may already contain burned-in karaoke captions. Adding the master subtitle layer creates duplicates; suppressing it is safe only when the embedded phrase and word timing match the new narration exactly. Otherwise use a clean source or mask/rebuild the embedded text, and probe the segment’s last 0.10–0.25 s so the next source sentence does not appear before the cut.
- **Single-word pseudo-highlights:** colouring an isolated one-word caption is not meaningful karaoke highlighting. Keep contextual chunks, then reduce only when measured pixel width demands it.
- **Subtitle offset drift:** word timestamps from clip B are relative to B; add the exact master offset before building ASS events and sample known words after rendering.
- **French clitic splitting:** merge ASR tokens such as `d` + `'agriculteurs` and `l` + `'air` so one spoken word does not flash twice.
- **ASS colour inversion or audio mutation:** ASS uses `&HAABBGGRR&`, and subtitle rendering should not alter audio. Use `-c:a copy` and compare decoded-audio MD5 values when no audio processing is requested.
- **Transparent-canvas scaling:** an RGBA logo may have large transparent margins or low-alpha dust. Threshold only negligible alpha, crop to the real content, then scale and inspect on decoded frames.
- **Brand collision on the end card:** persistence is not a virtue when it covers an existing campaign header or CTA. Disable or relocate the added logo at the scene transition and verify frames on both sides of the boundary.
- **One subtitle position for every scene:** a safe lower-third margin on presenter footage may cover end-card copy. Keep the campaign style but switch to a second timed ASS style in a verified empty band.
- **False MD5 failure after mixing:** music, gain, ducking, fades, limiting, and AAC encoding intentionally change audio. Use segment-level loudness and peak checks; reserve MD5 equality for unchanged audio-copy paths.
- **Single-word TTS pronunciation error:** prefer regenerating the complete sentence or full voice track with an explicit phonetic cue, especially for client masters. Never layer a replacement token over the original voice: that creates doubled attacks and audible overlap. A pre/replacement/post concat is acceptable only when the token has clean isolated boundaries and the result passes listening QA; otherwise regenerate. Verify that the final filter graph maps exactly one voice source, then check the disputed sound with ASR and, for `/s/`, high-frequency/fricative energy.
- **Dirty branding from frame extraction:** never rebuild a logo vignette from a composited video-frame crop while the original asset may exist. Search prior artifacts first, prefer the original RGBA/alpha PNG, inspect alpha edges on several backgrounds, and for visual-only revisions remux the previously approved audio with `-c copy`; verify identical audio stream MD5 before delivery.
- **Global-only mix QA:** a full-program mean can hide music that is inaudible in gaps or too loud under speech. Measure intro, speech, pause, and outro separately, then listen when playback is available.
- **Phase-cancel bed shipped as music:** center cancellation can leave hollow, swirly, or metallic residuals even when LUFS and peaks look normal. Treat it as a diagnostic stem; replace it with a clean bed or remove it, then audition the actual encoded master.
- **Speed-stack narration:** high TTS rate plus `atempo` can satisfy duration while making delivery visibly rushed. Reduce copy or extend the master, regenerate the full voice, and rebuild timings rather than applying another corrective stretch.
- **Container-duration false pass:** audio can hold `format.duration` at the target while video ends early because a source clip was shorter than its assigned trim or `overlay=shortest=1` propagated the short branch. Require video-stream duration and expected `nb_frames`, not container duration alone.
- **Numbered-deliverable ambiguity:** “the last video” in a client pack may mean the highest numbered brief, not the most recently edited local master. Resolve the numbered deliverable and canonical script from the named client source before acting.
- **Low-cadence storyboard blind spots:** 1 fps contact sheets can miss sub-second presenter flashes at generated scene boundaries. For presenter-free voice-over work, inspect source trim points at 0.10–0.25 s increments and verify the assembled master at 4 fps.
- **Voice-over role contamination:** a technically clean B-roll segment may contain one or two transition frames with a talking presenter. Move the trim boundary to the first safe frame and retime clean detail footage instead of accepting the contamination.

See `references/google-flow-assembly-cleanup.md` for the validated Google Flow 720×1280 mask/concat recipe and the provider-specific asset-selection pitfalls.

See `references/script-compliance-and-fallback.md` for the exact spoken-copy release gate, the audio-copy versus lip-sync decision matrix, ASR evidence requirements, deterministic TTS fallback rules, and glyph-level cleanup for hallucinated logos/text.
