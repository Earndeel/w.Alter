# Kling Pricing — fal.ai vs kie.ai (May 2026)

## fal.ai Pricing (per second of output video)

| Model | Endpoint | $/s |
|-------|----------|-----|
| V2.5 Turbo Standard I2V | `fal-ai/kling-video/v2.5-turbo/standard/image-to-video` | $0.042 |
| V2.5 Turbo Pro I2V | `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` | $0.07 |
| V2.5 Turbo Pro T2V | `fal-ai/kling-video/v2.5-turbo/pro/text-to-video` | $0.07 |
| V2.5 Turbo Standard T2V | `fal-ai/kling-video/v2.5-turbo/standard/text-to-video` | $0.0002/compute-sec ⚠️ |
| V2.1 Standard I2V | `fal-ai/kling-video/v2.1/standard/image-to-video` | $0.056 |
| V2.1 Pro I2V | `fal-ai/kling-video/v2.1/pro/image-to-video` | $0.098 |
| V3 Pro/Standard (all) | `fal-ai/kling-video/v3/...` | $0.14 |

⚠️ V2.5 Turbo Standard T2V uses "per compute-second" (server processing time), NOT "per second of video". A 5s video may take 50-200 compute-seconds.

## kie.ai Pricing (credit-based, 1 credit ≈ $0.005 USD)

| Model | Model ID | Credits/s | $/s (est.) |
|-------|----------|-----------|------------|
| Kling 2.5 Turbo T2V Pro | `kling/v2-5-turbo-text-to-video-pro` | unknown | ~$0.14-0.20 (est.) |
| Kling 2.5 Turbo I2V Pro | `kling/v2-5-turbo-image-to-video-pro` | unknown | ~$0.14-0.20 (est.) |
| Kling 2.6 T2V | `kling-2.6/text-to-video` | unknown | unknown |
| Kling 2.6 I2V | `kling-2.6/image-to-video` | unknown | unknown |
| Kling 3.0 | `kling/kling-3-0` | unknown | unknown |

kie.ai pricing is NOT published per-model on any scrapable API. The `/pricing` page is a SPA with 321 entries, paginated, JS-only search. To get exact pricing: submit a test task and check credit balance before/after via `GET /api/v1/chat/credit`.

## Cost Estimate for 5-second video

| Provider | Model | Cost |
|----------|-------|------|
| fal.ai | V2.5 Turbo Standard I2V | **$0.21** |
| fal.ai | V2.5 Turbo Pro I2V | **$0.35** |
| fal.ai | V3 Pro I2V | **$0.70** |
| kie.ai | V2.5 Turbo Pro (est.) | **$0.70-1.00** |
| kie.ai | Kling 2.6 (est.) | unknown |

## Key Insight

fal.ai is generally **cheaper** for Kling video than kie.ai, but kie.ai is cheaper for Claude/Chat models (~3× discount vs OpenRouter). For video-heavy workloads, prefer fal.ai. For mixed workloads (video + LLM), kie.ai offers a unified API with one balance.
