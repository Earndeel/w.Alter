# MiniMax H3 cross-platform pricing — 2026-07-31

Session-specific reference for comparing the same H3 generation workload across OpenRouter, Kie.ai, and fal.ai. Rates are live catalog values observed on 2026-07-31; re-check before reuse.

## Normalized comparison

Scope: 2K output, output-only text-to-video where available, 10-second clip, excluding any account-level minimum-fee effect.

| Platform | Published output rate | 10-second output | Notes |
|---|---:|---:|---|
| OpenRouter — `minimax/hailuo-3` | $0.13/s | $1.30 | Page showed one provider, MiniMax; input $0.00/s. |
| Kie.ai — Hailuo H3 | 36.5 credits/s = $0.1825/s | $1.825 | Kie model-pricing API, Video filter; credit catalog implies $0.005/credit. |
| fal.ai — `minimax/h3/text-to-video` | $0.26/s | $2.60 | 2K output; 5–15 seconds. |

Sticker-price deltas:

- Kie.ai is 40.38% above OpenRouter.
- fal.ai is 100% above OpenRouter and 42.47% above Kie.ai.
- OpenRouter charges a separate 5.5% fee when purchasing credits ($0.80 minimum), not a model-rate markup. If the 5.5% fee is fully amortized, its model-equivalent rate is $0.13715/s and Kie.ai remains about 33.07% higher. The minimum fee can make the effective rate higher for small credit purchases.

## Mode and input caveats

- fal.ai `minimax/h3/text-to-video` publishes $0.26/s at 2K with text only.
- fal.ai `minimax/h3/reference-to-video` also publishes $0.26/s for output, then adds: reference video at $0.26/s, extra reference images at $0.08 each after the first five, and free audio references.
- Do not compare a reference-to-video quote against a text-only quote without recording input assets and their charges.
- A model name is not a pricing contract: verify exact endpoint, resolution, duration, audio behavior, and reference inputs for each platform.

## Why the rates diverge

1. **Different commercial SKU:** the same weights/model family can be exposed through different endpoint contracts, defaults, and service tiers.
2. **OpenRouter pass-through:** its FAQ says it passes through underlying provider pricing without model markup. The H3 page showed MiniMax as the provider, so the $0.13/s rate is the marketplace/provider rate, with the credit-purchase fee handled separately.
3. **Kie.ai retail credits:** Kie publishes a credit-denominated retail SKU. Its public catalog does not provide a cost breakdown, so do not assume its advertised “lower than official API” positioning beats every marketplace rate or every negotiated launch rate.
4. **fal.ai hosted inference:** fal.ai publishes a higher 2K per-second rate for its serverless hosted endpoint. The public page does not expose an internal cost breakdown; explain the difference as provider pricing plus serving/capacity/service economics, not as a proven GPU-cost decomposition.
5. **Launch and negotiated rates:** a newly listed model can have different provider agreements or introductory marketplace rates. Never infer a universal “official H3 price” from one intermediary.

## Reusable verification workflow

1. Fetch the live model page/API for every provider; record the retrieval date and exact endpoint.
2. Normalize to the same output resolution, duration, modality, and reference assets.
3. Separate output charges, input/reference charges, credit-purchase fees, subscription quotas, and minimum fees.
4. Calculate both sticker cost and effective cost for the user's actual purchase size.
5. Report quality/feature differences separately; price equality does not prove identical routing, defaults, quantization, audio, queueing, or output behavior.
6. If a provider page only exposes a search snippet or ambiguous modality label, mark the comparison provisional rather than treating it as exact.

## Sources

- OpenRouter model page: `https://openrouter.ai/minimax/hailuo-3`
- OpenRouter FAQ and fees: `https://openrouter.ai/docs/faq`
- Kie.ai pricing page: `https://kie.ai/pricing`
- Kie.ai model-pricing endpoint: `https://api.kie.ai/client/v1/model-pricing/page`
- fal.ai text-to-video: `https://fal.ai/models/minimax/h3/text-to-video`
- fal.ai reference-to-video: `https://fal.ai/models/minimax/h3/reference-to-video`
