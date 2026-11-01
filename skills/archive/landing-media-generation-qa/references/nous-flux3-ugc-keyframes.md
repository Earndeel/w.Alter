# Nous Portal FLUX 3 — storyboard-to-UGC keyframe workflow

Use this reference when a beauty/product storyboard must become original UGC video clips through GPT Image 2 references plus the managed Nous Portal BFL FLUX 3 tools. It is a provider-specific supplement to the general media-generation and QA skill.

## 1. Convert the board into a new shot plan

Treat an uploaded storyboard as creative direction, not as media to insert into the video. Extract:

- timing and shot boundaries;
- visible actions and expressions;
- spoken copy and speaker visibility;
- product handling and packaging details;
- camera grammar (direct front-camera POV versus visible phone in a third-person shot).

For a 40-second deliverable, a reliable adaptation is two independent 20-second clips. Rewrite the copy and timings into two acts rather than asking the model to reproduce a contact sheet or the board's embedded text. Put the resulting shot plan and the exact dialogue in the generation prompt.

## 2. Build a coherent GPT Image 2 reference set

Generate one vertical identity anchor first. Supply the storyboard and the real product image as references, but explicitly request a single UGC still with:

- a fictional adult presenter and stable identity details;
- natural phone framing, realistic skin and hair, and the intended room;
- the real product packaging as the authoritative product reference;
- no storyboard grid, contact-sheet layout, captions, subtitles, watermark, or invented branding.

Generate subsequent action stills with the anchor as the primary identity reference and the product source as a secondary reference. Typical six-frame set:

1. presenter holding the product beside her face;
2. opening the sachet and applying the patch;
3. wearing the patches while presenting/pointing at the package;
4. removing a patch in a mirror;
5. fresh post-treatment selfie;
6. holding multiple sachets and giving a thumbs-up.

Open representative stills before video generation. Reject a frame with a materially different face, broken hands, malformed packaging, or a product text/logo defect severe enough to undermine the shot. Generated typography is not proof of correct brand copy; use the supplied product image as ground truth.

## 3. Submit FLUX 3 keyframe jobs

Use `bfl_flux3_keyframes_to_video` rather than text-to-video when several moments must remain anchored. The current contract is:

- `input_images`: 1–10 local PNG/JPEG/WebP paths or URLs;
- `keyframe_indices`: one unique frame index per input, at 24 fps;
- every index must satisfy `index <= duration * 24`;
- set `duration` explicitly when using indices;
- for vertical UGC use `aspect_ratio: "9:16"`, `resolution: "720p"`, `duration: 20`;
- set `generate_audio: true` when dialogue and ambient sound are required;
- set `grounding: false` when the supplied reference images are authoritative and an external research pass could reinvent the product.

Three pins per 20-second clip are usually enough. Example timing layouts:

- clip A: `[0, 120, 264]` → opening product reveal, application around 5 s, packaging/pointing around 11 s;
- clip B: `[0, 144, 336]` → mirror action, fresh face around 6 s, product/CTA around 14 s.

These are pins, not loose reference images: describe the motion that carries the presenter between them and explicitly forbid a slideshow or face morph.

### Prompt recipe for dialogue

The speaker must be visible on camera. Quote the exact French line in the prompt and separately describe the visible shot containing it. Include:

- `SHOT ONE`, `SHOT TWO`, etc. with approximate timing and a clear hard cut when desired;
- natural real-life speed and enough distinct action to occupy the duration;
- no music when the goal is speech-led UGC, plus the desired ambient/package sounds;
- `no on-screen text, no subtitles, no captions, no watermark`, unless the brief explicitly asks for them;
- same presenter, room, clothing, light, and product identity across pins.

Do not rely on “no slow motion” alone; give the presenter concrete actions and completion points. Do not ask the model to render a storyboard, text overlay, or reference board inside the video.

In a direct repository harness where the native tools are not exposed to the agent, local paths can be passed through the managed media uploader before invoking the registered handlers. Prefer the native `bfl_flux3_keyframes_to_video` / `bfl_flux3_get_result` surface when available; never hand-encode local files into prompt arguments.

