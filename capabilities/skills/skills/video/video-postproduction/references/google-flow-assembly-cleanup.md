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
