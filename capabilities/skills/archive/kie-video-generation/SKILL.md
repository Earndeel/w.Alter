---
name: kie-video-generation
description: Kie.ai video generation API integration — Seedance 2.0, Seedance 2.0 Fast, Kling, Hailuo, Wan, Sora2, and other video models via unified task API.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [video, generation, kie, seedance, bytedance, api]
---

# Kie.ai Video Generation

Unified video generation via Kie.ai marketplace API. Cheaper alternative to Fal.ai for ByteDance Seedance 2.0 and other video models.

## Authentication

```bash
vault get kie/api_key
# Header: Authorization: Bearer <token>
```

For Cloudflare Workers, upload as a secret:
```bash
echo "$KIE_KEY" | npx wrangler secret put KIE_API_KEY --name scena-api
```

## Base URL

```
https://api.kie.ai/api/v1/jobs/createTask
```

## Reference Files

- `references/api.md` — Full parameter table, mutual exclusivity rules, pricing context
- `references/gpt-image-2-i2i.md` — GPT Image 2 Image-to-Image API details, polling patterns, input format differences from T2I
- `references/common-api.md` — Credits, download URLs, webhook verification, rate limits, retention policy
- `references/pricing-comparison.md` — Live-derived Claude/Chat pricing vs OpenRouter, credit-to-USD conversions, account balance endpoint
- `references/kling-pricing-cross-provider.md` — Kling video pricing: fal.ai vs kie.ai, all versions, empirical cost measurement method
- `references/gpt-image-2-i2i-workflow.md` — Product creative workflow: I2I with real product references, format requirements, prompt strategy
- `references/grok-imagine-i2v.md` — Grok Imagine Image-to-Video API details (payload, polling, parameters)
- `scripts/test.py` — Quick API validation script (supports `--poll`)
- `scripts/check-credits.sh` — One-liner credit balance check

## Query Endpoints

Kie.ai currently has two task-detail endpoints depending on model family:

```bash
# Legacy/video endpoint used by older integrations such as Seedance tests
GET /api/v1/jobs/getTaskDetail?taskId=<taskId>

# Market unified endpoint used by newer Market models such as z-image
GET /api/v1/jobs/recordInfo?taskId=<taskId>
```

For production, prefer `callBackUrl` instead of polling. If `getTaskDetail` returns 404 for a Market model, retry `recordInfo`.

## Supported Video Models

| Model | ID | Use Case |
|-------|-----|----------|
| **Grok Imagine T2V** | `grok-imagine/text-to-video` | Grok-powered text-to-video |
| **Grok Imagine I2V** | `grok-imagine/image-to-video` | Image-to-video with prompt; supports `image_urls`, `prompt`, `mode`, `duration`, `resolution`, `aspect_ratio` |
| **Grok Imagine Upscale** | `grok-imagine/upscale` | Video upscaling |
| **Grok Imagine Extend** | `grok-imagine/extend` | Video extension |
| Seedance 2.0 | `bytedance/seedance-2` | High quality, text/image-to-video |
| Seedance 2.0 Fast | `bytedance/seedance-2-fast` | Faster generation, same features |
| Seedance 1.5 Pro | `bytedance/seedance-1-5-pro` | Previous gen |
| Bytedance V1 Pro | `bytedance/v1-pro-text-to-video`, `bytedance/v1-pro-image-to-video` | Legacy |
| Bytedance V1 Lite | `bytedance/v1-lite-text-to-video`, `bytedance/v1-lite-image-to-video` | Cheaper legacy |
| Grok Imagine | `grok-imagine/text-to-video`, `grok-imagine/image-to-video`, `grok-imagine/upscale`, `grok-imagine/extend` | Grok video suite |
| Kling 2.5 Turbo Pro | `kling/v2-5-turbo-text-to-video-pro`, `kling/v2-5-turbo-image-to-video-pro` | Older turbo tier (T2V + I2V) |
| Kling 3.0 | `kling/kling-3-0` | Latest Kling |
| Kling 2.6 | `kling/text-to-video`, `kling/image-to-video` | Standard Kling |
| Hailuo 2.3 Pro | `hailuo/2-3-image-to-video-pro`, `hailuo/02-text-to-video-pro` | Hailuo |
| Wan 2.7 | `wan/2-7-text-to-video`, `wan/2-7-image-to-video` | Wan series |
| Sora2 | `sora2/sora-2-text-to-video`, `sora2/sora-2-image-to-video` | Sora2 |

