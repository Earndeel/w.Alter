# Higgsfield Model Catalog & Error Patterns

## Valid Model IDs

| Model ID | Provider | Type | Notes |
|----------|----------|------|-------|
| `kling-v1-6` | Kling 1.6 | text-to-video | |
| `kling3_0_turbo` | Kling 3.0 Turbo | text-to-video | **NOT `kling3_0`** — that ID errors with "Something went wrong." Duration must be a number (8), not a string ("8s"). |
| `gemini_omni` | Gemini Omni Flash | text-to-video | Google. Discover with `action:"search","query":"gemini"`. |
| `veo3_1` | Google Veo 3.1 | text-to-video | Ultra-realistic cinematic. |

## Full Model Catalog (from `models_explore(action:"list")`)

### Video Models
- `kling3_0` — Kling v3.0 (Kling) — Multi-shot, audio sync, motion transfer
  - Duration: 5-10s, modes: std/pro
  - Aspect ratios: 16:9, 9:16, 1:1
- `seedance_2_0` — Seedance 2.0 (Bytedance) — Reference-driven video w/ image/video/audio refs
- `veo3_1` — Google Veo 3.1 (Google) — Ultra-realistic, top-tier cinematic quality
- `cinematic_studio_video` — Cinema Studio Video (Higgsfield) — Cinematic, dramatic compositions
- `wan_2_5` — Wan 2.5

### Image Models
- `nano_banana_2` — Nano Banana 2 (Google) — Fast next-gen images, quad/2K/4K
- `seedream_5_0` — Seedream 5.0 (Bytedance) — Reference-driven, logo injection, medium/high quality
- `cinematic_studio_2_5` — Cinema Studio Image 2.5 (Higgsfield) — Cinematic stills, up to 4K
- `seedream_4_5` — Seedream 4.5 (Bytedance) — Image, Reels
- `midjourney_v7` — Midjourney v7 (Midjourney)

## Common Error Transcripts

### Missing `params` wrapper
```
MCP error -32602: Input validation error: Invalid arguments for tool generate_video: [
  {
    "expected": "object",
    "code": "invalid_type",
    "path": ["params"],
    "message": "Invalid input: expected object, received undefined"
  }
]
```
**Fix**: Always wrap args in `{"params": {...}}`.

### Wrong model ID
```
Invalid request: unknown model "kling-v1-6". Use models_explore(action:'list') to see available models.
```
**Fix**: Use `kling3_0`.

### Generic server error
```
Error starting generation: Something went wrong. Please try again.
Request ID: d395bd98-a47c-4a82-8e16-a6c478601b1c
```
This can mean: token expired, server-side issue, or bad parameter combination. Try `get_cost:true` first to validate params.

### Transport down
```
MCP server 'higgsfield' transport is down; reconnect requested. Do NOT retry this tool immediately.
```
**Fix**: Run `hermes mcp test higgsfield`, wait a few seconds, retry.

### Headless OAuth failure
```
MCP OAuth for 'higgsfield': non-interactive environment and no cached tokens found.
Run `hermes mcp login higgsfield` interactively first to complete initial authorization.
```
**Fix**: Must run `hermes mcp login higgsfield` from an interactive terminal.

### Not Acceptable (wrong Accept header)
```
{"jsonrpc":"2.0","error":{"code":-32000,"message":"Not Acceptable: Client must accept both application/json and text/event-stream"},"id":null}
```
**Fix**: Include `Accept: application/json, text/event-stream` header.

### Token refresh endpoint not found
```
{"message":"Route POST:/oauth/token not found","error":"Not Found","statusCode":404}
```
OAuth token endpoint is at `/oauth2/token` (with `2`) — but even that may return an error if the refresh token is already consumed.
