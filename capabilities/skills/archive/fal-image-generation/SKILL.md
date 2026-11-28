---
name: fal-image-generation
description: Fal.ai image generation API — text-to-image and image-to-image/edit with NanoBanana 2 and Flux models. Payload formats, pitfalls, and correct parameter names.
category: mlops
---

# Fal.ai Image Generation

## Endpoints

### ⚡ SYNC vs ASYNC — Choose Based on Timeout Budget

| Endpoint | Mode | Latency | Use Case |
|----------|------|---------|----------|
| `https://fal.run/...` | **Sync** | Returns directly (~20-30s) | Images when Worker timeout > 30s |
| `https://queue.fal.run/...` | **Async** | Returns request_id immediately | Videos, long jobs, 30s timeout Workers |

**Cloudflare Workers free tier has 30s timeout.** For images that take ~25s, sync is borderline risky. For videos (1-3 min), async + polling is mandatory.

### Text-to-Image (NanoBanana 2)
```
POST https://queue.fal.run/fal-ai/nano-banana-2   (async)
POST https://fal.run/fal-ai/nano-banana-2          (sync)
```

### Image-to-Image / Edit (NanoBanana 2)
```
POST https://queue.fal.run/fal-ai/nano-banana-2/edit   (async)
POST https://fal.run/fal-ai/nano-banana-2/edit          (sync)
```

### Sync Mode Response (direct image URL, no polling needed)
```json
{
  "images": [
    {
      "url": "https://v3b.fal.media/files/.../image.png",
      "content_type": "image/png"
    }
  ],
  "description": ""
}
```

### Async Mode Response (need polling)
```json
{
  "status": "IN_QUEUE",
  "request_id": "019d85c1-...",
  "response_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/..."
}

### Flux Dev Image-to-Image
```
POST https://queue.fal.run/fal-ai/flux/dev/image-to-image
```

## Auth
```
Authorization: Key <FAL_API_KEY>
```

## Text-to-Image Payload

```json
{
  "prompt": "Professional product photography...",
  "negative_prompt": "blurry, low quality, watermark",
  "num_images": 1,
  "output_format": "png",
  "webhook_url": "https://your-server.com/webhook/fal-image"
}
```

## ⚠️ CRITICAL: image_urls vs image_url (DIFFERENT PER MODEL!) — VERIFIED VIA OPENAPI

**This is the #1 cause of 422 errors from Fal.ai.** Each model has DIFFERENT parameter names!

| Endpoint | Parameter | Type | Required | Example |
|----------|-----------|------|----------|---------|
| `nano-banana-2` (T2I) | N/A | N/A | N/A | No image input |
| `nano-banana-2/edit` (I2I) | `image_urls` | **array** of strings | **YES** | `["https://..."]` |
| `flux/dev/image-to-image` | `image_url` | **string** (singular) | YES | `"https://..."` |

### nano-banana-2/edit — CORRECT format (verified via OpenAPI schema)

Get schema: `curl -s 'https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/nano-banana-2/edit'`

**REQUIRED fields**: `prompt`, `image_urls`

```json
{
  "prompt": "Colorized version of this portrait",
  "image_urls": ["https://example.com/img.jpg"],  // ✅ ARRAY, required
  "num_images": 1,
  "output_format": "png"
}
```

**⚠️ There is NO `strength` parameter for nano-banana-2/edit!** (verified via OpenAPI schema)

### flux/dev/image-to-image — CORRECT format
```json
{
  "prompt": "Same image with vintage filter",
  "image_url": "https://example.com/img.jpg",  // ✅ SINGULAR string
  "strength": 0.65,  // Required for Flux only
  "num_images": 1,
  "output_format": "png"
}
```

## ⚠️ CRITICAL: Result URL ≠ Submit URL for /edit endpoint

When submitting to `fal-ai/nano-banana-2/edit`, the result must be fetched from a DIFFERENT URL:

```typescript
// Submit endpoint (with /edit):
POST https://queue.fal.run/fal-ai/nano-banana-2/edit

