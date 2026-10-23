# OpenAI Direct Image Edit — Fallback for Atlas GPT Image 2

When Atlas Cloud returns `"not found"` for GPT Image 2, use the OpenAI API directly.

## Endpoint

```
POST https://api.openai.com/v1/images/edits
Content-Type: multipart/form-data
Authorization: Bearer <OPENAI_API_KEY>
```

## Parameters (multipart form fields)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | ✅ | `gpt-image-2` |
| `image` | file | ✅ | Source image (JPEG/PNG, multipart upload) |
| `prompt` | string | ✅ | What to do with the image |
| `size` | string | ❌ | `1024x1024` (default), `1024x1536`, `1536x1024`, `auto` |
| `n` | string | ❌ | Number of images (1-10), **must be string** |
| `quality` | string | ❌ | `low`, `medium`, `high` (default: `medium`) |

## Response

```json
{
  "created": 1234567890,
  "data": [
    {
      "b64_json": "base64...",
      // OR
      "url": "https://..."
    }
  ]
}
```

Response typically returns `b64_json`. Decode directly — no need to fetch a URL.

## Python Pattern

```python
import requests, base64, os

def edit_image(image_path, prompt, size="1024x1024", quality="medium"):
    url = "https://api.openai.com/v1/images/edits"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    with open(image_path, 'rb') as f:
        files = {'image': (os.path.basename(image_path), f, 'image/jpeg')}
        data = {'model': 'gpt-image-2', 'prompt': prompt, 'size': size, 'n': '1', 'quality': quality}
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)
    resp.raise_for_status()
    result = resp.json()
    img_data = result['data'][0]
    if 'b64_json' in img_data:
        return base64.b64decode(img_data['b64_json'])
    elif 'url' in img_data:
        return requests.get(img_data['url'], timeout=30).content
```

## Pitfalls

1. **`n` must be a string**, not int — multipart form data serializes everything as strings anyway, but be explicit.
2. **Timeout 120s+** — image editing takes 20-60s per image. Don't use short timeouts.
3. **Atlas `/v1/images/edits` does NOT exist** — this is OpenAI-only. Atlas uses `/api/v1/model/generateImage` for its own models.
4. **Vault key**: `openai/api_key` — retrieve with `vault get openai/api_key`.

## Atlas vs OpenAI Direct

| Aspect | Atlas Cloud | OpenAI Direct |
|--------|-------------|---------------|
| GPT Image 2 | ❌ Removed (May 2026) | ✅ Available |
| ERNIE | ✅ | ❌ |
| Gemini image | ⚠️ Untested | ❌ (use Vertex AI) |
| Auth | Atlas API key | OpenAI API key |
| Endpoint | `/api/v1/model/generateImage` | `/v1/images/edits` |
