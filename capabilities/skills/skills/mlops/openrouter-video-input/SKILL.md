---
name: openrouter-video-input
category: mlops
description: 'Send video to LLMs via OpenRouter native video support -- model catalog, payload formats, and R2 upload workflow for efficient transmission'
---

# OpenRouter Video Input Strategy

OpenRouter supports **33+ models** that accept video natively. This skill covers which models work, how to format payloads, and the optimal strategy for sending video without losing data.

## Model Catalog (Video-Supported)

### Free Tier
- `qwen/qwen3.6-plus:free` — Input: text, image, video. Price: $0. **CAUTION**: rate-limited on free tier.

### Budget (<$0.0000003/prompt token)
- `qwen/qwen3.5-9b` — $0.00000005/token
- `qwen/qwen3.5-flash-02-23` — $0.000000065/token
- `google/gemma-4-26b-a4b-it` — $0.00000013/token
- `google/gemma-4-31b-it` — $0.00000014/token  
- `bytedance-seed/seed-2.0-mini` — $0.0000001/token
- `google/gemini-3.1-flash-lite-preview` — $0.00000025/token. Supporte aussi: audio, file
- `qwen/qwen3.5-122b-a10b` — $0.00000026/token

### ⚠️ OpenAI models on OpenRouter do NOT support video input
**Critical finding**: `openai/gpt-5.5`, `openai/gpt-4o`, `openai/gpt-4.1` and all other OpenAI models on OpenRouter return `"No endpoints found that support input video"`. OpenRouter's OpenAI provider relay does not expose the multimodal video capability that these models have natively on `api.openai.com` (ChatGPT.com works because it uses internal endpoints, not OpenRouter).

**On OpenRouter, video input is exclusively available on Google Gemini models.** Check actual model video support with:
```python
import requests, os
models = requests.get("https://openrouter.ai/api/v1/models",
    headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}).json()
video_models = [m["id"] for m in models["data"] if "video" in m.get("architecture", {}).get("input_modalities", [])]
```

### Premium
- `google/gemini-3.1-pro-preview` — $0.000002/token. Top-tier video analysis. Also `gemini-3.1-pro-preview-customtools`
- `google/gemini-2.5-flash` — Best quality/cost ratio for video ($0.005 for a 12s analysis with 8k tokens output)
- `google/gemini-2.5-pro` — Max quality, best for detailed scene-by-scene video analysis
- `google/gemini-3-flash-preview` — $0.0000005/token. Good mid-range option

### ⚠️ CRITICAL: OpenAI & Anthropic do NOT support video on OpenRouter
Models like `openai/gpt-5.5`, `openai/gpt-4.1`, `anthropic/claude-sonnet-4`, and `anthropic/claude-opus-4` all return `"No endpoints found that support input video"` via OpenRouter, even though the same models accept video natively via their own APIs (ChatGPT.com, api.openai.com). **Only Google Gemini models currently support video input through OpenRouter.** Always verify via the `/v1/models` endpoint — query `architecture.input_modalities` for `'video'`.

### How to Query Available Models
```python
import json, urllib.request

API_KEY = os.environ.get('OPENROUTER_API_KEY', '')
headers = {"Authorization": f"Bearer {API_KEY}"}
req = urllib.request.Request("https://openrouter.ai/api/v1/models", headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    models = json.loads(resp.read())
    
video_models = [m for m in models['data'] 
                if 'video' in m.get('architecture', {}).get('input_modalities', [])]
print(f"Found {len(video_models)} video-capable models")
```

## Payload Formats

### Format 1: Direct Base64 (Small Files)
For files <5MB (before base64 expansion to ~6.7MB):

```python
import json, base64, urllib.request

with open('video.mp4', 'rb') as f:
    vid_b64 = base64.b64encode(f.read()).decode()

payload = json.dumps({
    "model": "google/gemini-3.1-flash-lite-preview",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{vid_b64}"}},
            {"type": "text", "text": "Describe this video in detail"}
        ]
    }],
    "max_tokens": 500
})

url = "https://openrouter.ai/api/v1/chat/completions"
req = urllib.request.Request(url, data=payload.encode(), headers={
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "http://localhost",
    "X-Title": "Video Analysis"
}, method='POST')
```

**⚠️ Limits & Gotchas**:
- Base64 inflates size by ~33% (5MB file → 6.7MB payload)
- 120s timeout recommended for video processing
- Free tier models rate-limit aggressively (HTTP 429)
- Qwen free tier returned: "temporarily rate-limited upstream"
- If file >5MB: use URL-based approach (Format 2)

### Format 2: URL-Based (Large Files, Recommended)
For files of any size — upload to a URL-accessible location first:

```python
payload = json.dumps({
    "model": "google/gemini-3.1-flash-lite-preview",
    "messages": [{
        "role": "user", 
        "content": [
            {"type": "video_url", "video_url": {"url": "https://your-cdn.com/video.mp4"}},
            {"type": "text", "text": "Analyze this video"}
        ]
    }],
    "max_tokens": 500
})
```

**Sources compatibles**: R2 (Cloudflare), S3 presigned URLs, any HTTPS URL, Google Drive direct links.

## R2 Upload Workflow (Zero Data Loss)

### Prerequisites
1. R2 must be **enabled via Cloudflare Dashboard** (cannot be done via API — error 10042)
2. API Token must have R2 permissions (Storage: Edit, Account: Read)

