# Complete Video-Ad Review Reference

Use this reference for a finished vertical or social video when the request is to review the whole asset, not merely validate that a provider returned an MP4.

## Evidence-first sequence

1. Preserve the original and work on a separate review/output copy. Record `stat`, duration, and a SHA-256 hash before and after any transfer.
2. Run a technical probe with `ffprobe`: container, duration, video/audio streams, codec, profile, dimensions, frame rate, frame count, sample rate, channels, and bit rate.
3. Run FFmpeg checks for black frames and freezes, scene-cut timestamps, and audio loudness/true peak. A valid stream is not proof of a usable ad.
4. Review the entire timeline visually. Extract frames at about 2 fps into a labelled contact sheet, then create a second contact sheet for the bottom-right watermark zone.
5. Inspect the final 1–3 seconds separately at about 10 fps or 0.1-second intervals. Render a high-resolution crop of the end-card text and logos; small contact-sheet thumbnails are insufficient for typography QA.
6. If the file was retouched, build original-vs-edited crops at several timestamps where the background moves, where a hand crosses the mask, and immediately before the end-card transition.

## Technical probe examples

```bash
ffprobe -v error \
  -show_entries format=filename,format_name,duration,size,bit_rate:\
stream=index,codec_type,codec_name,profile,width,height,r_frame_rate,\
avg_frame_rate,nb_frames,duration,bit_rate,sample_rate,channels,channel_layout \
  -of json input.mp4

ffmpeg -hide_banner -i input.mp4 \
  -vf "blackdetect=d=0.10:pix_th=0.10,freezedetect=n=-60dB:d=0.5" \
  -an -f null - 2>&1 | grep -E 'black_start|black_end|freeze_start|freeze_end'

ffmpeg -hide_banner -i input.mp4 \
  -af loudnorm=print_format=json -f null - 2>&1

ffmpeg -hide_banner -i input.mp4 \
  -filter_complex "select='gt(scene,0.25)',showinfo" \
  -an -f null - 2>&1 | grep -o 'pts_time:[0-9.]*'
```

Treat audio and video duration separately. A few milliseconds of audio tail is normal, but a missing audio stream, clipping, or a long silent tail should be reported.

## Complete multimodal analysis

Before using a model, query `https://openrouter.ai/api/v1/models` and select an exact current model ID whose architecture declares video (or the provider's documented video-file modality). Do not copy a stale skill/model constant. Save the selected model, response ID, elapsed time, token usage, and actual cost in run metadata without exposing credentials.

Use a separate system message for the analysis rubric and a user message containing the video plus the task. The rubric should require:

- chronological scene boundaries and shot changes;
- visible action, camera, lighting, continuity, and generation defects;
- dialogue/voiceover/music observations without invented transcription;
- all on-screen text, captions, logos, fixed watermarks, and UI marks as separate fields;
- an ad evaluation covering hook, offer clarity, proof, CTA, pacing, brand recall, platform fit, and blockers;
- a specific audit of the final card and the requested brand/legal wording.

For files small enough for base64, use a `data:video/mp4;base64,...` `video_url`; for larger files use an approved HTTPS URL. Save the raw API response before normalization. Some models return a JSON object inside a Markdown code fence despite a JSON-only instruction: remove only the outer fence, parse the normalized content, and validate required keys. Never treat a prose response as valid structured analysis.

Use the model as a semantic aid, not as the sole evidence for typography, logos, or watermark removal. Verify questionable OCR against high-resolution crops and mark uncertain characters as `[unclear]` instead of silently correcting them.

## Watermark/removal audit

Fixed provider marks and scene-generated branding are different objects. If a user-owned/generated video needs a fixed mark removed, use a separate mask and a time gate when a legitimate scene logo appears later, for example:

```text
removelogo=f=/path/to/fixed-mark-mask.png:enable='lt(t,18.65)'
```

The cutoff must come from the actual transition, not a rounded guess. Validate the result by comparing the original and edited crops at early, mid-video, moving-subject, and pre-transition timestamps. Look for residual sparkle pixels, a rectangular blur, texture discontinuity, hand/face distortion, and the mask leaking into legitimate content. Do not classify a later scene-generated logo as a residual provider watermark merely because it occupies the same area.

## End-card acceptance gate

Reject the video for deployment if any of these are true:

- the final text contains malformed or invented words;
- the requested brand is absent or replaced by a generated lookalike;
- a certification, subsidy, or government logo is unverified or visually fabricated;
- the text is too dense, too small, or visible for too little time to read;
- the card is still over moving footage when a clean branded slate is required.

When the rest of the ad works, recommend replacing only the final card in postproduction with real vector logos and approved copy. Do not regenerate the complete video and risk damaging otherwise coherent scenes.

## Report format

Return, in this order:

1. verdict (`ready`, `needs targeted fix`, or `reject`);
2. technical facts with measured values;
3. chronological scene table with approximate timestamps;
4. strengths in hook/message/proof/CTA/pacing/audio;
5. blockers ranked by deployment impact;
6. watermark-removal result, explicitly separated from scene branding;
7. exact targeted fix and what must be re-verified afterward.

Use calibrated language: distinguish what was measured, what was visibly read, and what is an interpretation. Avoid a single aggregate score hiding a legally or commercially blocking end-card defect.

## Session-derived caution

A useful failure pattern is a video whose main 18 seconds are strong while the final 1–2 seconds contain generated text resembling French but with nonsense words and a generated CEE-style logo. In that case, the correct outcome is **targeted end-card replacement**, not a generic “video approved” and not a second full generation. Compare the original/edited bottom-right zone first: the fixed sparkle can be fully removed while the later legitimate-looking mark remains a separate end-card problem.
