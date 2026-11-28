# Higgsfield Model Catalog — Verified IDs

Last verified: 2026-07-03. Generate models come and go; always query live with `models_explore` (search) before generating.

## Image generation models (Nano Banana family)

| ID | Name | Provider |
|----|------|----------|
| `nano_banana` | Nano Banana (v1) | Google |
| `nano_banana_2` | Nano Banana 2 | Google |
| `nano_banana_2_lite` | Nano Banana 2 Lite | Google |
| `nano_banana_pro` | Nano Banana Pro | Google |
| `nano_banana_2_shots` | Nano Banana Pro (alt) | — |

**⚠️ Model name caution:** No model named "nano banana 2 flash" or "Nano Banana Flash" exists in the Higgsfield catalog. Users may conflate the Nano Banana brand with Gemini's "Flash" tier. The correct Nano Banana 2 models are `nano_banana_2` and `nano_banana_2_lite`.

## Other image models (sampling)

| ID | Name | Provider |
|----|------|----------|
| `flux_2` | FLUX.2 | Black Forest Labs |

## Async generation workflow

`generate_image` is **asynchronous** — it returns a pending job ID immediately, not the image. The workflow:

1. Call `generate_image` → get `status: "pending"` + job `id`
2. Poll `job_status` with `jobId` (singular string, NOT `job_ids` array!) → wait for `status: "completed"`
3. Download from `results.rawUrl`

**⚠️ Critical pitfall:** The tool `show_jobs` DOES NOT EXIST on Higgsfield MCP. Use `job_status`, not `show_jobs`.

**⚠️ Critical pitfall:** `job_status` parameter is `jobId` (singular, a string) — NOT `job_ids` (array). Passing `job_ids` returns `MCP error -32602: Input validation error: expected string, received undefined`.

### Full generate + poll + download

```bash
# 1. Generate (returns pending job)
curl -sS -X POST https://mcp.higgsfield.ai/mcp \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"generate_image","arguments":{"params":{"model":"nano_banana_2_lite","prompt":"A cat","aspect_ratio":"1:1","count":1}}}}'

# 2. Poll status (note: jobId, NOT job_ids)
curl -sS -X POST https://mcp.higgsfield.ai/mcp \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"job_status","arguments":{"jobId":"<job-id>"}}}'

# 3. When status=completed, download results.rawUrl
```

Job statuses: `pending` → `processing` → `completed` (or `failed`). Poll every 5s.

### Image generation tools reference

| Tool | Description | Key params |
|------|-------------|------------|
| `generate_image` | Generate images | `params.model`, `params.prompt`, `params.aspect_ratio`, `params.count` |
| `job_status` | Check job status | `jobId` (string, singular) |
| `job_display` | Display result | `jobId` (string) |

## Direct curl pattern for MCP tool calls

When Hermes's MCP tool registry hasn't loaded the server (e.g., mid-session, or before a `/reload-mcp`), call the MCP endpoint directly with the cached access token:

```bash
ACCESS_TOKEN=$(cat ~/.hermes/mcp-tokens/higgsfield.tokens.json | python3 -m json.tool access_token)

# List all tools
curl -sS -X POST https://mcp.higgsfield.ai/mcp \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Search models
curl -sS -X POST https://mcp.higgsfield.ai/mcp \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"models_explore","arguments":{"action":"search","query":"nano banana","type":"image"}}}'

# Get model details
curl -sS -X POST https://mcp.higgsfield.ai/mcp \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"models_explore","arguments":{"action":"get","model_id":"nano_banana_2"}}}'
```

The response is SSE-formatted. The `data:` line is a JSON payload with `result.structuredContent` (models_explore) or `result.tools` (tools/list).

## Token refresh

If the access token expired, use the refresh token against the token endpoint. See `mcp-oauth-troubleshooting` for the full refresh flow.
