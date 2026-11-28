# GPT Image 2 provider pricing — live evidence snapshot

**Captured:** 2026-08-11. Re-open the live endpoints before making a new pricing decision; both catalogs are mutable.

## Frozen comparison rule

Do not compare a flat marketplace tier directly with a token-priced proxy without fixing output dimensions and quality. Kie’s `1K/2K/4K` labels are resolution tiers; OpenRouter’s `low/medium/high` are quality settings. They are not interchangeable, and Kie’s public catalog does not expose a quality mapping for its flat tier.

Report whether the figure is **output-only** or **all-in**. Add prompt text and reference-image input charges for OpenRouter when relevant, especially for image-to-image.

## Kie.ai — public Market pricing catalog

Endpoint:

```text
POST https://api.kie.ai/client/v1/model-pricing/page
```

Request shape used:

```json
{"pageNum":1,"pageSize":100,"modelDescription":"","interfaceType":"Image"}
```

Live GPT Image 2 rows returned by the catalog:

| Mode | Tier | Billing | Kie USD | Credits |
|---|---|---|---:|---:|
| Text-to-image | 1K | per image | $0.03 | 6 |
| Text-to-image | 2K | per image | $0.05 | 10 |
| Text-to-image | 4K | per image | $0.08 | 16 |
| Image-to-image | 1K | per image | $0.03 | 6 |
| Image-to-image | 2K | per image | $0.05 | 10 |
| Image-to-image | 4K | per image | $0.08 | 16 |

The rows showed `discountPrice: false`. Preserve Kie’s `usdPrice`; `falPrice` is a comparison/anchor field, not Kie’s charge.

Model page: `https://kie.ai/gpt-image-2`

Kie slugs:

```text
gpt-image-2-text-to-image
gpt-image-2-image-to-image
```

## OpenRouter — dedicated image catalog

Exact model ID verified:

```text
openai/gpt-image-2
```

Do not use only the generic text-model list. Query:

```text
GET https://openrouter.ai/api/v1/images/models
GET https://openrouter.ai/api/v1/images/models/openai/gpt-image-2/endpoints
```

Current endpoint pricing:

| Billable item | USD per token |
|---|---:|
| Text input | $0.000005 ($5/M) |
| Reference image input | $0.000008 ($8/M) |
| Image output | $0.000030 ($30/M) |

The dedicated catalog exposes `quality` values `low`, `medium`, `high`, and `auto`, up to 16 reference images, and aspect-ratio controls. OpenRouter does not publish one fixed per-image price for GPT Image 2; the image-output charge depends on requested dimensions and quality.

Model page: `https://openrouter.ai/openai/gpt-image-2`
OpenRouter guide: `https://openrouter.ai/openai/gpt-image-2/llms.txt`

## OpenAI GPT Image 2 output-token calculator

Official calculator/source: `https://developers.openai.com/api/docs/guides/image-generation`

The calculator JavaScript defines quality bases:

```text
low    = 16
medium = 48
high   = 96
```

For width `w`, height `h`, and quality base `q`:

```text
longest  = max(w, h)
shortest = min(w, h)
short_base = round(q * shortest / longest)
width_base, height_base = q/short_base according to orientation
output_tokens = ceil((width_base * height_base) * (2,000,000 + w*h) / 4,000,000)
```

The official calculator requires both dimensions to be divisible by 16, pixel budget between 655,360 and 8,294,400 inclusive, maximum edge 3,840 px, and aspect ratio no greater than 3:1.

### Output-only reference calculations

These numbers use the live OpenRouter image-output price of $30/M tokens and exclude prompt/reference-image input:

| Dimensions | Low | Medium | High |
|---|---:|---:|---:|
| 1024×1024 | $0.00588 | $0.05268 | $0.21072 |
| 1536×1024 | $0.00474 | $0.04116 | $0.16464 |
| 2048×2048 (≈2K square) | $0.01191 | $0.10704 | $0.42816 |
| 3840×2160 (≈4K UHD 16:9) | $0.01113 | $0.10008 | $0.40026 |

Use these as dimension-specific estimates, not as generic `1K/2K/4K` OpenRouter tariffs. The final completed response’s `usage.cost` is authoritative.

## Reporting pattern

- For Kie: report the exact tier, `per image`, credits, and displayed USD.
- For OpenRouter: report exact dimensions, quality, output-only vs all-in, token rates, and derived output cost or completed `usage.cost`.
- For image edits: add reference-image input cost and state that Kie’s flat public row and OpenRouter’s tokenized input are not a like-for-like total unless the input material is fixed.
- If recommending a provider, separate `cheapest nominal output` from `cheapest comparable quality`; do not call Kie’s default quality “medium” without evidence.
