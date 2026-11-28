---
name: kie-media-assets
description: Upload local images/videos to Kie.ai for use as reference frames in video generation — file upload endpoint, naming model, and pitfall reference for ByteDance model confusion.
version: 1.0.0
author: W.Alter
tags: [kie, upload, seedance, seedream, reference]
---

# Kie.ai Media Asset Upload

Companion to `kie-video-generation`. Covers uploading local reference images/videos to Kie.ai's CDN so they can be used as `first_frame_url`, `reference_image_urls`, etc.

## Trigger

Load when:
- You need a public URL for a local image before calling Kie video/image APIs
- A user references "Seedance 5" or "Seedream" and you need to disambiguate

## File Upload

```
POST https://kieai.redpandaai.co/api/file-stream-upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
```

```bash
curl -s -X POST "https://kieai.redpandaai.co/api/file-stream-upload" \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -F "file=@/path/to/image.png" \
  -F "uploadPath=images"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | ✅ | File to upload (multipart) |
| `uploadPath` | string | ❌ | Subdirectory path |
| `fileName` | string | ❌ | Custom name (auto if omitted) |

### Response

```json
{
  "success": true,
  "code": 200,
  "data": {
    "downloadUrl": "https://tempfile.redpandaai.co/kieai/200585/images/1784....png",
    "fileSize": 2264065,
    "mimeType": "image/png"
  }
}
```

Use `data.downloadUrl` as the image URL in Seedance/Kling/etc. `createTask` payloads.

### Constraints

- **24h retention** — download to permanent storage if needed
- **Free** — no credits consumed for uploads
- **Base URL differs** — upload is `kieai.redpandaai.co`, generation is `api.kie.ai`
- Max tested: 2.2 MB PNG (limit not documented)

## ⚠️ Pitfall: ByteDance Model Naming Confusion

Users frequently confuse ByteDance model families:

| What user says | What they likely mean | Reality |
|---------------|----------------------|---------|
| "Seedance 5" | Seedance 2.0/2.5 (video) | **Seedance 5 does not exist.** Seedance is the video line (latest: 2.0 on Kie, 2.5 announced). Seed**ream** 5 is the image line. |
| "Seedream 5" | Latest ByteDance image model | Correct — Seedream 5 Pro/Lite is the current image model. |

**Action when user says "Seedance 5":** clarify that Seedance latest is 2.0 (2.5 not yet on Kie), and ask if they meant Seedream 5 (image) or a Seedance video model. Do NOT silently substitute.

## Querying Results

Seedance uses the **Market** polling endpoint, NOT the legacy one:

```
# ✅ Correct (Market models: seedance-2, z-image, etc.)
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>

# ❌ Returns 404 for Market models
GET https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=<taskId>
```

If `getTaskDetail` returns 404, switch to `recordInfo`. The skill `kie-video-generation` documents this but it's easy to miss.

## Related Skills

- `kie-video-generation` — main video generation skill (createTask, models, parameters)
- `vault-lookup` — retrieve `kie/api_key`
