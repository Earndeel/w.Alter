---
name: openrouter-image-generation
description: "Use when Monsieur requests OpenRouter image generation."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [openrouter, image-generation, image-to-image, references, visual-qa]
---

# OpenRouter Image Generation

## When to use

Use this skill whenever Monsieur explicitly names OpenRouter, an OpenRouter image model, or an OpenRouter model page/playground for image generation or image editing. It is provider-specific operational guidance; use a generic image-generation skill only when OpenRouter is not part of the request.

## Non-negotiables

- Load `model-id-lookup` before using a named model ID. Never silently replace the requested model with a nearby model or version.
- Prefer the dedicated Image API (`/api/v1/images`) for models whose output modality is `image`; do not assume the text Chat Completions API is the correct image route.
- Discover capabilities live. The model page, the dedicated image catalog, and the per-endpoint record are the sources of truth; model-level UI prose can be stale or incomplete.
- Never print, persist, or place credentials in prompts, request logs, skill files, or output metadata. Read `openrouter/api_key` from the vault only at execution time.
- The deliverable is a verified local image file and a native file delivery, not a claimed URL or a description of what the image might look like.

## Operational workflow

### 1. Validate the requested model and endpoint

1. Read the requested OpenRouter page with the web front door when the user supplied a URL, so the request is grounded in the current page.
2. Query `GET https://openrouter.ai/api/v1/images/models` and match the exact `id`/`name`. The dedicated image catalog is authoritative; a model can be absent from the general `/api/v1/models` response while present here.
3. Fetch `GET https://openrouter.ai/api/v1/images/models/{model_id}/endpoints` and inspect the selected endpoint's `supported_parameters`, `allowed_passthrough_parameters`, provider, and pricing. Use only advertised fields.
4. Confirm the requested aspect ratio is supported. If not, report the mismatch instead of silently changing it.

### 2. Normalize reference inputs without losing critical details

The Image API uses `input_references` and many endpoints allow only one reference. If Monsieur supplies several images:

1. Inspect every source visually before composing anything.
2. Make one high-resolution reference board with the full identity/character views and enlarged crops of the details Monsieur called out (teeth, eyes, logos, hands, product markings, or fabric). Keep the mapping obvious: e.g. "upper-left = character A; upper-right = character B; lower panels = detail crops".
3. Do not add decorative labels or generated content that could be mistaken for part of the reference. Preserve source pixels and use neutral separators/backgrounds.
4. Tell the model in the prompt how the board is organized. A single board is a fidelity workaround, not permission to invent a second reference slot.

Reference object shape:

```json
{
  "type": "image_url",
  "image_url": {
    "url": "data:image/png;base64,<base64-bytes>"
  }
}
```

### 3. Build an explicit, constraint-first prompt

Keep the user's requested scene and composition first. Then state:

- which person/object belongs to which area of the reference board;
- identity and style features that must remain unchanged;
- the one or two details that are acceptance-critical;
- aspect ratio and framing;
- a concise negative list for text, watermark, extra subjects, duplicated anatomy, or genericized details.

For detail-sensitive faces, say what is actually visible rather than using vague instructions such as "make the teeth realistic". Example: distinguish upper-only versus both arches, natural ivory versus artificial white, visible alignment/asymmetry, and which details must not be normalized. Do not claim dental features that the reference inspection did not show.

### 4. Call the dedicated Image API

Use `POST https://openrouter.ai/api/v1/images` with the exact catalog ID. For a model that advertises the common MAI-style contract:

```json
{
  "model": "microsoft/mai-image-2.5-pro",
  "prompt": "...",
  "aspect_ratio": "9:16",
  "n": 1,
  "input_references": [
    {
      "type": "image_url",
      "image_url": {"url": "data:image/png;base64,..."}
    }
  ]
}
```

Do not add `size`, `quality`, or provider-specific fields unless the live endpoint advertises them. Use a 180–240 second request timeout: image generation may take 1–2 minutes even when the connection is healthy. Capture `usage.cost` when returned so Monsieur receives a real cost, not an estimate.

### 5. Decode, validate, and deliver

1. Parse the non-streaming JSON response and require `data[0].b64_json`.
2. Decode the base64 bytes and save a PNG under `/root/.hermes/attachments/` (or the active session's output directory).
3. Validate with Pillow: file opens, pixels load, format is expected, dimensions are non-zero, and the resulting aspect ratio is consistent with the requested ratio. Print only safe metadata: status, model, path, bytes, dimensions, cost, and elapsed time.
4. Load the actual output with vision and check the requested scene, identities, critical details, text/watermarks, obvious artifacts, and crop. If the model adds a frame or margin, crop the inner artwork with Pillow and re-run visual QA on the final path.
5. Deliver the verified path with the platform's native `MEDIA:` convention. Never deliver an intermediate reference board instead of the generated image.

## Provider safety-filter recovery

A benign prompt can still be rejected if the reference board contains accidental suggestive material or if the wording is overinterpreted. If the provider returns a content-safety label such as `MultiSeverity_SexualScore`:

1. Do not resubmit the identical payload.
2. Keep only the relevant face/object/detail crops; remove body or underwear views and mask exposed areas with ordinary clothing where necessary.
3. Rephrase the scene as wholesome, fully clothed, family-friendly, and non-erotic without changing the user's intended setting or emotional tone more than necessary. Avoid repeating unnecessary suggestive vocabulary.
4. If this succeeds but a user-marked detail was normalized, make at most one targeted refinement pass: combine the successful base image and the original critical-detail crops into one reference board, ask to keep the scene unchanged, and correct only that detail.

This is accidental-input cleanup, not a safety bypass. If the sanitized request is still rejected, report the provider block plainly and do not claim a generated result.

## Visual QA for identity and dental fidelity

When the user explicitly emphasizes teeth, inspect both the original mouth crops and the final smiles. Check:

- visible tooth count and which arch(es) are exposed;
- central incisor shape and relative width;
- natural color versus synthetic whitening;
- visible crowding, overlap, spacing, or asymmetry;
- no extra/missing/duplicated teeth, braces, or melted anatomy.

A model often produces a plausible but generic Hollywood smile. Treat that as a failed critical-detail check, not as an invisible success. Prefer a targeted refinement or report the limitation honestly.

## Reusable support material

- `references/openrouter-image-api.md` — live contract notes, validated MAI-Image-2.5 Pro parameters, request/response details, cost/latency snapshot, and the tested safety-filter recovery pattern.

## Common mistakes

- Using `/api/v1/models` alone and declaring a current image model unavailable.
- Passing two `input_references` objects to an endpoint whose live maximum is one.
- Assuming all image models accept `size` or `quality` because another provider does.
- Treating HTTP 200 or a JSON response as proof that an image exists without decoding and opening the bytes.
- Delivering the first successful candidate without checking the user's acceptance-critical visual detail.
