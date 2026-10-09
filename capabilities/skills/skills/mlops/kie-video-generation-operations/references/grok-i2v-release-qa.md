# Grok Imagine Video 1.5 — reference-driven I2V release QA

Use this reference when a local environment/character reference set must drive a Kie.ai Grok Imagine Video 1.5 Preview image-to-video task.

## Verified operational pattern

1. **Upload local references before task creation.** Use `POST https://kieai.redpandaai.co/api/file-stream-upload` with `multipart/form-data`, `file=@...`, and `uploadPath=images`. Retrieve the Kie credential with `vault get kie/api_key`; keep it in memory and return only HTTP status, response code, and public `downloadUrl` values.
2. **Use the exact current model contract.** Submit `POST https://api.kie.ai/api/v1/jobs/createTask` with:
   - `model: grok-imagine-video-1-5-preview`
   - `input.prompt`: the user's visual prompt
   - `input.image_urls`: the uploaded reference URLs (preserve the user's Image1/Image2/Image3 mapping)
   - `input.aspect_ratio`: `16:9` when requested
   - `input.resolution`: `720p`
   - `input.duration`: integer seconds, max 15 for this model
   - `input.nsfw_checker: true` unless the live contract says otherwise
   Do not add `generate_audio`, `aspect`, `aspectRatio`, `seconds`, or other fields from unrelated Kie model families without rechecking the live model page. Native audio is produced by this Grok route when the prompt requests it.
3. **Measure paid usage.** Query `GET https://api.kie.ai/api/v1/chat/credit` immediately before and after the task. Report only numeric balances and HTTP status. A verified 15-second 720p task consumed 45 credits; the before/after delta is authoritative for the account.
4. **Poll and download.** Poll `GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...` about once per minute. On `data.state=success`, parse `data.resultJson` and extract `resultUrls[0]`; download the temporary URL immediately. Do not call `createTask` again just because the first status is `waiting` or `generating`.

## Release normalization

Before delivery, inspect with `ffprobe` and decode with `ffmpeg -f null -`. Kie may return a preview/thumbnail stream (often MJPEG) alongside the actual H.264 video, and may include a small duration overrun. Build the deliverable explicitly from `0:v:0` and `0:a:0`, trim audio/video to the requested duration, and re-encode only when needed to get an exact duration or remove the preview stream. Confirm `width:height`, SAR, frame count, codecs, audio sample rate/channels, and a non-silent track.

Create a 1-fps storyboard and inspect it visually: reference fidelity, environment continuity, requested final pose, no reference-board residue, no extra people, no text/logo/watermark, and no major anatomy failure. Scene-cut detection is supporting evidence only; whip-pans and impacts can create or hide metric cuts, so never infer shot quality from the count alone.

## Pitfalls

- Three reference sheets are identity/context references; they are not automatically safe as literal keyframes. For models with only a first-frame input, make or select a clean opening composition instead of exposing character-sheet typography in the video.
- A successful API submission is not a generated artifact. The task is complete only after `recordInfo` returns success, the MP4 is downloaded, and the local file passes technical and visual QA.
- Temporary result URLs expire; download in the success branch before doing secondary analysis.
