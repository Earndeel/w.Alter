# Branded overlays and light dialogue music

Use this recipe when a finished vertical ad needs a persistent official/partner logo, word-highlight subtitles, and a subtle music bed without damaging dialogue or an existing end card.

## 1. Resolve the real master

Do not trust names such as `final`, `premium`, or `video1` by themselves. For every plausible candidate:

1. Record duration, resolution, frame rate, audio presence, file size, and modification time.
2. Build a comparable 5-frame strip (start, three interior points, near-end).
3. Label each row with the real path and visually identify presenter, campaign text, end card, and watermark state.
4. Select the asset whose decoded content matches the requested role, then keep an explicit role → path mapping.

## 2. Clean a supplied transparent logo

Many PNG logos are nominally RGBA but contain nearly invisible alpha dust far outside the real artwork. Scaling the uncropped canvas makes the mark too small; compositing it can reveal specks.

- Inspect image mode, alpha extrema, and alpha bounding box.
- Zero only negligible alpha values (for example `alpha <= 10`), preserving antialiasing above the threshold.
- Compute the new alpha bounding box, add a small padding, and crop.
- Scale from the cleaned content, not the original padded canvas.
- For a 720×1280 portrait ad, a logo block around 25–30% of canvas width is usually discreet but readable. Validate on actual frames rather than treating this as a fixed rule.
- Dark official text often needs a subtle white rounded plate (roughly 80–85% opacity) for consistent contrast. Do not add a plate when it conflicts with the supplied identity treatment.

Example placement on a 720-wide canvas: `x=24`, `y=30`, cleaned artwork near 190 px wide inside a ~214 px plate. These are starting values, not a universal brand standard.

## 3. Audit collisions over the full timeline

Inspect at least three ordinary backgrounds and the final 3 seconds at one-second cadence.

- Never cover an existing campaign header, logo, legal block, or CTA merely to keep the new mark persistent.
- If an end card already owns the top-left region, disable the added logo at the end-card transition with an overlay timeline expression such as `enable='lt(t,16.75)'`, or relocate it only when another safe branded region exists.
- A clean disappearance at the designed scene transition is preferable to overlapping two logos.
- Verify one frame immediately before and after the enable boundary.

## 4. Adapt subtitles around an occupied end card

Keep the same font, outline, colours, and active-word behavior as the campaign's other videos, but allow a second ASS style for a crowded end card.

- Main footage: bottom-centre alignment with the established safe margin (for example `MarginV=170`).
- End card: keep bottom-centre alignment but move into a known-empty lower band (often `MarginV=40–60`).
- Switch styles by timing, not by manually repainting frames.
- Continue to cap blocks at two measured lines and keep 4–5 contextual words when width permits.
- Correct ASR against the actual spoken French and domain context. Split a fused token such as `panoïbrides` into `panneaux` + `hybrides` by dividing its original time span, then merge clitics (`l` + `'électricité`, `d` + `'énergie`) before ASS generation.

Sample representative active words on ordinary footage and on the end card. The active word alone must use the highlight colour; all other words remain white.

## 5. Mix a light music bed under dialogue

Use a supplied licensed track or generate an original instrumental bed. For a restrained lounge treatment, a soft electric-piano chord progression, rounded bass, brushed percussion, and a 1–2 second fade in/out work well. Render 48 kHz stereo at the exact master duration.

Dialogue must remain the anchor:

1. Measure the source audio globally and in meaningful segments: intro, speech, pause, outro.
2. Set the music so its mean level is roughly 10–15 dB below speech before or after ducking, depending on the density of the arrangement.
3. Use the original audio as sidechain input so the music recedes during speech and returns during gaps.
4. Leave peak headroom or apply a transparent final limiter.

Representative FFmpeg audio graph:

```text
[0:a]volume=0.92,asplit=2[voice][side];
[2:a]volume=0.18[music];
[music][side]sidechaincompress=threshold=0.020:ratio=5:attack=20:release=350[ducked];
[voice][ducked]amix=inputs=2:normalize=0,alimiter=limit=0.95[aout]
```

Treat the values as starting points. Re-measure and adjust for the actual voice and track.

## 5a. Audio-only revision fast path

When the picture, graphics and captions are already approved and the source master contains clean dialogue only, do **not** rebuild or upscale the video just to add music. Stream-copy the approved video and replace only its audio:

