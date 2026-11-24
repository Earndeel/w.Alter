# Google Flow vertical MP4: assembly and watermark cleanup

Provider-specific reference for two completed Flow exports, typically 10 s + 10 s at 720×1280 and 24 fps.

## Resolve the completed asset

A Flow rendering card can expose a pending preview/media ID and later show a completed asset. Do not freeze the first `video.src` while the card still shows a percentage. After completion, re-scan the card/result and probe the downloaded candidate.

```bash
ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames \
  -of json source.mp4 continuation.mp4
```

Reject HTML/error downloads, wrong durations/resolutions, and candidates without audio.

## Resolve the ordered clip roles

Do not infer the pair from filenames alone. Before concatenating, map each selected asset to the brief's ordered role (for example, `0–10 s = agriculteur`, `10–20 s = femme`) and verify start/middle/end frames. A generated asset called `continuation` may be based on a separate reference subject; it is not automatically the first input. Keep the role mapping beside the probe output so a technically valid but creatively wrong all-one-subject montage is caught before encoding.

## Starting mask for the Flow sparkle

On validated 720×1280 vertical exports, the small white sparkle sits near the lower-right clothing area. Prefer a shape-aware 720×1280 grayscale mask that follows the sparkle silhouette plus a small antialiased margin. The previously validated star mask occupies roughly `x=569..631`, `y=1129..1191`:

```python
from PIL import Image, ImageDraw

mask = Image.new("L", (720, 1280), 0)
draw = ImageDraw.Draw(mask)
# Approximate four-point sparkle; expand only enough to cover its antialiased halo.
cx, cy = 600, 1160
points = [(cx, cy-31), (cx+11, cy-10), (cx+31, cy),
          (cx+11, cy+10), (cx, cy+31), (cx-11, cy+10),
          (cx-31, cy), (cx-11, cy-10)]
draw.polygon(points, fill=255)
mask.save("flow-star-watermark-mask.pgm")
```

These coordinates and the shape are starting points, not universal constants. Extract first/middle/last frames from every new asset and adjust if the watermark moved. A broad rectangle can remove the sparkle while visibly smoothing textured fabric or erasing a zipper; use it only as a fallback after visual comparison. A mask that is too tight can leave a white crescent, so inspect enlarged crops rather than trusting mask geometry.

## Validated FFmpeg assembly pattern

Use `removelogo` with the shape-aware mask when the overlay is fixed, then concatenate both filtered video streams and both audio streams explicitly. `delogo` option sets vary by FFmpeg build; in particular, do not assume `band` exists. Check `ffmpeg -h filter=delogo` before using it.

```bash
ffmpeg -y \
  -i farmer_10s.mp4 -i woman_10s.mp4 \
  -filter_complex \
  "[0:v]removelogo=flow-star-watermark-mask.pgm,setpts=PTS-STARTPTS[v0]; \
   [1:v]removelogo=flow-star-watermark-mask.pgm,setpts=PTS-STARTPTS[v1]; \
   [0:a]asetpts=PTS-STARTPTS[a0]; \
   [1:a]asetpts=PTS-STARTPTS[a1]; \
   [v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 24 \
  -c:a aac -b:a 192k -movflags +faststart final.mp4
```

Because the logo filter operates on decoded frames, re-encode the video. Keep both audio streams in the concat graph; otherwise a valid-looking MP4 can silently lose narration or music. If the creative brief instead requires a true same-subject continuation, use the same role-resolution step but verify visual continuity rather than forcing the farmer/woman example.

## Premium vertical ad variant

For a paid-ad deliverable, the validated cleanup/concat recipe is only the media layer. Add a creative gate before encoding: choose the visually coherent pair, not merely the pair that satisfies subject labels. In the reference case, the cinematic farmer A+B pair was commercially coherent while the woman assets were raw selfie/UGC; mixing them produced an amateur result. If a subject change is mandatory, use a regenerated bridge or make the transition a deliberate branded chapter rather than a naked hard cut.

A reliable 20-second structure for a 10-second A + 7.25-second B + 3.25-second end card is:

- A → B: `xfade=transition=fadeblack:duration=0.25:offset=9.75`.
- Content → end card: the first transition outputs 17.0 s; use `xfade=transition=fade:duration=0.25:offset=16.75` to finish at 20.0 s.
- Before either xfade, normalize all video inputs with `fps=24,settb=1/24`; encoded Flow files and a PNG loop often arrive with different timebases.
- Keep B's final audio tail if it contains the closing spoken phrase, even when B's video is trimmed earlier for pacing. After `acrossfade`, probe the audio stream separately; pad and trim (`apad`, `atrim=duration=20`) so audio and video both end at exactly 20.000 s.
- Generate the end card deterministically with known copy. Do not retain provider-generated certification text, seals, URLs, or brand typography unless verified. Use explicit line breaks and a safe rectangle, then inspect the full-resolution PNG for clipping before compositing.

The final QA storyboard must include the fade/black seam, the first clean frame of B, the end-card crossfade, several stable end-card frames, and enlarged crops of the former sparkle coordinates. A passing `ffprobe` duration is not enough: visually inspect the end card and probe the audio stream duration independently.

## Required QA

```bash
ffmpeg -hide_banner -loglevel error -i final.mp4 -f null -
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames \
  -of json final.mp4
```

Inspect a storyboard containing the end of A, the start and middle of B, and the final frame. Inspect enlarged crops of the former watermark area at the beginning, the seam, and the end. Metadata alone cannot prove visual removal.
