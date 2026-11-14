# Kling Video Pricing — Cross-Provider Comparison

Session: May 22, 2026. Sources: fal.ai MCP API, kie.ai docs + pricing page (SPA).

## fal.ai Kling 2.5 Turbo (confirmed via `mcporter call fal.get_pricing`)

| Endpoint | Type | Price |
|----------|------|-------|
| `fal-ai/kling-video/v2.5-turbo/standard/image-to-video` | I2V Standard | **$0.042/s** video |
| `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` | I2V Pro | **$0.07/s** video |
| `fal-ai/kling-video/v2.5-turbo/pro/text-to-video` | T2V Pro | **$0.07/s** video |
| `fal-ai/kling-video/v2.5-turbo/standard/text-to-video` | T2V Standard | $0.0002/compute-sec (different unit) |

**Cost per 5s video:**
- Standard I2V: 5 × $0.042 = **$0.21**
- Pro I2V/T2V: 5 × $0.07 = **$0.35**

### fal.ai Kling Other Versions (for reference)

| Model | Price |
|-------|-------|
| V2.1 Standard I2V | $0.056/s |
| V2.1 Pro I2V | $0.098/s |
| V3 Pro/Standard (all) | $0.14/s |

## kie.ai Kling 2.5 Turbo

| Endpoint | Model ID |
|----------|----------|
| T2V Pro | `kling/v2-5-turbo-text-to-video-pro` |
| I2V Pro | `kling/v2-5-turbo-image-to-video-pro` |

**Pricing: NOT available from API or docs.** Only visible on the SPA pricing page (`kie.ai/pricing`), which is unscrapable (paginated 25/page, JS-only search). See SKILL.md pitfall section.

### How to measure empirically

```bash
# Check balance before
BEFORE=$(curl -s -H "Authorization: Bearer $(vault get kie/api_key)" \
  https://api.kie.ai/api/v1/chat/credit | python3 -c "import sys,json; print(json.load(sys.stdin)['data'])")

# Submit a 5s I2V task
curl -s -X POST https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer $(vault get kie/api_key)" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kling/v2-5-turbo-image-to-video-pro",
    "input": {
      "prompt": "Test video for pricing measurement",
      "image_url": "https://example.com/test.jpg",
      "duration": "5"
    }
  }'

# Wait for completion, then check balance after
AFTER=$(curl -s -H "Authorization: Bearer $(vault get kie/api_key)" \
  https://api.kie.ai/api/v1/chat/credit | python3 -c "import sys,json; print(json.load(sys.stdin)['data'])")

# Cost in credits = BEFORE - AFTER
# Cost in USD = credits × $0.005
```

## Key Naming Difference

fal.ai uses **slashes** in path: `fal-ai/kling-video/v2.5-turbo/...`
kie.ai uses **dashes** in model ID: `kling/v2-5-turbo-...`

The fal.ai model page URL is `https://fal.ai/models/fal-ai/kling-video/v2.5-turbo/standard/image-to-video` (note: `v2.5-turbo` with dashes, NOT `v2.5/turbo` with slashes).
