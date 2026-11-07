# Video Model Pricing Comparison — July 2026

Live pricing extracted 2026-07-28 via Kie.ai model pages and provider API endpoints.
All prices in $/second for 720p unless noted.

## Gemini Omni Flash

| Provider | $/s (720p) | 10s clip | Notes |
|----------|-----------|----------|-------|
| **Kie.ai** | $0.063/s | $0.63 | Degressive per duration. 1 cr ≈ $0.005 |
| Google API | $0.10/s | $1.01 | $17.50/1M tokens, 5,792 tok/s |
| Fal.ai | $0.13/s | $1.30 | $21.875/1M output tokens |

Kie.ai prices per duration: 4s=$0.315 (63cr), 6s=$0.42, 8s=$0.525, 10s=$0.63.
4K: 4s=$0.735 (147cr), 6s=$0.84, 8s=$0.945, 10s=$1.05.
With video input: flat 720p=$0.84 (168cr), 4K=$1.26 (252cr).

## Seedance 2.0 (ByteDance)

All via Kie.ai. Fal.ai only carries Seedance 2.0 Fast at $0.242/s (720p, text-to-video).

| Variant | 480p (w/ video) | 720p (w/ video) | 720p (no video) | 1080p | 4K |
|---------|-----------------|-----------------|-----------------|-------|-----|
| **Mini** | $0.030/s | $0.0625/s | $0.1025/s | — | — |
| **Fast** | $0.045/s | $0.100/s | $0.165/s | — | — |
| **Standard** | $0.0575/s | $0.125/s | $0.205/s | $0.31/s | $0.64/s |

"With video" = video_list input, lower per-second rate because billing is `Price × (Input + Output)` instead of `Price × Output`.

## Grok Imagine 1.5 (xAI)

| Provider | $/s (720p) | 480p |
|----------|-----------|------|
| **Kie.ai** | $0.015/s | $0.008/s |
| xAI API (direct) | $0.05/s | — |
| Fal.ai | N/A (model page 404) | — |

Kie.ai pricing for Grok Imagine is exceptionally low: 3 credits/s at 720p, 1.6 credits/s at 480p.
This is 70% cheaper than xAI's direct API.

## Cross-Provider Summary (720p, cheapest variant)

| Model | Best price | Provider | vs next cheapest |
|-------|-----------|----------|-----------------|
| Gemini Omni Flash | $0.063/s | Kie.ai | −37% vs Google API |
| Seedance 2.0 Mini | $0.0625/s | Kie.ai | exclusive |
| Seedance 2.0 Fast | $0.100/s | Kie.ai | −59% vs Fal.ai ($0.242/s) |
| Grok Imagine 1.5 | $0.015/s | Kie.ai | −70% vs xAI direct |
