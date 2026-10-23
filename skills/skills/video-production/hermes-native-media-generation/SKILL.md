---
name: hermes-native-media-generation
description: "Use for Nous-native Hermes media generation."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [hermes, nous, media, video, flux3, bfl, oauth, gateway]
    related_skills: [hermes-agent, multi-model-video-gen, multi-model-video-pipeline]
---

# Hermes Native Media Generation

Use this skill when a user wants Hermes to generate video, images, audio, or other media through a **Nous-managed native tool**, especially when the request names BFL FLUX 3 or explicitly says to use Nous Research rather than a direct vendor API.

This is the native-route skill. It is deliberately separate from generic `video_gen` providers, direct FAL BYOK flows, Kie.ai workflows, and Scena's multi-model pipeline. Do not silently substitute one route for another: the provider and billing path are part of the user's request.

## Routing rule

1. If the user requests **FLUX 3 through Hermes/Nous**, use the native `bfl` toolset (`bfl_flux3_*`).
2. Do **not** route that request through the generic `video_gen` FAL family catalog. Older Hermes checkouts may show only Pixverse/Veo/Seedance/Kling families there and still lack FLUX 3.
3. Do **not** require or use `FAL_KEY`. The native BFL tools authenticate with the Nous bearer and call the Nous-managed BFL gateway; the gateway owns vendor access and account billing.
4. If the user explicitly requests direct FAL, Kie.ai, Higgsfield, or another provider, switch to that provider's skill instead of applying this route.

## Authentication

- Check that the `nous` provider has an OAuth credential without printing tokens or credential files.
- If absent or expired, run `hermes auth add nous --type oauth` and complete the device-code flow in the user's browser. A successful flow ends with a saved Nous device-code credential and `hermes status` reporting `Nous Portal ✓ logged in`.
- Authentication is the prerequisite for native BFL tools. **Do not pre-gate the tools on `paid_service_access`, subscription plan, remaining paid credits, or the generic `fal-video` coverage flag.** Promotional/free-plan eligibility can be a separate server-side entitlement and local billing snapshots can lag or describe only the generic FAL queue.
- If the gateway answers `401`, re-authenticate. If it answers a plan, quota, moderation, or model-availability refusal, surface that gateway message; it is authoritative for the requested native feature.

## Native FLUX 3 tool surface

The native toolset is separate from `video_gen`:

| Tool | Use |
|---|---|
| `bfl_flux3_prompting_guide` | Read once before the first generation; no generation budget |
| `bfl_flux3_text_to_video` | Generate from a prompt |
| `bfl_flux3_image_to_video` | Animate one opening-frame image |
| `bfl_flux3_keyframes_to_video` | Generate between 1–10 pinned images |
| `bfl_flux3_video_continuation` | Continue an existing MP4 |
| `bfl_flux3_get_result` | Poll a job and download the finished MP4 |

For a text-only smoke test, use `bfl_flux3_text_to_video` with a short explicit duration, 720p resolution, and a simple prompt. The submission returns a job id; it does not mean a video exists yet.

## Stale-checkout recovery

FLUX 3 support landed as a native Hermes feature after older local checkouts. If `bfl` or `bfl_flux3_*` is absent:

1. Check the live checkout and its revision; do not assume the installed CLI and source tree match.
2. Fetch the current upstream ref for inspection: `git fetch origin main --quiet`.
3. Search the fetched tree for `tools/flux3_video_tool.py` and `bfl_flux3` registrations.
4. Protect uncommitted work. For a one-off verification, use a detached temporary worktree and prepend it to `PYTHONPATH`, rather than resetting or overwriting the user's checkout:
   ```bash
   git worktree add --detach /tmp/hermes-flux3 FETCH_HEAD
   PYTHONPATH=/tmp/hermes-flux3 python3 -c "import tools.flux3_video_tool"
   ```
5. For a durable installation, use the project's normal Hermes update/restart procedure and verify the resulting `bfl` toolset; never silently copy a partial provider implementation into an old checkout.

The native tool's `check_fn` should be credential-and-endpoint based only. The gateway decides the account's actual eligibility. This distinction is essential for free trials and time-limited launches.

## Gateway contract

The current native implementation resolves the BFL vendor endpoints through the managed gateway helper rather than hardcoding them in the caller. The wire contract is:

- `POST {base}/generations` with a body containing `mode` (`text_to_video`, `image_to_video`, `keyframes_to_video`, or `video_continuation`) plus the model arguments.
- `GET {base}/generations/{id}` until the gateway reports a terminal state.
- Successful responses include a job id and live `guidance`; refusals include an error message and optional details. Treat `guidance` and `error.message` as server policy, not as prose to override.

