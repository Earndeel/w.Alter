# Seedance 2.5 provider-pricing and access verification — 2026-08-08

Session-specific evidence bank for comparing the standard, non-promotional Seedance 2.5 offers on MuAPI, Kie.ai, Fal.ai, and Higgsfield.ai. Re-open the live sources before making a new pricing decision: these catalogs are mutable.

## Normalization contract

Use a common baseline of **5 seconds, 16:9, no video reference/input** unless the user specifies another duration or mode. If the user has already frozen a 10-second comparison, keep **10 seconds** as the primary output and use 5-second provider examples only as explicitly labelled derivations. Keep 480p and 720p separate. Report the provider billing unit first, then derive a common total only when the source supports it; label derived values as approximate. Do not mix text/image-to-video with video-input or reference-video pricing.

## MuAPI — fixed per-output-second pricing

Official sources:

- `https://muapi.ai/seedance-2.5`
- Public model catalog: `https://api.muapi.ai/api/v1/models`

The standard Seedance 2.5 Text-to-Video and Image-to-Video entries were verified at:

- 720p: **$0.34/output second**; the public catalog's base cost is **$1.70**, consistent with a 5-second estimate.
- 480p: **$0.17/output second**; the public catalog's base cost is **$0.85**, consistent with a 5-second estimate.

The same advertised rate applies to the ordinary 2.5 image/video variants listed on the model page. Keep separate variants such as Spicy/relaxed-moderation out of a standard comparison unless explicitly requested. Do not treat the landing-page “starting at” figure as the canonical 720p rate when the model page and catalog expose the resolution-specific rate.

## Kie.ai — live catalog, not the marketing page

Query the public catalog with a browser-like user agent:

```text
POST https://api.kie.ai/client/v1/model-pricing/page
{"pageNum":1,"pageSize":100,"modelDescription":"","interfaceType":"Video"}
```

Paginate through `data.pages`; the endpoint currently rejects `pageSize > 100`. Filter exact `modelDescription` rows containing `bytedance/seedance-2-5`, and preserve `creditPrice`, `creditUnit`, `usdPrice`, `falPrice`, `discountRate`, `anchor`, and `discountPrice` as evidence.

The verified standard rows were:

| Mode | Rate | 5-second equivalent |
|---|---:|---:|
| 720p, no video input | 63 credits/s = **$0.315/s** | 315 credits = **$1.575** |
| 480p, no video input | 28 credits/s = **$0.140/s** | 140 credits = **$0.70** |
| 720p, with video input | 38 credits/s = **$0.190/s** | 190 credits = **$0.95** |
| 480p, with video input | 17 credits/s = **$0.085/s** | 85 credits = **$0.425** |

For a no-input baseline, use the first two rows. The “with video” rows are a different mode, not a cheaper generic rate. Use Kie’s `usdPrice` as the Kie charge; do **not** substitute `falPrice`, which is a comparison/anchor field. A live response with `discountPrice: false` supports excluding discount/promo logic.

## Fal.ai — token-based, not truly fixed per second

Official endpoint sources:

- `https://fal.ai/models/bytedance/seedance-2.5/text-to-video`
- `https://fal.ai/models/bytedance/seedance-2.5/image-to-video`
- `https://fal.ai/models/bytedance/seedance-2.5/reference-to-video`

The public page states **$0.0214 per 1,000 tokens** and gives approximate common-case rates:

- 720p with audio: approximately **$0.4730/output second** without video references.
- 480p with audio: approximately **$0.2205/output second** without video references.

The authoritative approximation is the token formula:

```text
tokens = (output_height * output_width * (input_video_duration + output_duration) * 24) / 1024
cost = tokens / 1000 * 0.0214 USD
```

The official worked examples include approximately **$2.31 for 5 seconds at 720p 16:9** and **$2.15 for 10 seconds at 480p** (the latter can be halved only as an explicitly derived 5-second estimate, about $1.07, assuming identical dimensions). The displayed per-second figures are rounded and may not multiply exactly to the examples.

If video references are supplied, Fal.ai applies a **0.6 multiplier**, but input-video duration is billed alongside output duration. Therefore the “with video reference” rate is not directly comparable to the no-input baseline. Image and audio references are not billed as input duration on the reference endpoint.

## Higgsfield.ai — no public non-Unlimited unit price

Official sources:

- `https://higgsfield.ai/pricing`
- `https://higgsfield.ai/creator-hub/help-center/credits-and-usage/how-credits-work`
- `https://higgsfield.ai/creator-hub/help-center/ai-models/how-do-i-use-seedance`
- `https://higgsfield.ai/seedance-2.5`

Exclude all plan cards, temporary offers, and Unlimited windows when the user asks for standard pay-per-generation pricing. Higgsfield’s public help center says the exact credit cost is shown on the **Generate** button and varies by model family, resolution, and duration. Its public pages do not expose a stable standalone Seedance 2.5 credit/USD rate.

