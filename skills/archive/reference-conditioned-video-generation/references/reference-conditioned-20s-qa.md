# Reference-conditioned 20-second QA recipe

This reference captures the repeatable details behind the class-level workflow. Replace `INPUT.mp4` and `FINAL.mp4` with the current artifact paths; do not copy stale session paths.

## Clean-anchor prompt pattern

> Use all supplied sheets only as identity, costume, palette, and environment references. Create a clean cinematic opening frame. Do not reproduce the reference sheets, labels, names, diagrams, swatches, typography, or board layout. Show exactly the requested characters in the requested environment, with recognizable silhouettes and full-body framing when the shot list requires it. No extra people, text, logos, subtitles, or watermark.

Inspect this image before submitting video generation. A successful image request is not enough if one character is missing or the board layout survived.

## Timed-extension pattern

Append this after the user's original prompt without rewriting it:

```text
ADDED EXTENSION — preserve every preceding instruction and every shot exactly, then continue from the existing final pose without restarting:

T0 to T1: State the exact body position, camera, and first action at the boundary.
T1 to T2: State readable action cause-and-effect and the required camera change.
T2 to T3: State the final exchange/recovery and the true end composition.

CONTINUITY AND AUDIO: Do not add characters, props, labels, subtitles, logos, or watermarks. Extend the existing sound bed through the extension. Move any earlier “final impact,” “bass drop,” or “near-silence” instruction to the true end while preserving all other audio instructions.
```

For action, describe advance -> evade/block -> counter -> recovery/reset. This gives the model a usable continuation instead of merely adding “five more seconds of fighting.”

## Native FLUX master normalization

The native 720p FLUX 3 output can be reported as 16:9 while measuring 1280x704. For a strict 16:9 file, trim and pad rather than stretch:

```bash
ffmpeg -hide_banner -loglevel error -i INPUT.mp4 \
  -filter_complex "[0:v]trim=duration=20,setpts=PTS-STARTPTS,pad=1280:720:0:8:color=black,setsar=1[v];[0:a]atrim=duration=20,asetpts=PTS-STARTPTS[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset medium -crf 18 \
  -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart FINAL.mp4
```

Use the requested duration instead of hard-coding `20` when the job is not 20 seconds. Equal 8-pixel bars preserve character geometry; vertical scaling does not.

## Technical QA

```bash
ffprobe -v error -show_entries \
  format=duration,size:stream=index,codec_type,codec_name,width,height,\
  sample_aspect_ratio,r_frame_rate,avg_frame_rate,nb_frames,sample_rate,channels \
  -of json FINAL.mp4

ffmpeg -hide_banner -loglevel error -i FINAL.mp4 -f null -

ffmpeg -hide_banner -loglevel error -i FINAL.mp4 \
  -vf "fps=1,scale=320:-2,tile=5x4:padding=4:margin=4" \
  -frames:v 1 STORYBOARD.jpg

ffmpeg -hide_banner -loglevel error -ss 15 -i FINAL.mp4 -t 5 \
  -vf "fps=2,scale=320:-2,tile=5x2:padding=4:margin=4" \
  -frames:v 1 EXTENSION_STORYBOARD.jpg

ffmpeg -hide_banner -i FINAL.mp4 -af volumedetect -vn -f null - 2>AUDIO_QA.log
```

The full storyboard tests identity and shot variety. The extension storyboard tests the boundary and the added interval. Scene detection is only a diagnostic and should be run at more than one threshold; camera whip-pans and impact motion can create extra detections. Report counts precisely: 20 distinct shots normally means 19 transitions, while “20 transitions” means 21 shots.

## Delivery rule

Only deliver the saved, verified local MP4 with the platform's native media marker. State exact duration, dimensions, FPS, audio presence, and any deliberate letterbox/padding caveat; do not report the provider's aspect-ratio label without checking the file.
