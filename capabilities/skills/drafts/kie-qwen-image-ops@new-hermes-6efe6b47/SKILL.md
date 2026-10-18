---
name: kie-qwen-image-ops
description: Generate images with a named model on Kie.ai Market API.
version: 1.1.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [kie, qwen, image-generation, image-to-image]
    related_skills: [kie-image-generation-operations]
---

## When to Use

- Monsieur names a specific image model (Qwen 2.1, Qwen 3, Seedream...) and Kie.ai — generate on that exact model via the Market API rather than the default agent route.

Load `kie-image-generation-operations` via `walter_skill_read` for the general Kie procedure; this file carries the model-specific contract and delivery rules proven on this VM.

## Contract discovery

- Verify the exact slug against the live catalog before generating: `GET https://api.kie.ai/api/v1/playground/model-paths` (no auth). Qwen Image 2.1 = `qwen2-1/image-to-image` (reference input) or `qwen2-1/text-to-image`. Older Qwen (`qwen/image-to-image`, `qwen/image-edit`) and Qwen 3 (`qwen3/...`) are separate models — never infer one model's fields from another and never silently substitute what the agent route picked.
- The default agent route (walter_generate) may choose a different model than the one Monsieur named. When he names a model, call the Market API directly and state which model actually ran.

## Submit and poll

Reference upload: `POST https://kieai.redpandaai.co/api/file-stream-upload` as `multipart/form-data` with BOTH `uploadPath` (a path string, e.g. `beaver/upload`) AND a file part named `file`. Omitting either yields a 400 that names only the missing parameter. Read the key via `vault get kie/api_key` inside the script; never print it. Keep the returned `data.downloadUrl` for `input.image_urls`.

```json
{
  "model": "qwen2-1/image-to-image",
  "input": {"prompt": "...", "image_urls": ["<downloadUrl>"], "aspect_ratio": "auto"}
}
```

Submit to `POST https://api.kie.ai/api/v1/jobs/createTask`, then poll `GET /api/v1/jobs/recordInfo?taskId=...` until `state: success` (single image ≈ ten seconds; cap the wait). Parse `resultJson` as a JSON string and download `resultUrls[0]`. Verify the file on disk (non-zero bytes, decodable image) before delivering.

## Output honesty

- AI-typical text rendering: main headings render cleanly, secondary fields and MRZ bands come out deformed or incoherent. Check the output with a vision pass before claiming wording, and flag the deformation instead of presenting it as clean.
- Never deliver an image styled as a real national identity document as-is: render the fictional/prop framing visibly (e.g. `SPÉCIMEN — NON VALABLE`) so the artifact stays a prop. A truly realistic-looking ID generation was not validated end-to-end on this VM — do not claim it works.
- Text rendered as an image cannot carry a live-model guarantee: verify before delivery, never from the prompt alone.