## Supported Chat / LLM Models

Kie.ai routes major chat models through unified endpoints. Pricing is **~2–4× cheaper** than OpenRouter for equivalent models.

### Claude Models (Anthropic Messages format)

| Model | ID | Endpoint | Notes |
|-------|-----|----------|-------|
| Claude Opus 4.6 | `claude-opus-4-6` | `POST /claude/v1/messages` | Anthropic Messages API format; supports `tools`, `stream`, `thinkingFlag` |
| Claude Opus 4.7 | `claude-opus-4-7` | `POST /claude/v1/messages` | Latest Opus |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | `POST /claude/v1/messages` | Fast, cheaper |
| Claude Sonnet 4.5 | `claude-sonnet-4-5` | `POST /claude/v1/messages` | Previous gen |
| Claude Haiku 4.5 | `claude-haiku-4-5` | `POST /claude/v1/messages` | Cheapest Claude tier |

### GPT Models (OpenAI-compatible)

| Model | ID | Endpoint | Notes |
|-------|-----|----------|-------|
| GPT 5.5 | `gpt-5-5` | `POST /chat/v1/messages` | OpenAI-compatible |
| GPT 5.4 | `gpt-5-4` | `POST /chat/v1/messages` | |
| GPT 5.2 | `gpt-5-2` | `POST /chat/v1/messages` | |
| GPT Codex | `gpt-codex` | `POST /chat/v1/messages` | Coding agent |

### Gemini Models (per-model OpenAI-compatible endpoints)

**Each Gemini model has its OWN endpoint with the model name in the URL path.**

| Model | Endpoint | Verified |
|-------|----------|----------|
| **Gemini 3.5 Flash** | `POST /gemini-3-5-flash-openai/v1/chat/completions` | 2026-06-02 |
| **Gemini 3.1 Pro** | `POST /gemini-3.1-pro/v1/chat/completions` | 2026-06-02 |
| Gemini 3 Flash | `POST /gemini-3-flash/v1/chat/completions` | via model-name URL |
| Gemini 3 Pro | `POST /gemini-3-pro/v1/chat/completions` | via model-name URL |
| Gemini 2.5 Flash | `POST /gemini-2.5-flash/v1/chat/completions` | via model-name URL |
| Gemini 2.5 Pro | `POST /gemini-2.5-pro/v1/chat/completions` | via model-name URL |

**Pattern:** `POST https://api.kie.ai/{model-name}/v1/chat/completions` with OpenAI chat completions body.

**Gemini 3.5 Flash naming:** URL uses `gemini-3-5-flash-openai` (hyphens + `-openai` suffix). The `model` field in the body can be `gemini-3-5-flash` or `gemini-3-5-flash-openai` (both work).

**Gemini 3.1 Pro naming:** URL uses dots `gemini-3.1-pro`, NOT hyphens `gemini-3-1-pro` (hyphens return 422).

**Hermes provider config:**
```yaml
providers:
  kie-gemini-pro:
    api: https://api.kie.ai/gemini-3.1-pro
    api_mode: chat_completions
    default_model: gemini-3.1-pro
    key_env: KIE_API_KEY
    models: [gemini-3.1-pro]
    name: Kie.ai Gemini 3.1 Pro
  kie-gemini-flash:
    api: https://api.kie.ai/gemini-3-5-flash-openai
    api_mode: chat_completions
    default_model: gemini-3-5-flash
    key_env: KIE_API_KEY
    models: [gemini-3-5-flash]
    name: Kie.ai Gemini 3.5 Flash
```

**Google native format (alternative):** Gemini 3.5 Flash also works via `POST /gemini/v1/models/gemini-3-5-flash:generateContent` with Google's native `contents/parts` payload. NOT compatible with Hermes's OpenAI transport.

### Gemini Pricing on Kie.ai

Both Gemini models cost **0.01 credits/call** (~$0.00005 USD) for short requests. At 1 credit approx $0.005, extremely cheap.

### Claude API Example

