# Fal.ai Pipeline Patterns for Scena Video Factory

## Architecture Decision (2026-05-25)

**User directive**: "pas de Kie ai juste FAL et openrouter pour le LLM et ils ne peuvent pas choisir les model ca c'est le worflow"

- Fal.ai = sole provider for image + video generation
- OpenRouter = sole provider for LLM (analysis, plans)
- Client provides only their Fal API key (BYOK)
- Client does NOT choose models — workflow decides per preset

## Fal.ai Endpoints Used

| Use Case | Endpoint | Input | Output |
|----------|----------|-------|--------|
| Text-to-image | `fal-ai/nano-banana-2` | `prompt`, `num_images` | `images[].url` |
| Image-to-image | `fal-ai/nano-banana-2/edit` | `prompt`, `image_urls[]` (ARRAY!) | `images[].url` |
| Text-to-video | `fal-ai/veo3` | `prompt` | video URL |
| Image-to-video | `fal-ai/minimax-video/video-01-live` | `prompt`, `image_url` | video URL |

## Critical Pitfalls

### 1. Result URL ≠ Submit URL for /edit endpoint
```
Submit: POST https://queue.fal.run/fal-ai/nano-banana-2/edit
Result: GET  https://queue.fal.run/fal-ai/nano-banana-2/requests/{request_id}  ← NO /edit!
```

### 2. image_urls vs image_url (DIFFERENT PER MODEL)
- `nano-banana-2/edit`: `image_urls` = **array** of strings
- `minimax-video`: `image_url` = **string** (singular)

### 3. Auth header format
```
Authorization: Key {FAL_API_KEY}    ← "Key" not "Bearer"
```

### 4. HTTP status codes for polling
- `200` = completed, body has result
- `202` = still processing
- `422` = failed permanently

### 5. Node.js TypeScript generics issue
`Record<string, string>` causes `ERR_INVALID_TYPESCRIPT_SYNTAX` with `--experimental-strip-types`.
Replace all generic types with index signatures: `{ [key: string]: string }`.
Same for `Partial<T>` → use explicit optional fields, `Promise<T>` → works fine in return types.
