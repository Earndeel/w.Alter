# Model contracts and batch recovery

## Verified image payloads

### Seedream 5 Pro image-to-image

```json
{
  "model": "seedream/5-pro-image-to-image",
  "input": {
    "prompt": "...",
    "image_urls": ["https://...", "https://..."],
    "aspect_ratio": "9:16",
    "quality": "basic",
    "output_format": "png",
    "nsfw_checker": false
  }
}
```

- `quality`: `basic` = 1K, `high` = 2K.
- Supports up to 10 reference images.
- `nsfw_checker` is documented and configurable for this model.

### Nano Banana 2

```json
{
  "model": "nano-banana-2",
  "input": {
    "prompt": "...",
    "image_input": ["https://...", "https://..."],
    "aspect_ratio": "9:16",
    "resolution": "1K",
    "output_format": "png"
  }
}
```

- Supports up to 14 reference images.
- `resolution`: `1K`, `2K`, or `4K`.
- Reference field is `image_input`, not `image_urls`.
- No exposed moderation switch; filtering is upstream.

### Nano Banana 2 Lite

```json
{
  "model": "nano-banana-2-lite",
  "input": {
    "prompt": "...",
    "image_urls": ["https://...", "https://..."],
    "aspect_ratio": "9:16"
  }
}
```

- Supports up to 10 references.
- Reference field differs from full Nano Banana 2.
- No exposed moderation switch.

### GPT Image 2 image-to-image

```json
{
  "model": "gpt-image-2-image-to-image",
  "input": {
    "prompt": "...",
    "input_urls": ["https://...", "https://..."],
    "aspect_ratio": "auto"
  }
}
```

- Reference field is `input_urls`.
- `auto` is the documented I2I aspect-ratio value; do not transplant unsupported `quality`, `size`, or provider-specific fields.
- In sensitive portrait workflows, tasks may run for several minutes before returning moderation or upstream-timeout failures. Persist task IDs and inspect `creditsConsumed` before deciding whether to retry.

### Grok Imagine image-to-image

```json
{
  "model": "grok-imagine/image-to-image",
  "input": {
    "prompt": "...",
    "image_urls": ["https://...", "https://..."]
  }
}
```

- Reference field is `image_urls`.
- The verified Kie I2I contract does not require an aspect-ratio or resolution field; omit decorative parameters not documented for this endpoint.
- Multiple reference sheets can be supplied together for identity and expression guidance.

## File upload

```bash
curl -X POST https://kieai.redpandaai.co/api/file-stream-upload \
  -H "Authorization: Bearer $KIE_API_KEY" \
  -F "file=@reference.png" \
  -F "uploadPath=images/user-uploads" \
  -F "fileName=reference.png"
```

Parse `data.downloadUrl`, then fall back to `data.url` or `data.fileUrl`. Upload reference sheets once per run and reuse URLs.

## Result parsing

Task details may place output data in `resultJson`, `result`, `output`, `outputs`, or `response`. A JSON string commonly decodes to an object containing `resultUrls`, `urls`, `images`, or `outputUrls`.

Never treat submit success as generation success. Poll and inspect `state`/`status`:

- Success states: `success`, `succeeded`, `completed`, `complete`
- Failure states: `fail`, `failed`, `error`, `cancelled`

A moderation rejection may look like:

```json
{
  "state": "fail",
  "failCode": "400",
  "failMsg": "...filtered...",
  "creditsConsumed": 0.0
}
```

## Partial batch recovery

Use a dictionary keyed by task index. During each poll pass:

1. Skip already-terminal indexes.
2. Save success URL or failure reason for each newly-terminal task.
3. Continue until all task IDs are terminal or the global deadline expires.
4. Download every success.
5. Rewrite and resubmit only failed concepts.
6. Preserve output numbering when replacement tasks complete.

This avoids the common failure mode where one rejected item raises an exception and hides four successful generations.

## Provider-selection lesson

For strongly sensual but non-explicit adult portrait briefs, provider behavior differs materially. Seedream exposes a documented moderation parameter through Kie; Google-backed Nano Banana models retain upstream filtering with no exposed switch. Choose based on the requested creative boundary rather than silently weakening the brief after submission.