### Step 1: Create Bucket via Wrangler
```bash
export CLOUDFLARE_API_TOKEN="..."
export CLOUDFLARE_ACCOUNT_ID="..."
wrangler r2 bucket create walter-analysis
```

### Step 2: Create R2 API Token (for S3 uploads)
Via Cloudflare Dashboard → R2 → Manage R2 API Tokens → Create token with:
- Permissions: Object Read & Write
- Bucket: specific bucket or all
- Store credentials: Access Key ID + Secret Access Key

### Step 3: Upload via boto3
```python
import boto3
session = boto3.Session(
    aws_access_key_id='YOUR_ACCESS_KEY',
    aws_secret_access_key='YOUR_SECRET_KEY',
    region_name='auto'
)
client = session.client('s3', endpoint_url=f'https://{ACCOUNT_ID}.r2.cloudflarestorage.com')
client.upload_file('video.mp4', 'walter-analysis', 'videos/temp_video.mp4')

# Get public URL or presigned URL
url = client.generate_presigned_url('get_object',
    Params={'Bucket': 'walter-analysis', 'Key': 'videos/temp_video.mp4'},
    ExpiresIn=3600)
```

### Step 4: Send URL to LLM, Clean Up
```python
# After analysis, delete temp file
client.delete_object(Bucket='walter-analysis', Key='videos/temp_video.mp4')
```

## Recommended Strategy by Use Case

### TikTok/Social Media Ad Reference Video → Storyboard → Regeneration

This is the most common workflow: user receives TikTok reference videos and needs to regenerate them with AI video models (Seedance, Kling, Sora, etc.).

**End-to-end pipeline:**

1. **Download** TikTok videos with `yt-dlp -f "mp4" --merge-output-format mp4 "<url>"`
2. **Upload** to Google Drive via `google-api-python-client` for archival
3. **Analyze** with Gemini 2.5 Flash via OpenRouter (base64 if <5MB) → returns scene-by-scene breakdown with timestamps, visual descriptions, and AI prompts
4. **Storyboard** — generate 2 keyframes per scene (before/after) via Atlas Cloud `openai/gpt-image-2/text-to-image` (1080×1920 vertical)
5. **Generate clips** — use each storyboard keyframe as image reference with Seedance 2 via Kie.ai for 4-8s video clips
6. **Assemble** in postprod — stitch clips, add text overlays, match audio

```python
# Step 3: Analyze video for scene breakdown
# Uses the direct base64 pattern (see "Direct Base64 Usage" section)
# Model: google/gemini-2.5-flash
# max_tokens: 8000 (scene breakdowns are long)
```

### Short Videos (<10s) under 3MB → Direct Analysis
→ **Direct base64** with `google/gemini-3.1-flash-lite-preview` ($0.00000025/token)
- Fast, simple, zero infrastructure needed
- ~2min total from file to analysis

### Medium Videos (10-60s) 3-10MB  
→ **R2 URL** with `google/gemini-2.5-flash` or `gemini-3.1-pro-preview`
- Full video with audio, no data loss
- ~5min including upload time

### Large Videos (>10MB) or Batch Processing
→ **R2 URL + Whisper transcription** fallback
- Send URL to LLM for visual analysis
- Use Whisper for audio transcription as context injection
- Most comprehensive analysis

## Direct Base64 Usage (Recommended for videos <5MB)

For short TikTok/social media reference videos under 5MB, direct base64 is the fastest approach. Working pattern:

```python
import subprocess, json, requests, base64

r = subprocess.run(["vault", "get", "openrouter/api_key"], capture_output=True, text=True, check=True)
API_KEY = r.stdout.strip()

with open("video.mp4", "rb") as f:
    vid_b64 = base64.b64encode(f.read()).decode()

url = "data:video/mp4;base64," + vid_b64  # string concat, NOT f-string

payload = json.dumps({
    "model": "google/gemini-2.5-flash",
    "messages": [{
        "role": "user",
        "content": [
            {"type": "video_url", "video_url": {"url": url}},
            {"type": "text", "text": "Analyze this video"}
        ]
    }],
    "max_tokens": 8000,
    "temperature": 0.3
})

resp = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    data=payload.encode(),
    headers={
        "Authorization": "Bearer " + API_KEY,  # string concat — avoids f-string shell escaping bugs
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Video Analysis"
    },
    timeout=300
)
```

**Critical**: Write scripts to `.py` files and execute them. Do NOT use inline f-strings with shell heredocs — the `Authorization: Bearer {API_KEY}` pattern breaks with Python f-string parsing in shell contexts.

## Video Analysis Prompt Pattern

For breaking down social media ads (TikTok/Reels) into regeneratable scenes:

> "Analyse cette video avec precision sur le temps, decoupe en scenes de 3-15s max. Pour chaque scene donne: timestamp depart/fin, description visuelle detaillee (personnage, decor, mouvement), transitions, et un prompt en anglais pour un modele video IA."

This produces a shot-by-shot breakdown ready for independent generation + postprod assembly.

## Error Handling

```python
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
except urllib.error.HTTPError as e:
    body = json.loads(e.read())
    if e.code == 429:
        # Rate limited — retry with different model or wait
        if 'provider_name' in body.get('error', {}).get('metadata', {}):
            print(f"Rate limited by {body['error']['metadata']['provider_name']}")
        # Retry after delay or switch to BYOK
    elif e.code == 413 and 'Too large' in body.get('error', {}).get('message', ''):
        # Payload too large — use URL-based approach
        print("Base64 too large, switching to R2 URL")
```