// Result endpoint (WITHOUT /edit) — returns 405 if you include /edit:
GET https://queue.fal.run/fal-ai/nano-banana-2/requests/{request_id}  // ✅
GET https://queue.fal.run/fal-ai/nano-banana-2/edit/requests/{request_id}  // ❌ 405
```

Pattern:
```typescript
const submitEndpoint = "fal-ai/nano-banana-2/edit";
const resultEndpoint = submitEndpoint.replace('/edit', '');
const resultUrl = `https://queue.fal.run/${resultEndpoint}/requests/${requestId}`;
```

## Response Format

Submit response:
```json
{
  "status": "IN_QUEUE",
  "request_id": "019d85c1-...",
  "response_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/...",
  "status_url": "https://queue.fal.run/fal-ai/nano-banana-2/requests/.../status"
}
```

Result response:
```json
{
  "images": [
    {
      "url": "https://v3b.fal.media/files/.../image.png",
      "content_type": "image/png"
    }
  ]
}
```

## Async Pattern: Polling as Primary (Webhook as Backup)

Webhooks from Fal.ai can be unreliable. Use polling as primary mechanism:

```typescript
// After submit, start polling immediately
env.waitUntil(pollFalResult(env, jobId, request_id, endpoint));

async function pollFalResult(env, jobId, requestId, endpoint) {
  const resultEndpoint = endpoint.replace('/edit', '');
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 4000));
    const resp = await fetch(`https://queue.fal.run/${resultEndpoint}/requests/${requestId}`, {
      headers: { "Authorization": `Key ${env.FAL_API_KEY}` },
    });
    if (resp.status === 200) {
      const data = await resp.json();
      // Process result, send to user
      return;
    }
  }
  // Timeout - mark failed, refund credits
}
```

## ⚠️ CRITICAL: Credit Refund on Failure

When image generation fails, you MUST refund credits:

1. Save `cost_credits` when creating job
2. On failure (webhook or polling timeout), refund to client
3. Log to `credit_ledger` table
4. Notify user with refund amount

```typescript
if (status === "FAILED" || timedOut) {
  const job = await db.prepare("SELECT * FROM image_jobs WHERE id=?").bind(jobId).first();
  const refundAmount = job.cost_credits || DEFAULT_COST;
  
  // Refund
  await db.prepare("UPDATE clients SET credits = credits + ? WHERE id=?")
    .bind(refundAmount, job.client_id).run();
  await db.prepare("INSERT INTO credit_ledger (client_id, type, amount, balance_after, description) VALUES (?,'refund',?,?,?)")
    .bind(job.client_id, refundAmount, newBalance, `Refund: job #${jobId} failed`).run();
  
  // Notify
  await tgSend(botToken, chatId, `❌ Failed. 💰 ${refundAmount} credits refunded.`);
}
```

## ⚠️ CRITICAL: Proxy URLs for Multi-Tenant Systems

When building multi-tenant systems (e.g., Telegram bots), image URLs from users go through a **proxy**:

```
User sends image → Telegram → Worker creates proxy URL:
https://api.your-domain.com/proxy/media/{file_id}?client={matricule}
```

**External APIs like Fal.ai must receive the PROXY URL, NOT the original URL** (Wikimedia, etc.).

### Ensuring Agent Uses Proxy URL

1. **Inject into agent messages**:
```typescript
if (imageUrl) {
  content += `\n\n[IMAGE_PROXY_URL]: ${imageUrl}\n⚠️ IMPORTANT: Use this exact proxy URL for tool calls.`;
}
```

2. **Fallback in tool execution**:
```typescript
let imageUrl = args.image_ref_url;
if (hasRef && !imageUrl.includes('/proxy/media/')) {
  const client = await db.prepare("SELECT notes FROM clients WHERE id=?").bind(clientId).first();
  const notes = JSON.parse(client.notes || '{}');
  if (notes.pending_proxy_url) imageUrl = notes.pending_proxy_url;
}
```

## Complete TypeScript Example

```typescript
async function toolGenerateImage(env, clientId, args, chatId, botToken) {
  const COST = 5;
  
  // 1. Deduct credits
  const client = await env.DB.prepare("SELECT credits FROM clients WHERE id=?").bind(clientId).first();
  const newBal = client.credits - COST;
  await env.DB.prepare("UPDATE clients SET credits=? WHERE id=?").bind(newBal, clientId).run();
  
  // 2. Create job WITH cost_credits
  const job = await env.DB.prepare(
    `INSERT INTO image_jobs (client_id, telegram_chat_id, input_prompt, status, cost_credits)
     VALUES (?, ?, ?, 'processing', ?) RETURNING id`
  ).bind(clientId, chatId, args.prompt, COST).first();
  
  // 3. Determine endpoint and validate URL
  const hasRef = args.image_ref_url?.length > 0;
  const falEndpoint = hasRef ? "fal-ai/nano-banana-2/edit" : "fal-ai/nano-banana-2";
  let imageUrl = args.image_ref_url;
  
  // Fallback to proxy URL if agent passed wrong URL
  if (hasRef && !imageUrl.includes('/proxy/media/')) {
    const c = await env.DB.prepare("SELECT notes FROM clients WHERE id=?").bind(clientId).first();
    if (c?.notes) {
      const notes = JSON.parse(c.notes);
      if (notes.pending_proxy_url) imageUrl = notes.pending_proxy_url;
    }
  }
  
  // 4. Build payload (image_urls ARRAY for /edit, no strength)
  const payload: any = { prompt: args.prompt, num_images: 1, output_format: "png" };
  if (hasRef) payload.image_urls = [imageUrl];  // ARRAY!
  
  // 5. Submit
  const resp = await fetch(`https://queue.fal.run/${falEndpoint}`, {
    method: "POST",
    headers: { "Authorization": `Key ${env.FAL_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, webhook_url: "https://api.example.com/webhook/fal-image" }),
  });
  const data = await resp.json();
  
  if (data.request_id) {
    // 6. Save request_id and start polling
    await env.DB.prepare(\"UPDATE image_jobs SET status='submitted', fal_request_id=?, fal_endpoint=? WHERE id=?\")
      .bind(data.request_id, falEndpoint, job.id).run();
    env.waitUntil(pollFalResult(env, job.id, data.request_id, falEndpoint, clientId, chatId, botToken));
  } else {
    // Error - refund immediately
    await env.DB.prepare(\"UPDATE image_jobs SET status='failed', error_message=? WHERE id=?\")
      .bind(`Fal.ai error: ${JSON.stringify(data).substring(0,200)}`, job.id).run();
    // ... refund logic ...
  }
}
```

## Fallback Provider: Pollinations.ai (No API Key)

When Fal.ai returns auth errors (exhausted key, invalid credentials), Pollinations.ai is a reliable zero-key fallback:

```bash
PROMPT="A majestic dragon on the moon, epic fantasy art"
ENCODED=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''$PROMPT'''))")
curl -sL "https://image.pollinations.ai/prompt/${ENCODED}?width=1024&height=768&seed=42&nologo=true" -o output.jpg
```

**Important**: Pollinations returns JPEGs even if the filename ends in `.png`. Verify with `xxd` — magic bytes `ffd8` = JPEG, `89504e47` = PNG.

| Parameter | Description |
|-----------|-------------|
| `width` / `height` | Output dimensions |
| `seed` | Reproducibility |
| `nologo=true` | Remove watermark |
| `negative_prompt` | URL-encoded negative prompt |

## Video Generation (Fal.ai)

### Veo3 — Text-to-Video
```
POST https://queue.fal.run/fal-ai/veo3
```
```json
{
  "prompt": "Cinematic product shot, dramatic lighting...",
  "webhook_url": "https://your-server.com/webhook/fal-video"
}
```

### MiniMax Video — Image-to-Video
```
POST https://queue.fal.run/fal-ai/minimax-video/video-01-live
```
```json
{
  "prompt": "Animate this product image with cinematic motion",
  "image_url": "https://example.com/product.png",
  "webhook_url": "https://your-server.com/webhook/fal-video"
}
```

### Video Response (async)
```json
{
  "status": "IN_QUEUE",
  "request_id": "019d85c1-...",
  "response_url": "https://queue.fal.run/fal-ai/veo3/requests/..."
}
```

Same polling pattern as images. Video jobs take 1-3 minutes.

## Common Pitfalls

1. **Fal response shapes vary by endpoint**: image sync calls commonly return `images[0].url`; queue/video calls commonly return `request_id` plus `status_url`/`response_url`. Store provider-returned status/response URLs when available instead of reconstructing them, and use broad extractors for `video.url`, `output.video_url`, `data.video.url`, and `result.video.url`.

2. **BYOK SaaS integrations must use the tenant key**: when a client supplies a Fal key, decrypt and use `providerKeys.fal` before falling back to platform `FAL_API_KEY`; a stubbed provider-key loader silently breaks the product contract.

3. **D1 column names**: SQLite column names cannot be `***` or other invalid identifiers. Use `fal_request_id` as the column name. The D1 API may silently fail if you use invalid column names in UPDATE statements.

2. **Telegram delivery**: After image is ready, send via `sendPhoto` with the image URL as `photo` parameter. Telegram fetches the URL directly — no need to download/re-upload.

3. **Worker timeout**: Cloudflare Workers free tier = 30s timeout. Sync `fal.run` calls that take 25s+ are risky. Use async + `waitUntil` polling for safety.

4. **`fal.run` vs `queue.fal.run`**: Same API, different behavior. `fal.run` blocks until complete. `queue.fal.run` returns immediately with request_id.

5. **Result URL for /edit**: Always strip `/edit` from endpoint when fetching results. `nano-banana-2/edit/requests/{id}` returns 405.
