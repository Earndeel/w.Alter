## Fal.ai Video Generation (Grok — Current Provider)

### Admin provider/model catalog (Scena control plane)
Scena now exposes a built-in provider/model catalog via `GET /api/admin/model-catalog` and the admin Action Route modal has a `Catalog model` picker.
Use it to choose the exact provider+model combo per action without hardcoding IDs.

Current built-in video entries can be switched by product mode. In Fal-only mode, expose only:
- `fal / xai/grok-imagine-video/text-to-video`
- `fal / xai/grok-imagine-video/image-to-video`

Recommended ops pattern for Fal-only mode:
- hide PiAPI entries from `/api/admin/model-catalog`
- set `video-default` route to `provider=fal`, `model_id=xai/grok-imagine-video/text-to-video`
- keep `endpoint=''` and let the worker choose text-to-video vs image-to-video dynamically based on whether `image_ref_url` exists
- keep default params minimal (e.g. `duration`, `resolution`) so aspect ratio can stay dynamic (`9:16` for T2V, `auto` for I2V)

The catalog also returns recommended default params JSON for the UI (duration/aspect ratio/resolution), so the route form can prefill provider/model/endpoint/params in one click.

### Field Names (Model-Specific)
Fal.ai video models use DIFFERENT field names than PiAPI:
- `xai/grok-imagine-video/image-to-video` → expects `image_url` (NOT `start_image_url`)
- Each Fal.ai model may have different param names — check the 422 error message for the exact field

### Image→Video Chaining (Critical Flow)
Agent must chain `generate_image` → `generate_video` using the Fal.ai CDN URL:

```
1. Agent calls generate_image → returns { output_url: "https://v3b.fal.media/.../image.png" }
2. Agent calls generate_video with image_ref_url = that output_url (Fal.ai CDN, NOT proxy)
3. Worker sends image_url: "https://v3b.fal.media/..." to Fal.ai
```

**DO NOT** override Fal.ai CDN URLs with Telegram proxy URLs in `generate_video`. The proxy URL is only needed for the FIRST `generate_image` call (referencing the user's original image).

### ReAct Loop — `generate_image` is SYNC
`generate_image` uses `https://fal.run/` (sync endpoint) and returns the result directly. It is NOT async.

**Only `generate_video` and `generate_voice` should stop the ReAct loop** (they use `queue.fal.run/` and polling/webhook).

If `generate_image` stops the loop, the agent never gets to call `generate_video` with the output URL.

```typescript
// CORRECT — only truly async tools stop the loop
const hasAsyncTool = response.tool_calls.some(
  (tc: any) => ["generate_video", "generate_voice"].includes(tc.function.name)
);

// WRONG — generate_image is sync, don't include it
// const hasAsyncTool = response.tool_calls.some(
//   (tc: any) => ["generate_image", "generate_video", "generate_voice"].includes(tc.function.name)
// );
```

### `ctx.waitUntil` Pattern (Cloudflare Workers)
The `fetch` handler signature must include `ctx: ExecutionContext`:

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // ...
    // Use ctx.waitUntil for background polling, NOT env.waitUntil
    ctx.waitUntil(pollFalVideoResult(env, jobId, requestId, endpoint, clientId, chatId, botToken));
  }
}
```

`waitUntil` is on the execution context (`ctx`), not on `env`. Forgetting this causes `env.waitUntil is not a function` — the polling never starts, jobs stay stuck forever.

Thread `ctx` through the call chain: `fetch` → `handleTelegramWebhook` → `handleAgentMessage` → `executeTool` → `toolGenerateVideo`.
