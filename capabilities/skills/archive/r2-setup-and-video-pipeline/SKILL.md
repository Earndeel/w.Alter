---
name: r2-setup-and-video-pipeline
category: cloud
description: 'Set up Cloudflare R2 via API/wrangler for video storage, create buckets, Worker upload endpoint, and integrate with OpenRouter video analysis pipeline'
---

# R2 Setup & Video Analysis Pipeline (WALTER)

## Prerequisites
1. Cloudflare account must have **R2 enabled via Dashboard** (cannot enable via API -- error 10042)
2. Wrangler CLI configured with API token with **WRITE permissions** (Workers Edit + Pages Write)
3. OpenRouter API key for video analysis
4. Credentials in `/root/.mcporter/mcporter.json`

## CRITICAL: CF Token Permission Limitations
The token in `/root/.mcporter/mcporter.json` is **READ-ONLY** (cfut_ prefix, token ID: 632d027acf474cdeea3eb56cc116f427):
- **GET requests work**: `wrangler whoami` OK, list projects OK, token verify OK
- **PUT/POST/DELETE requests FAIL**: 
  - `wrangler pages deploy` → error 10000 (auth error for this operation)
  - Workers API → error 10405 "Method not allowed for this authentication scheme"
  - Pages deployments API → error 8000096 (manifest expected but rejected)
- This is a **token permission issue**, not an auth bug. The token was generated with limited permissions (likely Workers Read only).
- **Solution**: Generate a new token at https://dash.cloudflare.com/profile/api-tokens with "Edit Cloudflare Workers" template, or add Workers Edit + Pages Write permissions manually.
- **Wrangler CLI env var conflict**: If `~/.hermes/config.yaml` has `delegation.base_url` set to OpenRouter, and you pass `CLOUDFLARE_API_TOKEN` as env var, wrangler may still read from stale config. Always verify with `CLOUDFLARE_API_TOKEN=xxx wrangler whoami` first. If you get "You are not authenticated", the env var isn't being picked up (wrangler uses `~/.wrangler/` state directory for session auth, env vars are secondary).

## Critical Error Codes
- **Error 10042**: "Please enable R2 through the Cloudflare Dashboard" -- R2 not activated
- **Error 10015**: "No route matches this url" -- R2 not enabled, API endpoint doesn't exist
- Sandbox Python `urllib` **403 on R2 Dev URLs** -- use `curl` instead (DNS restriction)

## Setup Steps

### 1. Enable R2 via Dashboard (manual only)
- Go to https://dash.cloudflare.com → R2 → Enable R2

### 2. Get Credentials
```python
import json
with open('/root/.mcporter/mcporter.json') as f:
    cfg = json.load(f)
    env = cfg['mcpServers']['cloudflare']['env']
    CF_TOKEN = env['CLOUDFLARE_API_TOKEN']
    CF_ACCOUNT_ID = env['CLOUDFLARE_ACCOUNT_ID']
```

### 3. Create Bucket via Wrangler
```bash
wrangler r2 bucket create <bucket-name>
wrangler r2 bucket info <bucket-name>
```

### 4. Enable Dev URL (public access via subdomain)
```bash
wrangler r2 bucket dev-url enable <bucket-name>
```
This creates a public URL: `https://pub-<hash>.r2.dev/<key>`
**No authentication needed, no presigned URLs required.**

---

## R2 Upload via Worker (SIMPLIFIED APPROACH)

### Why Worker instead of S3 API?
- S3-compatible R2 API requires creating Access Keys + HMAC signatures -- complex and brittle
- Worker with R2 binding is **one JS file** -- no keys, no signing, no boto3 needed
- **Uploads complete in ~1.6s for 5MB files**

### Worker Setup

**`wrangler.toml`:**
```toml
name = "walter-r2-upload"
main = "index.js"
compatibility_date = "2024-01-01"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "walter-analysis"
```

**`index.js`:**
```javascript
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = url.searchParams.get('key');
    
    if (!key) return new Response('Missing key', { status: 400 });
    
    if (request.method === 'POST') {
      // Upload
      const contentType = request.headers.get('content-type') || 'application/octet-stream';
      await env.BUCKET.put(key, request.body, { httpMetadata: { contentType } });
      const publicUrl = `https://pub-05185774c7984ece8e08d264dcad0fac.r2.dev/${key}`;
      return Response.json({ ok: true, key, url: publicUrl });
    }
    
    if (request.method === 'DELETE') {
      // Delete
      await env.BUCKET.delete(key);
      return Response.json({ ok: true, key });
    }
    
    if (request.method === 'GET' && url.pathname === '/test') {
      // List objects
      const listing = await env.BUCKET.list();
      return Response.json(listing.objects.map(o => ({ key: o.key, size: o.size })));
    }
    
    return new Response('Not found', { status: 404 });
  }
};
```

### Deploy
```bash
cd /tmp/cf-deploy-<uuid>  # Isolated dir (wrangler scans recursively!)
wrangler deploy
```

**Endpoint:** `POST https://walter-r2-upload.lucas-jouvencon.workers.dev/upload?key=<filename>`

