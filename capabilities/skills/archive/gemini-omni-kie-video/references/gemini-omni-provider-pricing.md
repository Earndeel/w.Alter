# Gemini Omni & Video Models — Provider Pricing Comparison

Live data July 28, 2026. All prices in USD per second of 720p video output unless specified.

## Gemini Omni Flash

| Provider | $/s (720p) | 10s clip | 1080p | 4K |
|---|---|---|---|---|
| **Kie.ai** | **$0.063/s** | $0.63 | $0.063/s | $0.105/s |
| Google API | $0.10/s | $1.01 | — | — |
| Fal.ai | $0.13/s | $1.30 | — | — |

Kie.ai per-second rate decreases with longer clips (fixed setup cost amortized):
- 4s: $0.079/s, 6s: $0.07/s, 8s: $0.066/s, 10s: $0.063/s

Google API: flat $0.10/s regardless of duration. No 4K pricing.
Fal.ai: ~$0.13/s, input $1.875/1M tokens, output $21.875/1M tokens.

## Seedance 2.0

| Provider | Fast (720p) | Standard (720p) | Standard (1080p) | Mini (720p) |
|---|---|---|---|---|
| **Kie.ai** | **$0.165/s** | $0.205/s | $0.51/s | **$0.1025/s** |
| Fal.ai | $0.242/s | N/A | N/A | N/A |

Seedance 2 Standard also available in 4K via Kie.ai: $1.04/s.

All Kie.ai prices are "without video input" (generation mode). With video input, prices are lower because billing formula changes to `Price × (Input + Output)` instead of `Price × Output`.

## Grok Imagine 1.5

| Provider | $/s (720p) |
|---|---|
| **Kie.ai** | **$0.015/s** (3 credits) |
| xAI API (direct) | $0.05/s |
| Fal.ai | N/A (endpoint returns 404) |

Grok Imagine 1.5 also available in 480p via Kie.ai: $0.008/s (1.6 credits).

## Key Takeaways

- **Kie.ai is the cheapest provider for every video model** tested
- Grok Imagine 1.5 is the cheapest model overall at $0.015/s — 3.3× cheaper than xAI direct
- Gemini Omni Flash on Kie.ai ($0.063/s) is 37% below Google API, 51% below Fal.ai
- Seedance 2.0 Fast on Kie.ai is 32% below Fal.ai
- Fal.ai is consistently the most expensive (+30-47% markup)
