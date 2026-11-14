## Adding a New Video Provider (e.g., Kie.ai)

When adding a new video generation provider to Scena, follow this 5-step pattern. Example: Kie.ai Seedance 2.0 integration.

### 1. Model Catalog — `orchestration_config.ts`

Add entries to `BUILTIN_MODEL_CATALOG` with `provider: 'kie'` (or the new provider slug):

```typescript
{
  id: 'video-kie-seedance-2-fast',
  action_type: 'video_gen',
  provider: 'kie',
  model_id: 'bytedance/seedance-2-fast',
  label: 'Seedance 2 Fast (Kie.ai)',
  family: 'Seedance 2',
  media_kind: 'video',
  mode: 'text-to-video / image-to-video',
  supports_image_ref: true,
  default_params: { duration: '5', aspect_ratio: '9:16', resolution: '720p' },
}
```

Remove any hard `provider === 'fal'` filters in `listModelCatalog()` so the new provider appears in admin UI.

### 2. Env Interface — `agent.ts` + `index.ts`

Add the API key to both `Env` interfaces:

```typescript
export interface Env {
  DB: D1Database;
  PIAPI_API_KEY: string;
  FAL_API_KEY: string;
  KIE_API_KEY: string;  // ← new
  OPENROUTER_API_KEY: string;
  // ...
}
```

### 3. Provider Branch — `agent.ts` in `submitSingleVideoGeneration()`

Add an `else if (routeProvider === 'kie')` branch before the PiAPI fallback:

```typescript
} else if (routeProvider === 'kie') {
  const kieModelId = requestedModelId || 'bytedance/seedance-2-fast';
  await env.DB.prepare('UPDATE video_jobs SET model = ? WHERE id = ?').bind(kieModelId, jobId).run();
  const kiePayload: any = {
    model: kieModelId,
    callBackUrl: 'https://api.walter-ai.cloud/webhook/kie',
    input: {
      prompt: injected.prompt,
      resolution: resolution || '720p',
      aspect_ratio: aspectRatio || '9:16',
      duration: durationInt || 5,
      generate_audio: false,
    },
  };
  if (hasRef) kiePayload.input.first_frame_url = imageUrl;
  // POST to https://api.kie.ai/api/v1/jobs/createTask
  // On success: UPDATE video_jobs SET piapi_task_id = ?, piapi_status = 'submitted'
  // Return { success: true, state: 'submitted', job_id, request_id: taskId }
}
```

Key: reuse the existing `video_jobs` table — the `piapi_task_id` column stores the external task ID regardless of provider.

### 4. Webhook Handler — `index.ts`

Add route + handler:

```typescript
// Route
if (path === "/webhook/kie" && method === "POST") {
  return await handleKieWebhook(request, env);
}

// Handler pattern
async function handleKieWebhook(request: Request, env: Env): Promise<Response> {
  const body = await request.json<any>();
  const taskData = body.data || body;
  const taskId = taskData.taskId || taskData.task_id;
  const status = String(taskData.status || taskData.msg || '').toLowerCase();
  const job = await env.DB.prepare("SELECT * FROM video_jobs WHERE piapi_task_id = ?").bind(taskId).first<any>();
  // completed → UPDATE status, send Telegram video, recordWorkflowAsyncResult
  // failed → UPDATE status, refund credits, notify client
}
```

### 5. Deploy Secret + Update D1 Route

```bash
# Upload secret
echo "$KIE_KEY" | npx wrangler secret put KIE_API_KEY --name scena-api

# Deploy
npx wrangler deploy

# Set as default video provider in D1
INSERT INTO action_model_routes (id, action_type, title, provider, model_id, enabled, priority)
VALUES ('default-video-kie', 'video_gen', 'Default Kie Video', 'kie', 'bytedance/seedance-2-fast', 1, 1)
ON CONFLICT(id) DO UPDATE SET provider='kie', model_id='bytedance/seedance-2-fast', enabled=1;
```

### Pitfalls
- Do NOT create a separate jobs table — `video_jobs` is provider-agnostic. The `piapi_task_id` name is legacy but stores any provider's task ID.
- The `routeProvider` variable in `submitSingleVideoGeneration` was previously hardcoded to `'fal'`. Change it to `requestedProvider || 'fal'` so the `action_model_routes` provider field actually routes requests.
- Kie.ai uses `callBackUrl` (camelCase) in the payload, not `webhook_url`.
- Always test the webhook route with `curl -X POST https://scena-api.lucas-jouvencon.workers.dev/webhook/kie` after deploy.