Content-Type: `video/mp4` or `application/octet-stream`

**Response:** `{"ok":true, "key":"...", "url":"https://pub-<hash>.r2.dev/<key>"}`

### Upload from Python (use `curl` -- sandbox urllib fails on R2 Dev URLs!)
```python
import subprocess, json

def upload_to_r2(file_path: str, key: str) -> str:
    """Upload via Worker. Uses curl (sandbox urllib gets 403 on r2.dev)."""
    r = subprocess.run([
        "curl", "-s", "-X", "POST", 
        f"https://walter-r2-upload.lucas-jouvencon.workers.dev/upload?key={key}",
        "-H", "Content-Type: video/mp4",
        "--data-binary", f"@{file_path}"
    ], capture_output=True, text=True, timeout=300)
    result = json.loads(r.stdout)
    if not result.get("ok"):
        raise Exception(f"Upload failed: {result}")
    return result["url"]

def delete_from_r2(key: str):
    """Delete via Worker."""
    r = subprocess.run([
        "curl", "-s", "-X", "DELETE",
        f"https://walter-r2-upload.lucas-jouvencon.workers.dev/delete?key={key}"
    ], capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout).get("ok", False)
```

### Upload Performance
- 5MB video: **~1.6s** via curl → Worker → R2
- Public URL immediately accessible (verified with `HEAD 200`)

---

## Video Analysis Pipeline (with R2)

### Key Decision: Video URL + Frames, NOT base64-only
- **Abandoned:** base64 encoding of full video (5MB → ~7MB base64, impractical payload)
- **Adopted:** Upload video to R2 → send public URL to OpenRouter → delete after analysis
- OpenRouter `video_url` type works with `qwen/qwen3.6-plus:free`, `google/gemini-3.1-flash-lite-preview`, `anthropic/claude-sonnet-4-20250514`
- **Enhanced with 12 extracted frames** for key-moment precision

### Frame Extraction
```bash
# 12 frames evenly spaced across video duration
dur=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 video.mp4)
interval=$(echo "$dur / 13" | bc -l)  # div N+1 for even spacing

ffmpeg -y -i video.mp4 \
  -vf "fps=1/$interval:round=down" \
  -frames:v 12 -q:v 2 frame_%03d.jpg
```

### OpenRouter Payload (Video URL + Frames)
```python
import os, json, urllib.request

API_KEY = os.environ.get('OPENROUTER_API_KEY', '')

content = [
    {"type": "text", "text": "Analyse vidéo publicitaire: card 1, durée=31.9s, 12 frames clé"},
    {"type": "video_url", "video_url": {"url": "https://pub-xxx.r2.dev/card_1.mp4"}},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<frame1>"}},
    {"type": "text", "text": "[Frame 1/12 ~2.7s]"},
    # ... repeat for each frame
    {"type": "text", "text": "<prompt template content here>"}
]

payload = {
    "model": "qwen/qwen3.6-plus:free",
    "messages": [{"role": "user", "content": content}],
    "max_tokens": 8000
}

req = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps(payload).encode('utf-8'),
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/walter",
        "X-Title": "W.Alter-Pipeline"
    }
)
result = json.loads(urllib.request.urlopen(req, timeout=180).read())
```

### Pipeline Flow (3 steps)
1. **Upload R2** → `upload_to_r2(video_path, key)` → ~2s → get public URL
2. **Extract frames + analyze** → 12 frames → build payload → call OpenRouter → 30-60s
3. **Cleanup** → `delete_from_r2(key)` → save analysis to `video_analysis` DB table

### Sandbox Warning
- **`urllib` on `r2.dev` URLs → 403 Forbidden** (sandbox DNS restriction)
- **Use `curl` via `subprocess.run()`** for all R2 network calls from Python
- OpenRouter calls via `urllib` work fine (different domain)

---

## Troubleshooting

### R2 Enable (Error 10042/10015)
Must enable via dashboard. API cannot enable R2.

### Sandbox Python 403 on R2 URLs
Use `curl` via subprocess. `urllib.request.urlopen()` on `pub-*.r2.dev` returns 403.

### Worker Deploy
Always deploy from isolated `/tmp/cf-deploy-<uuid>/` directory. `wrangler deploy` scans recursively and will break if `node_modules` or huge files exist.

### Upload Fails (>100MB limit)
Cloudflare Workers have 100MB request body limit. Videos in pipeline are ~5MB -- well within limit.
