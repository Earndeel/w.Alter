# Kie.ai GPT Image 2 — Image-to-Image Guide

Unlike the text-to-image endpoint (`gpt-image-2-text-to-image`), the image-to-image endpoint uses the Market task API.

## Submit

```
POST https://api.kie.ai/api/v1/jobs/createTask
```

```json
{
  "model": "gpt-image-2-image-to-image",
  "input": {
    "prompt": "Remove the background from this product...",
    "input_urls": ["https://your-cdn.com/original.png"],
    "aspect_ratio": "1:1",
    "resolution": "1K"
  }
}
```

**Important**: The `aspect_ratio` MUST be set explicitly for 2K/4K resolution. For `1:1` aspect ratio, 4K is not supported (API returns error).

## Poll

```
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId={taskId}
```

Response:
```json
{
  "code": 200,
  "data": {
    "state": "success",
    "resultJson": "{\"resultUrls\":[\"https://tempfile.aiquickdraw.com/images/chatgpt/...\"]}"
  }
}
```

Parse `resultJson` as JSON to extract `resultUrls`.

## Key differences from text-to-image
- Uses `/jobs/createTask` endpoint (Market task API), NOT OpenAI-compatible endpoints
- Uses `resultJson` field (nested JSON string), NOT direct `outputs` array
- Polls via `/jobs/recordInfo`, NOT `/v1/images/generations`
- Input images are in `input.input_urls[]` (public URLs), NOT base64
- `input_urls` accepts any publicly accessible HTTP(S) URL

## Reliable image hosting for I2I references
- Kie.ai rejects `.avif` format ("File type not supported") — convert to PNG/JPG first
- Use your deployed Cloudflare Pages URLs as reference image sources (they're always public)
- `transfer.sh` and `0x0.st` may block CORS or timeout — Cloudflare Pages URLs work reliably
