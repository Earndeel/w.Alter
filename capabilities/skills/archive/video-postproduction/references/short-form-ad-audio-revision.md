# Short-form ad audio revision — clean voice, natural pace, exact duration

Use this reference when a rendered 9:16 ad is technically valid but the user reports an unpleasant background, phasey residue, or rushed narration.

## Core diagnosis

A loudness pass and successful ASR do **not** prove that an ad sounds good. In one validated 15-second revision, the first master passed metadata, decode, transcript, and loudness checks, yet the user correctly rejected it because:

- the "music" bed came from center cancellation of the reference mix and carried audible phase/residual artifacts;
- a long script had been forced into 15 seconds through high TTS rate plus time compression.

The fix was not another broad denoiser. The bed itself was the bad source, and the copy was too long.

## Correction sequence

1. **Solo the sources.** Render or inspect voice-only, bed-only, and the combined mix. Identify whether the defect is in the voice, bed, or mix processing.
2. **Discard destructive extractions.** Treat center-cancel, karaoke, and phase-inversion stems as diagnostic or emergency sources, not release-ready music. Replace the bed with a clean licensed/generated instrumental, or deliver voice-only when no clean bed exists.
3. **Rewrite before accelerating.** If exact copy cannot fit naturally, shorten redundant copy or obtain approval to extend the duration. Do not stack a high TTS rate with `atempo` merely to satisfy the clock.
4. **Render the full voice again.** Regenerating the complete narration preserves prosody. Avoid patching isolated words over the old voice.
5. **Transcribe the new rendered voice.** Rebuild word-level subtitle timings from the actual audio, not the previous script timing.
6. **Re-time the picture semantically.** Align price, aid, comfort, offer, and CTA scenes to the corresponding spoken intervals. Changing audio without moving edit beats leaves a polished-looking but incoherent ad.
7. **Verify both streams and listen.** Check stream duration/frame count, loudness/peak, pause noise, ASR, subtitles, and an actual A/B audition. Metrics are screening gates, not a substitute for ears.

## Practical pace baseline

For short French direct-response narration, roughly **3.0–3.3 spoken words per second** is a useful first-pass screening range, not a universal release rule. Measure the generated file because punctuation, voice, and prosody change duration.

For a 15-second ad, a good starting layout is:

- last spoken word around 14.0–14.3 seconds;
- 0.5–0.8 seconds of visual breathing room on the end card;
- claim order matched to visual order;
- no artificial time-compression unless the user explicitly approves the trade-off.

Validated revision example (baseline only): 44-word French script, Remy FR at `+10%`, final word at 14.18 s, approximately 19.7% slower than the rejected version.

## Clean voice-only FFmpeg pattern

When the bed is the defect, remove it from the graph rather than attempting to hide it with denoising:

```text
[voice:a]atrim=0:15,apad=pad_dur=0.5,atrim=0:15,
  afade=t=in:st=0:d=0.03,
  alimiter=limit=0.95,
  loudnorm=I=-16:TP=-1.5:LRA=7[audio]
```

Do not add `afftdn`, aggressive gates, or spectral subtraction by reflex; each can introduce pumping or metallic speech. Use them only after the isolated voice itself demonstrates a noise problem.

## Exact-duration trap: audio can hide a short video stream

`format.duration=15.000` can be a false pass when audio lasts 15 seconds but the video stream ends early. This commonly happens when:

- a requested trim is longer than the generated source clip;
- `overlay=shortest=1` inherits the shorter base duration;
- concat branches were assumed to have target durations without probing actual source lengths.

In the validated revision, two nominal target segments were longer than their actual ~2.04-second sources. The first render reported a 15-second container but only a 13.37-second video stream.

For a mostly static/detail shot, retime the available clean range deliberately:

```text
trim=start=<safe_start>:duration=<available>,
setpts=(<target>/<available>)*(PTS-STARTPTS)
```

Inspect the slowed result; regenerate rather than over-stretch expressive human motion. At the final overlay, pad only the missing rounding frame(s), then trim:

```text
[base][overlay]overlay=0:0:format=auto:shortest=1,
  format=yuv420p,
  tpad=stop_mode=clone:stop_duration=0.05,
  trim=duration=15[video]
```

## Release checks

```bash
ffmpeg -v error -i final.mp4 -f null -
ffprobe -v error \
  -show_entries format=duration:stream=index,codec_type,duration,nb_frames,r_frame_rate \
  -of json final.mp4
ffmpeg -hide_banner -nostats -i final.mp4 \
  -af ebur128=peak=true -f null -
```

For exactly 15 seconds at 30 fps, require both:

- video stream duration `15.000000`;
- `nb_frames=450`.

Also inspect a full 0–14 second contact sheet, re-transcribe the final encoded audio, and audition at least the opening, one speech segment, every pause, and the ending. A clean transcript cannot detect a phasey bed; a good LUFS number cannot detect rushed delivery.
