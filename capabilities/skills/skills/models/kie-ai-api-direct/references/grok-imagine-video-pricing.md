# Grok Imagine Video — Confirmed Pricing & Workflow

## Credit Costs (Verified 2026-07-06)

| Mode | Duration | Resolution | Credits | USD |
|------|----------|------------|---------|-----|
| text-to-video | 10s | 720p | 30 | $0.15 |
| image-to-video | 10s | 720p | 30 | $0.15 |

**Key finding:** Both modes cost exactly the same. Image-to-video does NOT save credits — its advantage is artistic control over the starting frame, not cost reduction.

Credit rate: $0.005/credit.

## Image-to-Video Workflow

### 1. Generate keyframe image (any tool: GPT Image, Fal, etc.)
Must be accessible via public URL.

### 2. Upload image to public host
Free hosts that work:
- `catbox.moe` — `curl -sF "reqtype=fileupload" -F "fileToUpload=@image.png" https://catbox.moe/user/api.php`

### 3. Create Kie task
```
POST https://api.kie.ai/api/v1/jobs/createTask
Authorization: Bearer ${KIE_API_KEY}
Content-Type: application/json

{
    "model": "grok-imagine/image-to-video",
    "input": {
        "image_urls": ["https://files.catbox.moe/xxxxx.png"],
        "prompt": "motion description — what happens FROM this keyframe",
        "mode": "normal",
        "duration": "10",
        "resolution": "720p",
        "aspect_ratio": "16:9"
    }
}
```

### 4. Poll for completion
```
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>
```
Typical render time: 60-100 seconds. State transitions: `waiting` → `running` → `success`.

### 5. Result
Video URL is in `resultJson` → `generated_video.mp4` on `tempfile.aiquickdraw.com`.

## Prompt Engineering for Grok Imagine Video

- Pure visual description — what the viewer sees, not how to film
- No camera directions, no storyboard jargon, no "shot 1/then/cut to"
- Golden hour lighting, photorealistic, descriptive color and light
- For motion prompts (image-to-video): short, dense, action-focused — 2-3 sentences max
