# OpenRouter Image API — contract notes

These notes supplement the class workflow in `SKILL.md`. Re-check the live endpoints before every run because model catalogs and prices change.

## Dedicated discovery endpoints

- Image model catalog: `GET https://openrouter.ai/api/v1/images/models`
- Per-model capabilities: `GET https://openrouter.ai/api/v1/images/models/{model_id}/endpoints`
- Generation: `POST https://openrouter.ai/api/v1/images`

The dedicated image catalog can contain image-output models that do not appear in a filtered or unauthenticated general `GET /api/v1/models` response. Treat the dedicated catalog plus per-endpoint record as authoritative for image requests.

## Validated MAI-Image-2.5 Pro contract

The live catalog record for `microsoft/mai-image-2.5-pro` advertised:

- input modalities: `text`, `image`
- output modality: `image`
- `aspect_ratio`: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`, `3:2`, `2:3`, `auto`
- `n`: range `1..1`
- `input_references`: range `0..1`
- provider: Azure

The POST model value is the catalog slug `microsoft/mai-image-2.5-pro`; do not copy an incidental dated model suffix from a page URL unless the live catalog returns it as the actual `id`.

## Request shape

```json
{
  "model": "microsoft/mai-image-2.5-pro",
  "prompt": "...",
  "aspect_ratio": "9:16",
  "n": 1,
  "input_references": [
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/png;base64,<base64-bytes>"
      }
    }
  ]
}
```

The response is non-streaming JSON with base64 image bytes:

```json
{
  "data": [
    {"b64_json": "<base64>", "media_type": "image/png"}
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "cost": 0.0
  }
}
```

Decode `data[0].b64_json`; do not expect a hosted image URL. Validate the decoded file with Pillow before delivery.

## Multiple references when max is one

When the user gives two or more images, create one high-resolution board rather than sending unsupported extra reference objects. A tested layout is:

- top-left/top-right: the full character or product views;
- lower panels: enlarged crops of acceptance-critical details;
- neutral background and separators;
- no decorative text that the model could copy into the output.

Tell the model exactly how the board is mapped. For faces, enlarged mouth/eye/detail crops materially improve fidelity, but the board remains one API reference.

## Safety-filter recovery pattern

A benign real-person travel image request was rejected by Azure with HTTP 400 and the label `MultiSeverity_SexualScore` when the reference board contained irrelevant underwear/body views and the prompt used strongly affective wording. The validated recovery was:

1. Make a new board with face and detail crops only.
2. Mask any exposed shoulder/body area with ordinary clothing; retain the face and critical detail pixels.
3. Use wholesome, fully clothed, family-friendly wording and remove unnecessary suggestive vocabulary.
4. If the first safe result genericizes an acceptance-critical detail, make one targeted refinement using a board containing the successful image plus the original detail crops. Ask to preserve the scene and change only that detail.

This removes accidental suggestive input; it is not a bypass of the provider's safety controls. If the sanitized request remains blocked, report the block rather than inventing an output.

## Observed run snapshot (not a price guarantee)

On 2026-09-02, a successful MAI-Image-2.5 Pro call with one composite reference and `aspect_ratio: "9:16"` returned a PNG at `768x1360` in about 45 seconds with reported cost about `$0.1504`. A refinement pass returned the same dimensions; the raw output added a white frame, which was removed by cropping the inner artwork and re-running visual QA. Use live `usage.cost` for current reporting.
