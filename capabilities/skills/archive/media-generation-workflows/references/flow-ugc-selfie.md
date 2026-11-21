# Flow UGC selfie generation

Use this reference when adapting a supplied video to natural UGC selfie grammar in a browser video generator such as Flow.

## 1. Lock the creative interpretation before spending credits

1. Classify the job as **style/grammar adaptation** or literal shot recreation. For style-only UGC, preserve the camera POV and performance grammar, not every source object, subtitle, role, or edit.
2. Write the non-negotiables into the provider prompt: one primary speaker self-filming with the front-facing camera, direct eye contact, visible mouth while speaking, close/medium selfie framing, hand/arm occasionally visible, handheld micro-movement, a practical location, conversational native delivery, no voice-over, and no baked-in text.
3. Keep the approved dialogue separate from the visual direction and require the exact spoken copy. Explicitly ban subtitles, logos, UI, readable signage, music, off-screen narration, and cutaways when post-production owns those elements.
4. Start with one representative paid clip. Only generate the rest after a downloaded artifact passes the selfie-grammar gate.

## 2. Bind a clean reference

- Inspect the actual source pixels before upload. Crop away status bars, platform UI, lead forms, and ad chrome; crop or mask subtitles and logos when they are irrelevant to the style. Never rely on a filename or on prompt text to bind a reference.
- In Flow, use the visible ingredient picker or the visible Add-to-prompt path. After upload, verify the displayed filename, MIME type, byte size, thumbnail, and composer chip. A completed file-input event without a visible chip is not a binding receipt.
- For continuation clips, attach the downloaded approved clip as a continuity reference and state that it controls identity/wardrobe only; attach a style frame only when it adds a distinct camera or location cue. Do not let a reference clip silently replace the new dialogue or force a copied shot list.
- If Flow rejects a speaking-video ingredient with “Unable to edit the speech in this video”, do not resubmit the same input. Verify the job failure and actual credit balance, then, with retry approval, bind an inspected clean still extracted from the approved clip for identity/wardrobe instead; preserve the new dialogue and selfie directions. This avoids requesting speech editing of the reference video, but does not guarantee generation success.

## 3. Configure and verify Flow headlessly

Run the browser through headless Camoufox Max by default; do not open or create a Mac browser tab merely because it is available.

Before submission, verify the live UI/DOM states rather than trusting a summary label:

- Video mode, the exact live model selected by the provider, portrait `9:16`, the requested resolution, duration, and `x1` output.
- Agent disabled for a deterministic prompt-driven generation unless the brief explicitly requires it.
- Ingredients selected only when a real asset is bound.
- The displayed credit cost and current account entitlement.

Submit once, keep the submission receipt and project-scoped media ID, and poll that original job. Do not resubmit because a lazy gallery or monitor briefly appears empty.

## 4. Validate the representative clip before continuing

Download the original generated file from the opened Flow video element; do not validate a thumbnail or a claimed URL. Then run:

```bash
ffprobe -v error -show_entries format=duration,size:stream=index,codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels -of json clip.mp4
ffmpeg -v error -i clip.mp4 -f null -
ffmpeg -y -i clip.mp4 -vf "fps=1/2,scale=270:-1,tile=2x3:padding=8:margin=8" -frames:v 1 contact.jpg
ffmpeg -y -i clip.mp4 -vn -ac 1 -ar 16000 speech.wav
```

Use the contact sheet for composition and artifact triage, but judge handheld movement on the native-cadence video or measured frame-to-frame motion; a static sheet cannot prove camera stability, drift, or lip-sync. Review for one speaker, face-to-camera delivery, practical location, continuity, no generated text/logo/UI, and no serious facial or hand artifacts. If the provider repeatedly smooths the camera after the representative attempt, stop paid prompt churn and, when allowed by the brief, apply one restrained deterministic pass from the clean base (overscan, low-amplitude rotation/crop drift, and small exposure variation), then re-audit full-resolution frames and motion measurements. Run ASR on the speech and compare the transcript to the approved dialogue before generating additional clips; if ASR is unavailable, label that acceptance gate unverified instead of treating the prompt as a transcript.

## 5. Assemble and qualify the final master

1. Normalize dimensions, frame rate, timestamps, pixel format, sample rate, channel layout, and audio mapping before concatenation. Preserve each original and render to a new path.
2. After concatenation and any music/ducking mix, run ASR again on the **encoded clean master**. Individual clip transcripts are insufficient: a model can append a duplicated phrase, hidden narration, or a credit line at a clip tail that is only exposed after the master is decoded.
3. Reject or trim any out-of-script speech before subtitle timing. Generate word-synchronous karaoke from the approved final-master ASR, then render and inspect active-word pixels, line width, punctuation, and lower-third safety.
4. Verify the final container with `ffprobe`, perform a full decode, inspect start/middle/end frames and the complete caption contact sheet, and exercise the actual target player. If Hermes needs it, preserve MP4 and produce a VP9/Opus WebM fallback; a successful file write is not proof of playback.

## Reusable failure gates

- A polished presenter, colleague-operated camera, or technical B-roll sequence fails a style-only selfie brief even when the location and script are correct.
- A source frame containing platform UI or subtitles can cause the generator to reproduce those pixels; clean the bound reference instead of merely writing “no text” in the prompt.
- A successful generation card or thumbnail is not a delivered asset; download, decode, inspect, and transcribe the actual file.
- Per-clip ASR does not replace final-master ASR; reject unexplained spoken tails before subtitles and music are treated as final.