```bash
ffmpeg -y -i approved_voice_only.mp4 -i lounge_bed.wav \
  -filter_complex "[0:a]atrim=0:15,apad,atrim=0:15,asplit=2[voice][side]; \
  [1:a]atrim=0:15,volume=0.30[music]; \
  [music][side]sidechaincompress=threshold=0.020:ratio=5:attack=20:release=320[ducked]; \
  [voice][ducked]amix=inputs=2:duration=longest:normalize=0, \
  alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=7[aout]" \
  -map 0:v:0 -map '[aout]' -c:v copy -c:a aac -b:a 192k \
  -ar 48000 -ac 2 -t 15 -movflags +faststart final_lounge.mp4
```

Use the voice as sidechain only if the approved source really is voice-only; otherwise use the clean narration stem. Apply the bed fade in **one** place (source render or final graph), not redundantly at both stages.

For a deterministic original 15-second lounge bed, 96 BPM gives exactly six 4/4 bars. A sparse Rhodes/electric-piano progression, rounded root/fifth bass, brushed percussion and a quiet pad leaves room for narration. Render PCM at 48 kHz stereo, fade gently, and normalize the bed around −20 LUFS with conservative peaks before mix gain. In the final encoded master, a useful starting result is music roughly 10–15 dB below speech, still detectable in true pauses but never masking consonants.

Verification for this fast path:

- require identical video-stream duration/frame count and confirm the stream was copied rather than visually re-rendered;
- measure speech, pause and tail separately instead of trusting full-program LUFS;
- transcribe the **mixed final MP4** and compare the complete ordered script;
- retain final headroom and audition the encoded output, because meters cannot judge whether the lounge arrangement is tasteful.

## 6. Verification gates

### Visual

- Full decode succeeds.
- A 1 fps contact sheet shows stable logo size/position and intended disappearance or relocation on the end card.
- Full-resolution samples prove logo readability on several backgrounds.
- Word-highlight samples prove exact spelling, one active word, max two lines, and no CTA collision.
- Static end cards may legitimately trigger `freezedetect`; correlate events with decoded frames before calling them defects.

### Audio

- Verify codec, 48 kHz stereo, duration, mean level, and max peak.
- Re-measure intro, speech, gap, outro, and full program after mixing.
- Speech level should stay close to the source, while gaps should show the subtle added bed.
- Listen when an audio playback path is available; numeric levels prove headroom and presence, not musical taste.

### MD5 rule

Decoded-audio MD5 equality is valid only when audio is intentionally copied unchanged (for example, subtitle burn-in with `-c:a copy`). Once music, fades, ducking, gain, or limiting is added, the audio must differ. Verify the mix with segment-level levels and peak/headroom checks instead of expecting matching hashes.

## Premium-ad creative gate

When the user asks for a qualified advertisement, do not start by concatenating the requested role labels. First audit the available media as a visual set:

1. Build a contact sheet for every candidate with start, midpoints, last frame, and (for 10-second clips) roughly 0/2.5/5/7.5/last seconds. Score shot variety, product visibility, camera language, lighting, presenter continuity, and end-frame usability.
2. Do not mix a cinematic/generated product sequence with raw selfie/UGC footage merely because the subjects are different or the brief says `farmer + woman`. That creates a visibly amateur seam. Prefer a coherent same-presenter pair when the available assets make that the only commercial-looking option; otherwise report the trade-off and identify the missing bridge/regenerated shot needed to honor the subject change.
3. Treat provider-generated typography, logos, legal/certification claims, URLs, and end cards as untrusted image content. Never ship malformed generated text or invented claims. Replace the end card with deterministic typography/layout (Pillow, Remotion, or FFmpeg drawtext) using only verified copy supplied by the brief.
4. Wrap and size every end-card line for the actual 720×1280 canvas. Inspect the full-resolution card, not only a thumbnail, for right-edge clipping, CTA overflow, accent/diacritic errors, contrast, and safe margins.
5. Use an intentional transition grammar (hard cut, short fade-to-black, or a justified crossfade) instead of an accidental seam. If `xfade` is used, normalize every video input to the same frame rate and timebase first (`fps=24,settb=1/24` is a safe pattern for the common Flow exports).
6. Calculate video and audio durations independently. A crossfade reduces the sum by its duration; pad/fade the audio explicitly (`apad` + `atrim`) so the audio stream ends exactly with the video, including the final card.
