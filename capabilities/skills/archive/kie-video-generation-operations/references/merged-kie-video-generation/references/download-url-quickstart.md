# Kie.ai Download URL API Quickstart

## Generate Presigned Download URL

Temporary download link for generated files (20-min expiry).

```
POST /api/v1/common/download-url
Authorization: Bearer <token>
Content-Type: application/json
```

### Request Body

```json
{
  "url": "https://tempfile.aiquickdraw.com/g/users/.../generated/.../file.mp4"
}
```

**⚠️ CRITICAL:** The field is `"url"`, NOT `"file_url"`. `"file_url"` returns `422: 图片url不能为空` (Chinese error: image URL cannot be empty).

### Example

```bash
curl -s -X POST "https://api.kie.ai/api/v1/common/download-url" \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://tempfile.aiquickdraw.com/g/users/.../generated_video.mp4"}'
```

### Response (success)

```json
{
  "code": 200,
  "msg": "success",
  "data": "https://tempfile.xxx.r2.cloudflarestorage.com/...?X-Amz-Algorithm=...&X-Amz-Signature=..."
}
```

### Response (error — wrong field)

```json
{
  "code": 422,
  "msg": "图片url不能为空",
  "data": null
}
```

### Full Workflow: Submit → Generate Video → Download

```python
import requests

KIE_KEY = "..."
HEADERS = {"Authorization": f"Bearer {KIE_KEY}"}

# 1. Submit video generation
resp = requests.post("https://api.kie.ai/api/v1/jobs/createTask", headers=HEADERS, json={
    "model": "grok-imagine/image-to-video",
    "input": {
        "image_urls": ["https://image.png"],
        "prompt": "animate...",
        "duration": "6",
        "resolution": "480p",
        "aspect_ratio": "16:9"
    }
})
task_id = resp.json()["data"]["taskId"]

# 2. Poll for completion
# (use getTaskDetail or recordInfo endpoint)

# 3. Get raw URL from result (tempfile.aiquickdraw.com → 403 without presign)
raw_url = "https://tempfile.aiquickdraw.com/.../generated_video.mp4"

# 4. Generate presigned URL (field="url", NOT "file_url")
dl_resp = requests.post("https://api.kie.ai/api/v1/common/download-url",
    headers=HEADERS,
    json={"url": raw_url})
presigned_url = dl_resp.json()["data"]

# 5. Download from presigned URL
video_data = requests.get(presigned_url, stream=True).content
```