Do not expose signed delivery URLs in the final response or conversation. The native result tool downloads the clip locally and returns `saved_path`; deliver that path using the platform's exact media convention, commonly a standalone `MEDIA:/absolute/path/to/clip.mp4` line.

## Polling and delivery

- Poll with `bfl_flux3_get_result`; do not make the model or user sleep and guess intervals.
- A long `Generating` phase is normal. Re-poll the same job id rather than submitting a duplicate.
- On `Ready`, verify the local artifact before claiming success. Check the container and stream metadata with `file` and `ffprobe`; validate that the file is plausibly larger than a tiny error body.
- Report real output metadata (duration, resolution, codec, frame rate) from the verified file, not merely the prompt or the initial `submitted` response.
- Deliver the actual local file, not the signed URL and not a markdown link that turns the media into a dead click target.

## Prompting defaults

Read the native prompting guide before the first job. Preserve the user's wording unless grounding or explicit technical defaults are needed. Mention audio deliberately: FLUX 3 may generate synchronized audio by default; say `no music` or disable audio when the user does not want it. For smoke tests, keep the prompt generic and visually checkable so a failed render is easy to distinguish from a prompt-quality issue.

## Multi-shot vertical UGC workflow

Use this pattern for a self-contained 9:16 recipe, demo, or UGC clip when no reference media is required:

1. Prefer `bfl_flux3_text_to_video` when there is no load-bearing reference image. Use keyframes only when identity, packaging, or an exact visual transition must be pinned.
2. Set explicit native parameters: `aspect_ratio: "9:16"`, `duration: 20` (or the requested whole-second length), `resolution: "720p"`; set `generate_audio: true` for synchronized speech and kitchen sound, and `grounding: false` unless the brief genuinely needs a research pass.
3. Write a plain-prose prompt that names the subject, camera language, visible speaker, action, lighting, ambient sound, speech, and exclusions. For multi-shot structure, use explicit blocks such as `SHOT 1 ... HARD CUT. SHOT 2 ...`; make adjacent shots differ in scale, angle, location, or colour so the cut remains visible.
4. Quote dialogue only when the speaker is visible. State `no voiceover`, `no on-screen text`, `no subtitles`, and `no music` separately when those are required. Keep each line short enough to leave end-of-clip headroom; do not assume the provider will fit a long final sentence cleanly into the last second.
5. Give each shot a concrete action that can finish in its slot. A recipe should show the complete visual chain (ingredients/prep, principal cooking action, finishing detail, final plate), not merely list steps in dialogue.
6. Submit once, retain the returned job id, and poll `bfl_flux3_get_result`. `Generating` is normal; re-poll the same id and never resubmit a duplicate just because the first poll timed out or returned no file.
7. On `Ready`, save locally and validate the artifact: `ffprobe` for measured duration/dimensions/FPS/codecs/audio, a full `ffmpeg -f null -` decode, a 1 fps contact sheet for shot continuity and artifacts, and ASR on the delivered audio. If no exact script was supplied, semantic ASR confirmation is enough to report the spoken recipe; if exact copy was supplied, require word-order verification and label any mismatch rather than claiming compliance.

For the concrete prompt skeleton, polling call shape, and release checklist, see `references/flux3-multishot-vertical-ugc.md`.

## Pitfalls

- **Wrong entitlement gate:** a generic `hermes status` may say the account has no paid credits or that `fal-video` is not covered while native BFL FLUX 3 is still permitted. Do not use that generic flag to hide native tools.
- **Wrong provider:** a configured FAL key is not evidence that the user wants direct FAL. For a Nous request, keep the FAL key unused.
- **Wrong toolset:** enabling `video_gen` does not expose `bfl_flux3_*`; enable or load the separate `bfl` toolset on a build that contains it.
- **False completion:** `submitted` is only a job acknowledgement. Poll to `Ready`, download, and inspect the MP4.
- **Leaking URLs:** signed result URLs are bearer-like temporary access. Do not echo them; use the downloaded path.
- **Duplicate jobs:** if polling is interrupted, retain and re-poll the original job id; do not resubmit unless the gateway explicitly says the job is unrecoverable.

For the verified FLUX 3 contract, smoke-test recipe, and expected response shapes, read [references/flux3-bfl-nous-gateway.md](references/flux3-bfl-nous-gateway.md). The free FLUX 3 promo via Nous ended (verified 2026-08-21): expect a promo-end refusal on submission — see [references/flux3-promo-ended-2026-08.md](references/flux3-promo-ended-2026-08.md) for the exact gateway message and post-promo access routes.
