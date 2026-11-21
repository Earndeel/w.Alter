# Kie.ai ↔ OpenRouter live video pricing — evidence snapshot 2026-08-26

This is a dated evidence snapshot, not a permanent tariff. Re-query both catalogs before making a paid decision.

## Sources and retrieval

- Kie.ai public pricing catalog: `POST https://api.kie.ai/client/v1/model-pricing/page`
  - JSON body: `{"pageNum": N, "pageSize": 100, "modelDescription": "", "interfaceType": "Video"}`
  - Browser-shaped `User-Agent`; paginate `pageNum=1..data.pages`.
  - The live request returned HTTP 200 across the selected pages and 251 Video rows in total.
- OpenRouter dedicated video catalog: `GET https://openrouter.ai/api/v1/videos/models`
  - Live response: HTTP 200, 26 video-model rows.
  - Do not use the generic `GET https://openrouter.ai/api/v1/models` list as the sole video check.
- For model-specific OpenRouter pricing/contract context, read the model page and `https://openrouter.ai/<model-id>/llms.txt`.

## Normalization used in the comparison

- USD, before tax, 5 seconds, 16:9, no video input.
- Preserve Kie `usdPrice`, `creditPrice`, and `creditUnit` separately; do not infer a universal USD-per-credit conversion from one row.
- Convert only genuine per-second prices to a 5-second total.
- Seedance OpenRouter rows are token-priced. Derived output-only estimates used the provider's video-token formula:
  `tokens = width × height × duration_seconds × 24 / 1024`.
  At 1280×720 for 5 seconds this is 108,000 tokens.
- For token-priced jobs, final `usage.cost` is authoritative; the normalized values below are estimates.

## Kie.ai rows observed

The following exact `modelDescription` values and displayed prices were returned by the live Video catalog:

| Model description | Kie price | Billing | Notes |
|---|---:|---|---|
| `wan 3.0 video, 480p, video` | $0.04/s; 8 credits/s | per second | standard row |
| `wan 3.0 video, 720p, video` | $0.16/s; 16 credits/s | per second | USD/credit relationship differs from adjacent rows; preserve literally |
| `wan 3.0 video, 1080p, video` | $0.16/s; 32 credits/s | per second | standard row |
| `wan3.0 video prime, 480p, video` | $0.0612/s; 12.2 credits/s | per second | separate Prime variant |
| `wan3.0 video prime, 720p, video` | $0.126/s; 25.2 credits/s | per second | separate Prime variant |
| `wan3.0 video prime, 1080p, video` | $0.252/s; 50.4 credits/s | per second | separate Prime variant |
| `MiniMax H3, ... 768p` | $0.08/s; 16 credits/s | per second | text/image/reference/video variants returned at this rate |
| `MiniMax H3, ... 2K` | $0.13/s; 26 credits/s | per second | text/image/reference/video variants returned at this rate |
| `MiniMax H3, image input, 768p, 2k` | $0.04; 8 credits | per image | separate input charge |
| `bytedance/seedance-2-5, 480p no video input` | $0.14/s; 28 credits/s | per second | Kie family label |
| `bytedance/seedance-2-5, 720p no video input` | $0.315/s; 63 credits/s | per second | Kie family label |
| `bytedance/seedance-2-5, 1080p no video input` | $0.57/s; 114 credits/s | per second | OpenRouter catalog did not list this resolution for the same row |
| `bytedance/seedance-2 fast, 480p no video input` | $0.059/s; 11.7 credits/s | per second | Kie label is `2 fast`, not `2.0 fast` |
| `bytedance/seedance-2 fast, 720p no video input` | $0.124/s; 24.8 credits/s | per second | Kie label is `2 fast`, not `2.0 fast` |
| `grok-imagine-video-1-5-preview, image-to-video, 480p` | $0.012/s; 2.4 credits/s | per second | exact 1.5 Preview listing is I2V |
| `grok-imagine-video-1-5-preview, image-to-video, 720p` | $0.0225/s; 4.5 credits/s | per second | exact 1.5 Preview listing is I2V |
| `gemini-omni-video, 720p, no video input, 4s` | $0.315; 63 credits | per video | fixed-duration offer |
| `gemini-omni-video, 720p, no video input, 6s` | $0.42; 84 credits | per video | fixed-duration offer |
| `gemini-omni-video, 720p, no video input, 8s` | $0.525; 105 credits | per video | fixed-duration offer |
| `gemini-omni-video, 720p, no video input, 10s` | $0.63; 126 credits | per video | fixed-duration offer |

No current Kie Video row matched FLUX 3 in this snapshot.

## OpenRouter rows observed

The dedicated catalog returned these exact model IDs and pricing SKUs:

- `alibaba/wan-3.0`: `$0.05/s` at 480p, `$0.10/s` at 720p, `$0.20/s` at 1080p; audio generation exposed.
- `black-forest-labs/flux-3-video`: `$0.17/s` at 720p, `$0.29/s` at 1080p; continuation SKUs `$0.41/s` and `$0.53/s`.
- `minimax/hailuo-3`: `$0.13/s` at 2K; reference-image SKU `$0.04/image`.
- `bytedance/seedance-2.5`: `$0.0000107/video token`, with `$0.0000064/video token` for video input; catalog resolutions 480p/720p.
- `bytedance/seedance-2.0-fast`: `$0.0000042/video token`, with `$0.000002475/video token` for video input; catalog resolutions 480p/720p.
- `x-ai/grok-imagine-video-1.5`: `$0.08/s` at 480p, `$0.14/s` at 720p, `$0.25/s` at 1080p; `$0.01/image` input.
- No OpenRouter model ID matched `gemini` or `omni` in the 26-row video catalog.

The OpenRouter Wan model page also displayed a current 15% discount badge; keep the API/catalog nominal price and the promotional page price as separate evidence. Do not silently rewrite `$0.05/s` to `$0.0425/s` without saying that the latter is promotional.

## 5-second 720p reference totals

| Model | Kie.ai | OpenRouter |
|---|---:|---:|
| Wan 3.0 standard | $0.80 | $0.50 nominal; about $0.425 if the displayed 15% promotion applies |
| Wan 3.0 Prime | $0.63 | $0.50 nominal |
| FLUX 3 | no row | $0.85 |
| MiniMax H3 at 2K | $0.65 | $0.65, plus any reference-image charge |
| Seedance 2.5, no video input | $1.575 | about $1.1556, token-derived |
| Seedance 2.0 Fast, no video input | $0.62 | about $0.4536, token-derived |
| Grok Imagine Video 1.5 Preview, I2V | $0.1125 | $0.70 output-only, or $0.71 with one image |
| Gemini Omni | fixed Kie offers above; no 5-second row | no catalog row |

## Interpretation safeguards

- Keep `wan 3.0 video` and `wan3.0 video prime` as separate variants. At Kie, the standard 720p row is internally unusual (`16 credits/s` and `$0.16/s` while adjacent rows do not follow the same ratio); report the returned USD value and flag the inconsistency instead of correcting it.
- Do not merge Kie's exact `grok-imagine-video-1-5-preview` I2V row with the generic `grok-imagine` T2V family row without labeling the model/input mismatch.
- Do not compare Kie's fixed `per video` Gemini Omni offers as an exact 5-second tariff.
- Do not compare Seedance 1080p Kie rows against OpenRouter when the OpenRouter live catalog only exposes 480p/720p for that model.
- The price winner is not a quality winner; audio behavior, reference inputs, output resolution, account eligibility, and final usage can change the usable choice.
