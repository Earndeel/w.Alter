# Gemini Omni Flash — Cross-Provider Pricing (July 2026)

Live extraction from Google API, Kie.ai, and Fal.ai model pages. All data as of July 28, 2026.

## Model Identification

- **Model:** Gemini Omni Flash (first and only member of the Omni family)
- **Google model ID:** `gemini-omni-flash-preview`
- **Kie.ai model ID:** `gemini-omni-video`
- **Fal.ai model ID:** `google/gemini-omni-flash/image-to-video`
- **Cap:** 10-second clips max
- **720p token rate:** 5,792 tokens per second (Google's billing conversion)

## Pricing Comparison — 720p Video Output

| Provider | Per-Second | 10s Clip | Input $/1M tokens | Output $/1M tokens |
|---|---|---|---|---|
| **Google API** | $0.10/s | $1.01 | $1.50 | $17.50 |
| **Kie.ai** | $0.063–0.079/s | **$0.63** | crédits | — |
| **Fal.ai** | $0.13/s | $1.30 | $1.875 | $21.875 |

## Kie.ai Detail (1 crédit ≈ $0.005)

| Duration | 720p/1080p | 4K |
|---|---|---|
| 4s | 63 cr ($0.315) | 147 cr ($0.735) |
| 6s | 84 cr ($0.42) | 168 cr ($0.84) |
| 8s | 105 cr ($0.525) | 189 cr ($0.945) |
| 10s | 126 cr ($0.63) | 210 cr ($1.05) |

With video input: 1080p = 168 cr ($0.84) flat, 4K = 252 cr ($1.26) flat (duration auto-determined).

Volume discount: high-tier top-ups include 10% bonus credits → effective ~90% of listed prices.

## Verdict

- **Kie.ai −37% vs Google API** on 10s 1080p. Cheapest option.
- **Fal.ai +30% vs Google API.** Most expensive. Advantage = no monthly commitment, direct dev integration.
- Google API: no free tier, no Batch API discount for Omni Flash (unlike other Gemini models).
- ⚠️ Google marks Omni Flash Preview as "content used to improve products" even on paid tier.
