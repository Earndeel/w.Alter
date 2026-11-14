## Oracle FFmpeg media-worker sidecar

Scena uses the Oracle VM only for deterministic zero-credit post-production after provider-generated clips. Runtime flow: `render_video` creates a `video_jobs` row (`task_type='video_composition'`, `cost_credits=0`) → `POST https://temp-scena.walter-ai.cloud/jobs/render-video` → FFmpeg/ffprobe → signed `/webhook/media-worker` callback → D1 completion → multimodal QA → retry or Telegram human gate.

Security contract for Scena↔VM jobs and callbacks:
- Shared key: Cloudflare secret and VM env both named `SCENA_TEMP_STORAGE_TOKEN` / `SCENA_TEMP_UPLOAD_TOKEN` respectively.
- Headers: `X-Scena-Timestamp` and `X-Scena-Signature: sha256=<hex>`.
- Canonical bytes: `<timestamp>\n<METHOD>\n<URL pathname>\n<exact raw body>`.
- Reject timestamps outside 300 seconds, malformed signatures, Bearer-only job/callback requests, private/non-HTTPS asset URLs, and callback hosts other than `api.walter-ai.cloud`.
- Legacy operator `/upload` remains Bearer-authenticated; job submit/status and callbacks require HMAC.

Production service:
- Source: `services/scena-media-worker/server.py`
- Tests: `python3 -m unittest -v services.scena-media-worker.test_server` and `node --experimental-strip-types --test tests/media-worker-integration.test.mjs`
- Installed code: `/opt/scena-temp-storage/server.py`
- Unit: `scena-temp-storage.service`
- Local/public health: `http://127.0.0.1:8799/health`, `https://temp-scena.walter-ai.cloud/health`
- Cloudflare Worker deploy must include the same shared secret and the `/webhook/media-worker` route. Always verify the shared key without printing it: a valid signed callback for an unknown `scena-media-*` job must return `404 media_job_not_found`, not `401`.
- End-to-end verification must render real clips, wait for D1 `status=completed`, download the master, run `ffprobe`, visually inspect a frame, confirm `cost_credits=0`, then delete the temporary D1 job row.