```bash
curl -s -X POST https://api.kie.ai/claude/v1/messages \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 4096,
    "stream": false
  }'
```

Response shape:
```json
{
  "role": "assistant",
  "usage": {"input_tokens": 12, "output_tokens": 4},
  "stop_reason": "end_turn",
  "model": "claude-opus-4-6",
  "credits_consumed": 0.01,
  "content": [{"text": "Hello", "type": "text"}]
}
```

Key fields:
- `credits_consumed` — Kie.ai internal credit cost for the call
- `usage.input_tokens` / `usage.output_tokens` — token counts
- Supports `tools` (function calling), `thinkingFlag`, `stream: true` (SSE)

## Supported Image Models

| Model | ID | Use Case |
|-------|-----|----------|
| GPT Image 2 Text-to-Image | `gpt-image-2-text-to-image` | Preferred Scena production image provider via Kie.ai |
| GPT Image 2 Image-to-Image | `gpt-image-2-image-to-image` | Preferred Scena production image-to-image provider via Kie.ai |
| Z-Image | `z-image` | Cheap test/benchmark model only; do **not** route Scena production image jobs to it |

### GPT Image 2 Image-to-Image (Preferred for Product Creatives)

**Best for: generating ecommerce product photos from real product reference images.** Unlike text-to-image, I2I preserves the actual product design, color, and shape — critical when making landing page creatives for dropshipping products.

**Workflow:**
1. Download the actual product photos from the source (e.g. AliExpress)
2. Convert AVIF/WebP to PNG (Kie rejects `.avif` with "File type not supported")
3. Upload PNGs to a public URL (e.g. deploy to a staging Pages site, or any public CDN)
4. Submit I2I task referencing the PNG URL
5. Download results and compress JPEG (85 quality, 1024px max) to avoid multi-MB page loads

Submission pattern for I2I:
```json
{
  "model": "gpt-image-2-image-to-image",
  "input": {
    "prompt": "Style/context transformation while keeping the EXACT same product...",
    "input_urls": ["https://public-hosting.example.com/ref_product.png"],
    "aspect_ratio": "1:1",
    "resolution": "1K"
  }
}
```

**Resolution:** Use `1K` not `2K` for web landing pages. 2K images are 3-5MB each (PNG), which breaks page load and causes layout issues. After generation, convert to JPEG at quality 85 with 1024px max dimension → ~50-200KB each.

**Critical prompt tip:** Include "this exact ..." and "maintain identical product shape, color and design details" in the prompt so GPT Image 2 doesn't hallucinate a different product.

**Polling for I2I results:**
```bash
GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<taskId>
# Response: data.state = "success" → data.resultJson → resultUrls[0] = image URL
# Download from tempfile.aiquickdraw.com within 20 min (presigned URLs expire)
```

### GPT Image 2 Pitfalls

- **"File type not supported" error** — GPT Image 2 I2I does NOT accept `.avif` files (common from AliExpress). Convert references to PNG/JPG before submitting: `Image.open(src).save(dst, "PNG")`.
- **Resolution matters for web output** — Use `"resolution": "1K"` for website assets. `"2K"` produces 3-5MB files (too heavy for Pages). 1K gives ~50-200KB after JPEG compression at quality 85. A 75MB site (17 x 2K PNGs) caused a broken page because images never loaded.
- **Post-processing mandatory** — Even 1K I2I output is PNG at several MB. Compress after download: resize to 1024px max, convert to JPEG quality 85 via PIL.
- **Input URLs must be publicly accessible** — Kie.ai I2I fetches from your `input_urls`. Host reference images somewhere with public CDN access (e.g. your Pages deployment, R2, etc.) before submitting I2I tasks. `.avif` format is rejected even if publicly accessible.
- **Transparent background I2I** — GPT Image 2 cannot produce true transparency via I2I — it outputs a white/colored background regardless. For "remove background" requests, use proper background removal tools after generation.
- **I2I subtly changes the product** — Even with exact reference images, GPT Image 2 I2I alters product geometry slightly. For hero/product shots where fidelity matters: let the user review and be ready to accept their manually provided replacement image.
- **Transparent background limitation** — GPT Image 2 I2I cannot produce true alpha transparency. If asked for "transparent background", generate on solid white/colored background first, then apply a separate background removal tool, or simply accept the user's hand-provided transparent PNG as a replacement.
- **Background-removal I2I prompt strategy** — To remove a background via I2I, prompt with: "Remove the background completely. Keep the exact product as-is with identical colors, shape and details. Make the background plain white (for later removal)." Do NOT ask GPT I2I to "make it transparent" — it will hallucinate a different product on a colored background instead.

