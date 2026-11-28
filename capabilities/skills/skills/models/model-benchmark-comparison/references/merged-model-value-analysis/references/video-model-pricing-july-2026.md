# Video Model Pricing Comparison — July 2026

Cross-provider pricing for AI video generation models. All data live as of July 28, 2026.
Prices in USD per second of output video at 720p unless noted. Generation mode (no video input).

## Gemini Omni Flash

Kie.ai API: `POST /api/v1/jobs/createTask`, model `gemini-omni-video`. Poll at `GET /api/v1/jobs/recordInfo?taskId=X`.
Duration capped at 10s. Resolution: 720p, 1080p, 4K. Aspect: 16:9, 9:16.

### Without video input (per-second, progressive):

| Duration | 720p/1080p | $/s effective | 4K | $/s effective |
|---|---|---|---|---|
| 4s | $0.315 | $0.079/s | $0.735 | $0.184/s |
| 6s | $0.42 | $0.070/s | $0.84 | $0.140/s |
| 8s | $0.525 | $0.066/s | $0.945 | $0.118/s |
| 10s | $0.63 | **$0.063/s** | $1.05 | **$0.105/s** |

Longer clips = cheaper per second (fixed setup cost amortized).

### With video input (editing/extension, flat rate):

| Resolution | Price |
|---|---|
| 720p/1080p | $0.84 |
| 4K | $1.26 |

Duration is model-determined when video input is present.

### Cross-provider comparison (720p, 10s clip):

| Provider | $/s | 10s clip |
|---|---|---|
| **Kie.ai** | **$0.063/s** | $0.63 |
| Google API | $0.10/s | $1.01 |
| Fal.ai | $0.13/s | $1.30 |

Google API pricing: $17.50/1M output tokens, fixed 5,792 tokens/s of 720p video → ~$0.10/s.
Fal.ai pricing: $21.875/1M output tokens, same token rate → ~$0.13/s.

## Seedance 2.0 (ByteDance)

### Kie.ai — bytedance/seedance-2-fast (no video input):

| Resolution | $/s |
|---|---|
| 480p | $0.0775/s |
| 720p | **$0.165/s** |

### Kie.ai — bytedance/seedance-2 (standard, no video input):

| Resolution | $/s |
|---|---|
| 480p | $0.095/s |
| 720p | $0.205/s |
| 1080p | $0.51/s |
| 4K | $1.04/s |

### Kie.ai — bytedance/seedance-2-mini (no video input):

| Resolution | $/s |
|---|---|
| 480p | $0.0475/s |
| 720p | $0.1025/s |

### Fal.ai — bytedance/seedance-2.0/fast/text-to-video:

| Resolution | $/s |
|---|---|
| 720p | **$0.242/s** |

Fal.ai is 47% more expensive than Kie.ai for Seedance 2 Fast.

### Seedance pricing note:
All Seedance variants have a "with video input" mode that is **cheaper** than generation mode,
because billing switches from `Price × Output` to `Price × (Input + Output)` where input is weighted lower.

## Grok Imagine 1.5 (xAI)

### Kie.ai — grok-imagine/image-to-video:

| Resolution | $/s |
|---|---|
| 480p | $0.008/s (1.6 credits) |
| 720p | **$0.015/s** (3 credits) |

### xAI API (direct):

| Resolution | $/s |
|---|---|
| 720p | $0.05/s |

Kie.ai is 70% cheaper than xAI direct API.

### Fal.ai:
Grok Imagine 1.5 page returns 404 as of July 2026. Model may not be available.

## Summary — Best price per model (720p)

| Model | Best Price | Provider | vs Next Best |
|---|---|---|---|
| Gemini Omni Flash | $0.063/s | Kie.ai | −37% vs Google API |
| Seedance 2.0 Fast | $0.165/s | Kie.ai | −32% vs Fal.ai |
| Seedance 2.0 Mini | $0.1025/s | Kie.ai | exclusive |
| Grok Imagine 1.5 | $0.015/s | Kie.ai | −70% vs xAI direct |

Kie.ai is the cheapest provider for every video model tested. 1 credit ≈ $0.005.
High-tier top-ups include +10% bonus credits (~90% effective).
