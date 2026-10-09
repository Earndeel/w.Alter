---
name: gemini-file-api
description: Upload files to Gemini File API for native analysis.
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux, macos]
metadata:
  hermes.tags: [gemini, video, multimodal, file-upload, analysis]
  hermes.category: mlops
---

# Gemini File API Skill

Upload files (video, audio, images) to Gemini's File API and analyze them with Gemini models. Use this instead of base64-encoding large files or using OpenRouter for video — Gemini handles files natively and is faster.

## When to Use

- Analyzing video files (product demos, recordings, tutorials)
- Transcribing or analyzing audio files
- Sending large images or documents to Gemini models
- Any task where base64-encoding a file >10MB into an API call is impractical

## Prerequisites

- `GEMINI_API_KEY` — on this system, it lives in `~/.hermes/hindsight/hybrid-search.env` (NOT in `auth.json`)
- `requests` or stdlib `urllib` — no extra dependencies needed

## Quick Reference

```
1. Upload file    → POST /upload/v1beta/files       → get file_uri
2. Poll status    → GET /v1beta/files/{name}          → wait for ACTIVE
3. Generate       → POST /v1beta/{model}:generateContent → get analysis
```

## Procedure

### Step 1: Upload the file

```python
import urllib.request, json, os

api_key = "..."  # from ~/.hermes/hindsight/hybrid-search.env
file_path = "/tmp/video.mp4"
boundary = "----FormBoundary7MA4YWxkTrZu0gW"
metadata = json.dumps({"file": {"display_name": os.path.basename(file_path)}})

body = (
    f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
    f"{metadata}\r\n"
    f"--{boundary}\r\nContent-Type: video/mp4\r\n\r\n"
).encode() + open(file_path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()

req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}",
    data=body,
    headers={
        "Content-Type": f"multipart/related; boundary={boundary}",
        "X-Goog-Upload-Protocol": "multipart",
    },
    method="POST"
)
result = json.loads(urllib.request.urlopen(req, timeout=120).read())
file_uri = result["file"]["uri"]
file_name = result["file"]["name"]  # e.g. "files/abc123"
state = result["file"]["state"]     # "PROCESSING"
```

### Step 2: Wait for ACTIVE state

```python
import time
while state == "PROCESSING":
    time.sleep(5)
    check_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    state = json.loads(urllib.request.urlopen(check_url).read())["state"]
# state is now "ACTIVE" — ready for generation
```

Typical wait: 5-10 seconds for a 40MB video.

### Step 3: Generate with the file

```python
models = [
    "models/gemini-2.5-flash-lite",  # try lite first (cheaper)
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash",
]

for model in models:
    gen_url = f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [
            {"text": "Your analysis prompt here..."},
            {"file_data": {"mime_type": "video/mp4", "file_uri": file_uri}}
        ]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192}
    }
    req = urllib.request.Request(gen_url, data=json.dumps(payload).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        result = json.loads(urllib.request.urlopen(req, timeout=180).read())
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        break  # success
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        continue
```

### Model Selection Strategy

| Model | Best For | Cost |
|-------|----------|------|
| `gemini-2.5-flash-lite` | General video analysis, summaries | Lowest |
| `gemini-2.5-flash` | Detailed analysis, longer responses | Low |
| `gemini-2.0-flash` | Fallback if 2.5 unavailable | Low |

Try in order: lite → flash → 2.0 flash. Most video analysis tasks work perfectly on lite.

## Pitfalls

### API key location
On this system, `GEMINI_API_KEY` is NOT in `~/.hermes/auth.json`. It lives in `~/.hermes/hindsight/hybrid-search.env`. Read the env file directly.

### File size limits
- Gemini File API accepts files up to 2GB
- Files expire after 48 hours (check `expirationTime` in upload response)
- No need to compress video — 40MB+ files work fine

### Model name format
Always use the full path: `models/gemini-2.5-flash-lite`, NOT `gemini-2.5-flash-lite`.

### Don't use OpenRouter for video
OpenRouter requires base64-encoding video inline (slow, 90-130s for 40MB). Gemini File API handles it natively (30-60s total). Always prefer Gemini.

## Verification

After generation, confirm:
- `result["candidates"][0]["content"]["parts"][0]["text"]` contains the analysis
- `result.get("usageMetadata")` shows token counts
- File is marked for auto-deletion at `expirationTime`
