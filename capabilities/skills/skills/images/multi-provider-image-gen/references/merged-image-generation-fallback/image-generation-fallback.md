---
name: multi-provider-image-gen
description: Multi-provider image generation with fallback chain — OpenAI Direct API → OpenAI Codex → Fal MCP → Atlas Cloud → Pollinations.ai (zero-key). Includes local serving trick for CLI delivery.
category: mlops
---

# Image Generation Fallback Chain

## Provider Priority (try in order)

1. **OpenAI Direct API** (`api.openai.com/v1/images/generations`) — premier choix si clef valide
   - **⚠️ TIMEOUT CRITICAL: must use `--max-time 120` or more for gpt-image-2. Generation takes 2-4 minutes. Default 30s curl WILL timeout.**
   - Connection (TCP/TLS) succeeds in ~1s; the response hangs until image is ready. **Do NOT confuse this with a network block.**
   - Auth: `Authorization: Bearer <sk-proj-...>` (vault: `openai/api_key`)
   - Payload: `{"model": "gpt-image-2", "prompt": "...", "size": "1024x1024", "quality": "low"}`
   - `size` values: `"1024x1024"`, `"1536x1024"`, `"1024x1536"`, etc.
   - `quality` values: `"low"`, `"medium"`, `"high"`
   - Response always PNG b64_json, ~500KB–5MB depending on quality/size
   - Response shape: `{"created": ts, "size": "...", "quality": "...", "output_format": "png", "usage": {...}, "data": [{"b64_json": "..."}]}`
   - No URL download — only base64. Save via Python: `base64.b64decode(data["data"][0]["b64_json"])`
   - Dashboard usage lag: tokens/cost show up 5-15 minutes after generation completes

2. **OpenAI Codex** (`image_generate` tool) — if available
   - May have 401/auth errors depending on current tier

3. **Fal MCP** (`fal-ai/nano-banana-2` via mcporter)
   - Verify MCP server is configured and auth is valid

3.5. **Higgsfield MCP** (`nano_banana_2_lite` or `nano_banana_2`) — async generation via MCP
   - Requires OAuth (see `hosted-mcp-oauth` skill for setup)
   - **Async only**: `generate_image` returns `status: "pending"` + job ID → poll `job_status(jobId)` → download `results.rawUrl`
   - ⚠️ `job_status` uses `jobId` (singular string), NOT `job_ids` (array)
   - ⚠️ Tool `show_jobs` does NOT exist — use `job_status`
   - Auth header: `Authorization: Bearer <access_token>` from `~/.hermes/mcp-tokens/higgsfield.tokens.json`
   - Full workflow in `hosted-mcp-oauth` skill → `references/higgsfield-model-catalog.md`

4. **Atlas Cloud** (`api.atlascloud.ai`) — ERNIE-Image-Turbo + GPT Image 2 + more
   - Image gen endpoint: `POST https://api.atlascloud.ai/api/v1/model/generateImage`
   - Poll endpoint: `GET https://api.atlascloud.ai/api/v1/model/prediction/{id}`
   - Auth: `Authorization: Bearer <ATLAS_KEY>` (vault: `atlas/api_key`)
   - **⚠️ Model names MUST include `/text-to-image` suffix**:
     - `baidu/ERNIE-Image-Turbo/text-to-image` (fast, ~9.5s/img, ~90% reliable)
     - `openai/gpt-image-2/text-to-image` (slower, ~17.6s/img, ~100% reliable)
   - Payload: `{"model": "...", "prompt": "...", "size": "1440x2560", "n": 1, "enable_sync_mode": false, "quality": "low"}`
   - ⚠️ Failed jobs return `"code": 200` with `"status": "failed"` — always check `data.status`
   - See skill `atlas-cloud-image-gen` for full async polling patterns, Python scripts, and benchmarks

5. **Pollinations.ai** (zero-key fallback) — dernier recours
   - Aucun API key requis, toujours disponible
   - URL: `https://image.pollinations.ai/prompt/{ENCODED_PROMPT}?width=1024&height=768&nologo=true`
   - Latence ~10-20s

## Pollinations.ai URL Parameters

| Param | Description |
|-------|-------------|
| `width` / `height` | Dimensions (défaut 1024x768) |
| `seed` | Reproductibilité |
| `nologo=true` | Retire le watermark |
| `negative_prompt` | URL-encoded negative prompt |

## Quick OpenAI Direct API Test

```bash
curl -s --connect-timeout 10 --max-time 120 \
  https://api.openai.com/v1/images/generations \
  -H "Authorization: Bearer $(vault get openai/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-image-2","prompt":"your prompt","size":"1024x1024","quality":"low"}' \
  -o /tmp/openai_img.json

python3 -c "
import json, base64
data = json.load(open('/tmp/openai_img.json'))
img = base64.b64decode(data['data'][0]['b64_json'])
open('/tmp/output.png','wb').write(img)
print(f'Saved {len(img)//1024}KB to /tmp/output.png')
"
```

## Local Serving for CLI Delivery

Quand le CLI ne supporte pas l'affichage d'image direct, servir localement:

```bash
python3 -c "
import http.server, os, threading, time
os.chdir('/tmp')
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
s = http.server.HTTPServer(('',9321),H)
t = threading.Thread(target=s.serve_forever,daemon=True)
t.start()
time.sleep(300)
" &
# Puis curl -so /dev/null -w "%{http_code}" http://localhost:9321/output.png
```

**Note**: Le port 8787 semblait conflictuel — pivoter vers 9321 ou autre port libre.

## Delivery Pattern for CLI

1. Generate vers `/tmp/output.png` (OpenAI = PNG, pas JPEG)
2. Servir localement sur un port libre
3. Retourner `http://localhost:{PORT}/output.png` au user
4. Le user ouvre dans son navigateur