### GPT Image 2 Request Bodies

Text-to-image:

```json
{
  "model": "gpt-image-2-text-to-image",
  "callBackUrl": "https://api.walter-ai.cloud/webhook/saas/kie",
  "input": {
    "prompt": "A premium campaign visual...",
    "aspect_ratio": "auto",
    "resolution": "1K"
  }
}
```

Image-to-image:

```json
{
  "model": "gpt-image-2-image-to-image",
  "callBackUrl": "https://api.walter-ai.cloud/webhook/saas/kie",
  "input": {
    "prompt": "Create a polished campaign visual...",
    "input_urls": ["https://cdn.example/product.png"],
    "aspect_ratio": "auto"
  }
}
```

Required fields:
- T2I: `model`, `input.prompt`
- I2I: `model`, `input.prompt`, `input.input_urls`

Supported optional fields:
- `input.aspect_ratio`: `"auto"` (default), `"1:1"`, `"9:16"`, `"16:9"`, `"4:3"`, `"3:4"`
- `input.resolution`: `"1K"` (default), `"2K"`, `"4K"`

**Resolution constraints:**
- 1:1 ratio → cannot use 4K (task creation fails)
- `auto` or no aspect_ratio → limited to 1K only
- For 2K or 4K: **must** specify an explicit `aspect_ratio` (not "auto")

Unlike Atlas Cloud (which exposes OpenAI-native `size` in pixels + `quality` low/med/high), Kie.ai abstracts resolution to the 1K/2K/4K enum and does not expose a `quality` parameter.

### GPT Image 2 I2I — Product Reference Workflow

For generating product marketing images that match the **exact** product from supplier/AliExpress photos, use **image-to-image** (not text-to-image). T2I hallucinates product designs; I2I preserves the real product identity while transforming background, lighting, and context. See `references/gpt-image-2-i2i-workflow.md` for the full workflow including image format requirements, hosting strategy, and prompt patterns.

Key rule: **always use real product photos as `input_urls` reference**, never generate from text prompts alone.

### Z-Image Request Body

Endpoint:

```bash
POST https://api.kie.ai/api/v1/jobs/createTask
```

Payload:

```json
{
  "model": "z-image",
  "callBackUrl": "https://your-domain.com/api/callback",
  "input": {
    "prompt": "Photorealistic premium product advertising image...",
    "aspect_ratio": "1:1",
    "nsfw_checker": true
  }
}
```

Required input fields:
- `prompt` string, max 1000 chars
- `aspect_ratio`: `1:1`, `4:3`, `3:4`, `16:9`, `9:16`

Optional:
- `nsfw_checker` boolean

Successful create response example:

```json
{"code":200,"msg":"success","data":{"taskId":"...","recordId":"..."}}
```

Poll with Market endpoint:

```bash
curl "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=$TASK_ID" \
  -H "Authorization: Bearer $(vault get kie/api_key)"
```

Successful result contains `data.state="success"` and `data.resultJson`, e.g. `{"resultUrls":["https://..."]}`.

## Request Body Schema

