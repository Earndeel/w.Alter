# Verified FLUX 3 / BFL via Nous gateway

## When to use this reference

Use this path when the user requests FLUX 3 through Hermes and wants Nous Research to handle access. This is **not** the generic `video_gen` FAL plugin path.

## Verified facts

- The native implementation lives in `tools/flux3_video_tool.py` on current Hermes `main`.
- The toolset name is `bfl`; the six native tools are `bfl_flux3_*`.
- `check_bfl_requirements()` checks for a usable Nous credential and the managed BFL endpoint. It deliberately does not inspect subscription plan, paid credits, or the generic `fal-video` coverage flag.
- The managed endpoint resolves to the Nous tool gateway and uses the BFL mount (`.../api/bfl` in the verified build). Do not send the request to `fal.ai` directly and do not add `FAL_KEY` for this route.
- A Free Nous account can be accepted by the native FLUX 3 gateway when the launch/promotion entitlement applies. The server response is authoritative.

## Authentication recipe

```bash
hermes auth add nous --type oauth
hermes status
```

For a headless host, the auth command prints a Nous Portal device URL and code. Open the URL in the user's authenticated browser, complete the Google/passkey step, and let the waiting command finish. Do not print or copy access/refresh tokens into chat.

A healthy status includes:

```text
Nous Portal   ✓ logged in
```

Do not treat a generic message such as “no usable paid credits” as proof that native FLUX 3 is unavailable. That message can describe the generic managed tool pool, while BFL FLUX 3 has its own server-side launch entitlement.

## Tool modes

| Tool | Body mode | Required media |
|---|---|---|
| `bfl_flux3_text_to_video` | `text_to_video` | none |
| `bfl_flux3_image_to_video` | `image_to_video` | one image |
| `bfl_flux3_keyframes_to_video` | `keyframes_to_video` | 1–10 images + frame indices |
| `bfl_flux3_video_continuation` | `video_continuation` | one MP4 |
| `bfl_flux3_get_result` | GET job status | job id |

Read `bfl_flux3_prompting_guide` before the first generation. For a smoke test, use text-to-video, `duration: 5`, `resolution: 720p`, an explicit aspect ratio, and a visually simple prompt. Disable audio for a silent test or state `no music`; FLUX 3 may generate synchronized audio by default.

## Wire contract

The native tool resolves endpoints with the managed gateway helper and sends a Nous bearer:

```text
POST {bfl_base}/generations
{
  "mode": "text_to_video",
  "prompt": "...",
  "duration": 5,
  "resolution": "720p",
  "aspect_ratio": "16:9",
  "generate_audio": false
}
```

The submission response is a job acknowledgement, not a completed video. A verified successful shape is equivalent to:

```json
{
  "result": "Video generation started. Poll bfl_flux3_get_result with id=bfl_job_<id> ...",
  "details": {"id": "bfl_job_<id>", "status": "submitted"}
}
```

The gateway can include live guidance such as the remaining free-plan allowance. Do not infer entitlement locally from an unrelated account endpoint.

Poll with `bfl_flux3_get_result` using the same id. The native handler owns the wait cadence and downloads the finished clip; do not issue rapid external polls or submit a second job:

```json
{
  "details": {
    "id": "bfl_job_<id>",
    "status": "Ready",
    "saved_path": "/absolute/path/to/video.mp4",
    "saved_bytes": 2293057
  }
}
```

A `Generating` status is normal. If a client call is interrupted, retain the original id and poll it again. A 401 means re-authentication; a 4xx refusal, moderation result, quota limit, or model-unavailable response should be surfaced as the gateway's decision.

## Stale checkout procedure

Older checkouts may have the generic `plugins/video_gen/fal` families but no native BFL tools. Verify without disturbing uncommitted work:

```bash
git fetch origin main --quiet
git grep -n -i -E 'flux.?3|bfl_flux3' FETCH_HEAD -- ':!*.lock'
git worktree add --detach /tmp/hermes-flux3 FETCH_HEAD
PYTHONPATH=/tmp/hermes-flux3 python3 -c 'import tools.flux3_video_tool as f; print(f.check_bfl_requirements(), f._endpoints())'
```

For a durable fix, update Hermes through its normal deployment/update path and restart the process. Do not copy one provider file into an older tree: the native feature also relies on registry/toolset wiring, managed gateway helpers, media upload helpers, and delivery code.

## Verification and delivery

After `Ready`, verify the actual artifact rather than trusting the job text:

```bash
file /absolute/path/to/video.mp4
ffprobe -v error \
  -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 /absolute/path/to/video.mp4
```

Report the real duration, dimensions, codec, frame rate, and file size. Deliver the local artifact with the platform's native media convention, commonly as a standalone line:

```text
MEDIA:/absolute/path/to/video.mp4
```

Never return the signed CDN URL from the gateway: it is temporary bearer-like access and the native result handler already replaces it with a local file.
