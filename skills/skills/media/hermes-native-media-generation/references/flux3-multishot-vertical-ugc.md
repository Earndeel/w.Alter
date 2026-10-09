# FLUX 3 multi-shot vertical UGC reference

Use this reference for a short self-contained recipe, product demo, or creator-style clip rendered by the Nous-managed BFL FLUX 3 route.

## Request shape

When no reference media is load-bearing, use `bfl_flux3_text_to_video`:

```json
{
  "prompt": "<plain-prose multi-shot brief>",
  "aspect_ratio": "9:16",
  "duration": 20,
  "resolution": "720p",
  "generate_audio": true,
  "grounding": false
}
```

Use `bfl_flux3_keyframes_to_video` instead when identity, packaging, or exact visual continuity must be anchored by supplied images. Do not add reference fields to a text-only request.

## Prompt skeleton

```text
Ultra-realistic vertical 9:16 UGC video, <duration> seconds, <subject and setting>.
The same <person/product> remains coherent across every shot. <camera language>.
The visible speaker addresses the camera; no voiceover. Audio: <ambient layers>;
no music. No on-screen text, no subtitles, no logos.

SHOT 1, 0–<t1>s: <distinct opening action and visible dialogue>.
HARD CUT to a contrasting scale or angle.
SHOT 2, <t1>–<t2>s: <principal action and visible dialogue>.
HARD CUT to a contrasting detail shot.
SHOT 3, <t2>–<t3>s: <finishing action and visible dialogue>.
HARD CUT to the final composition.
SHOT 4, <t3>–<duration>s: <result, proof, or plated final state and short closing line>.
Natural-speed gestures; each action completes within its slot; no temporal stretching.
```

A quoted line is rendered as speech only when a speaker is visibly on camera. Keep lines short, especially the final line: FLUX 3 may place speech late in a shot and clip the last syllable when the script consumes the entire duration. If the brief does not contain canonical copy, validate the delivered speech semantically; if it does, transcribe the final file and enforce ordered word-level compliance.

For recipes, make the visual chain complete even if the dialogue is compact: ingredients/prep → principal cooking action → finishing detail → plated result. Naming a step in dialogue is not evidence that the step appeared on screen.

## Polling and persistence

Submission returns a job id, not a video. Store the id and poll the same job with `bfl_flux3_get_result` until `Ready`. A `Generating` result is normal; do not resubmit a duplicate after a long poll or a client timeout. On `Ready`, pass `save_to` when a deterministic local filename is useful and deliver the resulting `saved_path`, never the signed vendor URL.

## Release QA

Run all of the following against the downloaded MP4:

```bash
ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_frames,sample_rate,channels \
  -of json final.mp4

ffmpeg -hide_banner -loglevel error -i final.mp4 -f null -

mkdir -p qa
ffmpeg -hide_banner -loglevel error -y -i final.mp4 \
  -vf 'fps=1,scale=256:-2,tile=5x4:padding=4:margin=4' \
  -frames:v 1 qa/contact_1fps.jpg
```

Inspect the contact sheet for shot contrast, subject continuity, food/product state, malformed generated text, watermarks, and obvious morphing. Use a scene-change probe when the hard cuts themselves matter. Measure audio separately with `volumedetect` or `astats`, then run ASR on the delivered file rather than on the prompt or job metadata:

```bash
HF_HUB_DISABLE_TELEMETRY=1 uv run --with faster-whisper python3 -c '
from faster_whisper import WhisperModel
m = WhisperModel("base", device="cpu", compute_type="int8")
segments, info = m.transcribe("final.mp4", language="fr", beam_size=5, vad_filter=True)
print(" ".join(s.text.strip() for s in segments))
'
```

Report measured metadata, not requested metadata. A native 20-second render may probe as approximately `20.041667` seconds with 481 frames at 24 fps; this is frame-time quantization, not a reason to re-render unless the delivery spec demands an exact container duration. A typical 720p vertical result may measure 704×1280 with H.264 video and mono AAC at 44.1 kHz.

## Known generation/QA boundary

The provider can produce a visually coherent multi-shot recipe while moving or approximating speech timing. Treat “the prompt contains the dialogue” as intent only. For an exact script, a final ASR mismatch or a clipped closing line is a release failure and should trigger a shorter script, more end headroom, or a deterministic audio/lip-sync correction. For an open-ended recipe brief, state the semantic ASR result and any audible clipping instead of pretending word-for-word fidelity.