Higgsfield also states that MCP, CLI, Canvas, and Supercomputer generations deduct credits even when web Unlimited access exists, but that does not create a public numeric tariff. Do not infer a Seedance 2.5 USD rate from monthly-plan credit bundles or from Unlimited offer prices. Report **“not publicly published; requires the logged-in Credit Mode quote”** rather than inventing a number.

## Atlas Cloud — parameterized quote still unresolved

Official model pages:

- `https://www.atlascloud.ai/models/bytedance/seedance-2.5/text-to-video`
- `https://www.atlascloud.ai/models/bytedance/seedance-2.5/image-to-video`
- `https://www.atlascloud.ai/models/bytedance/seedance-2.5/reference-to-video`

A fresh rendered fetch of the **text-to-video** page on 2026-08-08 exposed duration controls (4–30 seconds, default 5), 480p/720p controls, and a live UI quote of **“Run ≈$1.514799” / “Your request will cost $1.514799 per run”** for the rendered default state. The same page also contains related-model cards labelled **$0.134/SEC**, while search/indexed text for the image-to-video page has shown **$0.134 per run**; these are not the same mode or a parameterized 10-second quote.

Evidence classification: Atlas is **not normalized for the standard text-to-video baseline** until a fresh quote is captured with explicit 10-second, 720p, 16:9 parameters. Do not use `$0.134` as a generic Seedance 2.5 rate, and do not rank Atlas against fixed per-second providers from the headline alone. Preserve the unit/mode contradiction explicitly; a low “From” card is not automatically the cheapest comparable offer.

## BytePlus ModelArk — international first-party access route

Official sources:

- Signup: `https://console.byteplus.com/auth/signup?redirectURI=https%3A%2F%2Fwww.byteplus.com%2Fen&skipAccountProfile=true`
- Pricing/API documentation: `https://docs.byteplus.com/en/docs/ModelArk/1099320`
- Video task API documentation: `https://docs.byteplus.com/en/docs/ModelArk/1520757`

The public BytePlus signup page rendered on 2026-08-08 with **email, username, password, and Google sign-in** fields and no phone-country selector on the initial form. This proves an email-based initial signup path, not that later identity/payment checks are absent.

The official ModelArk pricing page lists the Seedance 2.5 model ID **`dreamina-seedance-2-5-260628`** and states for **input without video**:

- 480p, 16:9, 5 seconds: **$0.514/video** ($0.103/second).
- 720p, 16:9, 5 seconds: **$1.156/video** ($0.231/second).

A 10-second 720p equivalent is therefore **approximately $2.312** when the published per-second example is used linearly. Keep it labelled derived: the official worked example shown here is 5 seconds, and the actual API response's token usage is authoritative.

Access classification for a Thai user: BytePlus is the **cheapest usable first-party route** in this evidence set when the China-only Volcano signup is unavailable. It is about **$0.072 / 3.21% above** the earlier verified Volcano 10-second equivalent of $2.24, before any taxes/payment fees; do not trade durable access for a shared or recycled OTP number solely to recover that small difference.

## Volcano Engine / 火山方舟 — transparent official token pricing

Official current price page: `https://docs.volcengine.com/docs/82379/1544106?lang=zh`

For `doubao-seedance-2.5` online inference, the page states:

- Output resolution: 480p or 720p.
- **No input video:** ¥70 per million tokens.
- **With input video:** ¥42 per million tokens.
- Offline inference: not supported.
- Estimated token usage: `(input_video_duration + output_duration) * output_width * output_height * output_fps / 1024`.
- Only successful video generations are billed; the returned API `usage.completion_tokens` is authoritative over the estimate.

Official 5-second, 16:9, no-input examples:

| Output | Official cost | Official rate | Approx. USD* |
|---|---:|---:|---:|
| 480p | ¥3.36/video | ¥0.67/s | $0.50 |
| 720p | ¥7.56/video | ¥1.51/s | $1.12 |

With a 5-second output and an input video of 2–30 seconds, the same page gives ranges of **¥3.63–¥14.12** at 480p and **¥8.16–¥31.75** at 720p. Keep these in a separate input-video section; they are not substitutes for the no-input baseline.

The page's active limited-offer block applies to Seedance 2.0 mini and Seedance 2.0 fast, not Seedance 2.5. Do not apply those discounts to the 2.5 list price. Preserve CNY as the canonical provider currency; USD values are only approximate conversions (the session used 1 USD = ¥6.763426 from a timestamped FX lookup).

## Output and evidence rules

1. Start with the verdict and state the frozen baseline.
2. Separate fixed per-second, live-credit-catalog, token-based, and unpublished-credit pricing.
3. Show provider currency/credits and the derived 5-second equivalent separately.
4. Keep video-input/reference-video rows in a secondary note, with the input-duration rule.
5. Explicitly say when a price is approximate or derived.
6. Exclude promotions, trials, Unlimited offers, subscription-plan economics, and reseller comparison fields unless the user asks for them.
7. Include the raw official source URLs as plain text or code, never as hidden markdown links.