## 4. Poll without duplicate generation

Submission returns a job ID; it does not create a local MP4 yet. Persist the ID and poll `bfl_flux3_get_result` with the same ID. A long `Generating` or `Reasoning` status is normal. If a poll returns `Still generating`, run another poll; do not resubmit the generation, which creates a duplicate charge/job.

For two independent clips, polling may run concurrently after both submissions. Use bounded background watchers if the provider call can occupy several minutes, and save each completed result to a deterministic local path. Do not inspect the output directory as a job-status signal: no file exists until the job is ready.

## 5. Verify before delivery

For every completed MP4:

```bash
ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,sample_rate,channels \
  -of json clip.mp4
ffmpeg -hide_banner -loglevel error -i clip.mp4 -f null -
```

Expect approximately 20.041667 seconds and 481 video frames for a nominal 20-second 24-fps export; this is frame quantization, not automatically a duration defect. Confirm a real H.264 video stream, 704×1280-ish vertical dimensions, and an AAC audio stream when audio was requested.

Extract a low-rate contact sheet (for example `fps=1/4,tile=2x3`) and inspect it with vision. Check the first, middle, last, and every keyframe region for identity, product fidelity, action cadence, malformed hands, unwanted board/text/watermarks, and hard-cut stability. Inspect the first 0.20–0.25 seconds after each hard cut at native cadence when the action or body geometry is important.

If the brief contains exact spoken copy, transcribe the delivered audio rather than trusting the prompt. A lightweight local verification pattern is:

```bash
uv run --with faster-whisper==1.2.1 --python 3.12 python3 asr_check.py clip_a.mp4 clip_b.mp4
```

Use language `fr`, an initial prompt containing the expected copy, and compare the normalized transcript. Treat punctuation/apostrophe segmentation (`à l’aise` versus an ASR `à’aise`) as an ASR artifact only after listening or a second model pass; if exact legal/claim wording is contractual and the transcript remains uncertain, do not call it script-verified—regenerate or replace the voice deterministically.

## 6. Assemble a 40-second master when requested

If the user asks to “coller” the two clips, concatenate only after both individual clips pass QA and their codecs/timebases match:

```text
file '/absolute/path/clip_a.mp4'
file '/absolute/path/clip_b.mp4'
```

```bash
ffmpeg -hide_banner -loglevel error \
  -f concat -safe 0 -i concat_list.txt \
  -c copy -movflags +faststart master_40s.mp4
```

Re-probe and decode the master, then inspect a seam contact sheet spanning roughly 18–22 seconds. A hard cut is preferable to an accidental blend for this two-act UGC structure. Report the measured master duration; concatenated 24-fps exports can land slightly above 40 seconds because of frame/timestamp rounding.

Deliver the two verified clips, the optional master, and the generated reference stills. Do not deliver the storyboard screenshot as a video frame unless explicitly requested.

## Common failure modes

- **Storyboard copied literally:** the model renders the board/grid or its text. Add explicit “single original UGC frame/video; do not reproduce the storyboard/contact sheet; no text overlays.”
- **Identity drift:** later stills describe a generic woman. Generate an anchor first, pass it into every later image prompt, and repeat stable face/hair/clothing details.
- **Product drift:** generated sachet typography changes. Keep the real product image in the reference set and reject visibly wrong packaging; do not treat model-rendered claims as verified.
- **Keyframe rejection:** an index is past the selected duration. Set an explicit duration and calculate indices as `seconds * 24` before submission.
- **Duplicate charge:** a slow poll is mistaken for failure. Reuse the original job ID; never resubmit until the provider returns a terminal error.
- **Silent or text-only dialogue:** quoted words are supplied without a visible speaker or audio flag. Keep the presenter visible, enable audio, name the ambient layer, and forbid subtitles.
- **Metadata-only release:** a job says Ready but the clip has wrong content. Decode it, inspect frames, verify audio, and transcribe exact copy before delivery.