```json
{
  "model": "bytedance/seedance-2",
  "callBackUrl": "https://your-domain.com/api/callback",
  "input": {
    "prompt": "A serene beach at sunset...",
    "first_frame_url": "https://...png",
    "last_frame_url": "https://...png",
    "reference_image_urls": ["https://...png"],
    "reference_video_urls": ["https://...mp4"],
    "reference_audio_urls": ["https://...mp3"],
    "return_last_frame": false,
    "generate_audio": false,
    "resolution": "720p",
    "aspect_ratio": "16:9",
    "duration": 15,
    "web_search": false
  }
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | ✅ | Model ID (see table above) |
| `callBackUrl` | string | ❌ | Webhook URL for completion notifications |
| `input.prompt` | string | ✅ | Text description of the video |
| `input.first_frame_url` | string | ❌ | First frame image URL (Image-to-Video) |
| `input.last_frame_url` | string | ❌ | Last frame image URL |
| `input.reference_image_urls` | string[] | ❌ | Reference images for style/character |
| `input.reference_video_urls` | string[] | ❌ | Reference videos for motion/style |
| `input.reference_audio_urls` | string[] | ❌ | Reference audio for lip-sync/sound |
| `input.return_last_frame` | boolean | ❌ | Return last frame image (default: false) |
| `input.generate_audio` | boolean | ❌ | Generate audio for video (default: false) |
| `input.resolution` | string | ❌ | `720p`, `1080p` (model-dependent) |
| `input.aspect_ratio` | string | ❌ | `16:9`, `9:16`, `1:1`, `3:4`, `4:3` |
| `input.duration` | integer | ❌ | Duration in seconds (5-15 typical) |
| `input.web_search` | boolean | ❌ | Enable web search augmentation (default: false) |

### ⚠️ Mutual Exclusivity Rules

- **Image-to-Video (First Frame)**, **Image-to-Video (First & Last Frames)**, and **Multimodal Reference-to-Video** are **mutually exclusive** — cannot be used simultaneously.
- If you need strict first/last frame matching, use `first_frame_url` + `last_frame_url`.
- For "First/Last Frame + Multimodal Reference" effect, use reference images via prompts in multimodal mode.

## Quick Start Examples

### Text-to-Video (Seedance 2.0)

```bash
curl -X POST https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bytedance/seedance-2",
    "input": {
      "prompt": "A serene beach at sunset with waves gently crashing",
      "resolution": "720p",
      "aspect_ratio": "16:9",
      "duration": 10
    }
  }'
```

### Image-to-Video (Grok Imagine)

```bash
curl -X POST https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine/image-to-video",
    "input": {
      "image_urls": ["https://example.com/image.png"],
      "prompt": "Subtle natural movement, cinematic slow motion",
      "mode": "normal",
      "resolution": "480p",
      "aspect_ratio": "16:9",
      "duration": "6"
    }
  }'
```

### Image-to-Video (Seedance 2.0 Fast)

```bash
curl -X POST https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bytedance/seedance-2-fast",
    "input": {
      "prompt": "Camera slowly zooms in on the subject",
      "first_frame_url": "https://example.com/image.png",
      "resolution": "720p",
      "aspect_ratio": "9:16",
      "duration": 5
    }
  }'
```

### Test Script

```bash
python3 ~/.hermes/scripts/test-kie-api.py        # Quick key validation
python3 ~/.hermes/scripts/test-kie-api.py --poll  # Full generation + polling
```

### With Webhook (Production)

```bash
curl -X POST https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bytedance/seedance-2",
    "callBackUrl": "https://api.walter-ai.cloud/webhook/kie",
    "input": {
      "prompt": "A product showcase video",
      "resolution": "1080p",
      "aspect_ratio": "16:9",
      "duration": 15,
      "generate_audio": true
    }
  }'
```

## Polling for Results

```bash
TASK_ID="task_bytedance_1765186743319"
curl "https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId=$TASK_ID" \
  -H "Authorization: Bearer $(vault get kie/api_key)"
```

## Scena Integration Notes

- Kie.ai uses **task-based async API** (like Fal but with explicit task IDs)
- Use `callBackUrl` for production — no polling needed
- `taskId` format: `task_bytedance_<timestamp>`
- Response format: `{ code: 200, msg: "success", data: { taskId } }`
- See `scena-cloudflare-serverless` skill for the full "Adding a New Video Provider" pattern

## Common API Account & Download URL

Check remaining credit balance:
```bash
curl -s -H "Authorization: Bearer $(vault get kie/api_key)" \
  https://api.kie.ai/api/v1/chat/credit
