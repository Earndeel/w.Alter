# Higgsfield Model Catalog

## Video models (text-to-video)

| Model ID | Name | Provider | Notes |
|---|---|---|---|
| `kling3_0_turbo` | Kling 3.0 Turbo | Kling | Default video model. 8s duration. |
| `kling-v1-6` | Kling v1.6 | Kling | Previous generation. |
| `gemini_omni` | Gemini Omni Flash | Google | Omni Flash for video generation. |
| `cinematic_studio_3_0` | Cinematic Studio 3.0 | Higgsfield | Premium model with genre/audio options. |
| `veo3_1` | Veo 3.1 | Google | Google's Veo video model. |

## Image models

| Model ID | Name | Provider |
|---|---|---|
| `nano_banana_2` | Nano Banana 2 | Google |
| `nano_banana_pro` | Nano Banana Pro | Google |
| `soul_2` | Higgsfield Soul 2.0 | Higgsfield |

## Discovery

Search for models:
```bash
curl -sS 'https://mcp.higgsfield.ai/mcp' \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"models_explore","arguments":{"action":"search"}},"id":1}'
```