```

**⚠️ Download URL endpoint field name: `"url"`, NOT `"file_url"`**
The `POST /api/v1/common/download-url` endpoint requires `{"url": "..."}`:
```bash
curl -s -X POST https://api.kie.ai/api/v1/common/download-url \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://tempfile.aiquickdraw.com/.../video.mp4"}'
```
Returns a 20-min presigned Cloudflare R2 URL. Passing `file_url`, `video_url`, or other field names returns `"图片url不能为空"`.

Other Common API utilities:
- `POST /api/v1/common/webhook-verification` — verify webhook signatures
- Docs: https://docs.kie.ai/common-api/quickstart

## Account & Credits

Check your remaining credit balance via the Common API:

```bash
curl -s -H "Authorization: Bearer $(vault get kie/api_key)" \
  https://api.kie.ai/api/v1/chat/credit
```

Response:
```json
{"code":200,"msg":"success","data":879.7}
```

> The `data` field is a float representing remaining credits. As of May 2026, Lucas's balance was 879.7.

Other Common API utilities:
- `POST /api/v1/common/download-url` — generate 20-min temporary download link for generated files
- `POST /api/v1/common/webhook-verification` — verify webhook signatures
- Docs: https://docs.kie.ai/common-api/quickstart

## Documentation & Discovery

Official docs live at **https://docs.kie.ai** (Apidog-generated). Key sections:
- `/common-api/quickstart` — credits, download URLs, webhook verification
- `/market/quickstart` — model marketplace overview
- `/file-upload-api/quickstart` — upload assets for generation
- Model-specific pages under `/market/<provider>/<model>/`

## ⚠️ Pitfall: Pricing Page is an Unscrapable SPA

The `/pricing` page (https://kie.ai/pricing) is a Next.js SPA with **321 pricing entries** paginated across 13 pages (25/page). It has a JS-driven search bar ("Search by model, modality, or provider...") but NO static API endpoint behind it. Neither `mcp_scrapling_fetch`, `mcp_scrapling_stealthy_fetch`, nor `mcp_scrapling_bulk_get` can paginate or search — they only return the first 25 entries. The `browser_navigate` tool times out on kie.ai.

**To find a specific model's pricing:**
1. Ask the user to search manually on `kie.ai/pricing` — after 2 failed scraping attempts, stop and ask
2. Do a live credit-consumption test (submit task, check balance before/after)
3. 1 credit ≈ $0.005 USD (derived from Claude pricing probes)

## Pricing Context

**1 Kie.ai credit ≈ $0.005 USD** (derived from observed consumption: ~0.20 credits for a 45+130 token call).

See `references/kling-pricing-comparison.md` for Kling video pricing comparison across fal.ai and kie.ai.

### Claude Opus 4.6 — Kie.ai vs OpenRouter

| | OpenRouter | Kie.ai |
|---|---|---|
| Input | $5.00 / M tokens | ~$2.00–2.50 / M tokens |
| Output | $25.00 / M tokens | ~$7.00–7.50 / M tokens |
| **1M in + 1M out** | **$30** | **~$9** |

Kie.ai is roughly **3× cheaper** than OpenRouter for Claude Opus 4.6.

### How to verify current prices

Token-based pricing is not published statically. Derive it empirically:

```bash
# Small probe (isolated input cost)
curl -s -X POST https://api.kie.ai/claude/v1/messages \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4-6","messages":[{"role":"user","content":"Say hi"}],"max_tokens":1}' \
  | jq '{credits: .credits_consumed, in: .usage.input_tokens, out: .usage.output_tokens}'

# Large probe (output-heavy)
curl -s -X POST https://api.kie.ai/claude/v1/messages \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-opus-4-6","messages":[{"role":"user","content":"Write a long essay about quantum computing"}],"max_tokens":4000}' \
  | jq '{credits: .credits_consumed, in: .usage.input_tokens, out: .usage.output_tokens}'
```

Solve the linear system from the two probes to get $/token for input and output.

### Video / Image pricing

- Seedance 2.0 via Kie.ai is **significantly cheaper** than equivalent quality via Fal.ai
- Exact per-generation cost in credits: check https://kie.ai/market (dynamic pricing)
- Fal.ai credits exhausted as of April 2026 — Kie.ai is the cost-effective replacement

See `references/pricing-comparison.md` for full research notes.

## Related Skills

- `vault-lookup` — retrieve `kie/api_key`
- `scena-cloudflare-serverless` — integrate Kie.ai into the Scena pipeline
- `fal-image-generation` — Fal.ai alternative (credits exhausted)
- `multi-model-video-pipeline` — route between providers
