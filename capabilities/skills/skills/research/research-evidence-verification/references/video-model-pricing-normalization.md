# Video-model API pricing normalization

Session reference for comparing direct vendor API prices. Prices below are a dated evidence snapshot, not a permanent catalog; re-open the cited pages before using them in a new decision.

## Reusable worksheet

Record one row per provider/model/mode:

| Field | Required value |
|---|---|
| Source URL | Vendor pricing/API reference, not an aggregator landing page |
| Model ID | Exact API identifier, if published |
| Input mode | Text/image only, video input, video-to-video, regeneration |
| Output | Duration, aspect ratio, resolution/pixel band, audio |
| Billing unit | Per output second, per image, per request, or token |
| Baseline cost | Prefer a 5 s, 16:9, no-video-input example |
| Input-material charges | Images, audio, video duration, reference assets |
| Rounding/minimums | Partial-second rounding and video-input minimum token rules |
| Access/discount caveats | Preview, region, free quota, promotion, taxes, reseller margin |

Never rank a token-priced model from its token rate alone. Apply the provider's consumption formula or use the official calculator/example, and label the result as estimated when the API reports final usage only after generation.

## Evidence snapshot — 6 August 2026

### Alibaba Cloud Model Studio — Wan 3.0
Source: `https://www.alibabacloud.com/help/en/model-studio/model-pricing`

The official table lists `wan3.0-video` as **Invitational Preview** for International deployment:

- 480P: **$0.05/second**
- 720P: **$0.10/second**
- 1080P: **$0.20/second**

The page also shows a 30-second free-quota entry with regional/account caveats. Do not subtract it from steady-state unit economics unless the account and region are verified. The page was marked updated 2026-08-06.

### BytePlus ModelArk — Seedance 2.5
Source: `https://docs.byteplus.com/docs/ModelArk/1099320`

Exact model ID: `dreamina-seedance-2-5-260628`.

- Online token rate, 480P/720P: **$10.70/M tokens without video input**; **$6.40/M tokens with video input**.
- Official estimated 5-second, 16:9 examples without video input: **$0.514 at 480P** (about $0.103/s) and **$1.156 at 720P** (about $0.231/s).
- With video input and a 5-second output: **$0.553–$2.152 at 480P** and **$1.244–$4.838 at 720P**, depending on input-video duration (2–30 s).

Billing is token-based: estimated consumption depends on input-video duration, output duration, width, height, and frame rate. The actual `usage.completion_tokens` value is authoritative after the API call; input-video minimum token limits can apply.

### Black Forest Labs — FLUX 3 Video
Source: `https://bfl.ai/pricing`

Prices are per output video second; partial seconds round up. The official page defines HD as above 0.5 to 1.0 MP/frame and FHD as above 1.0 to 2.0 MP/frame.

- Draft, text/image-to-video: **$0.06/s in HD**.
- Regular text/image-to-video: **$0.17/s HD**, **$0.29/s FHD**.
- Video-to-video: **$0.41/s HD**, **$0.53/s FHD**.
- Audio is included at no extra charge.

Do not compare the Draft rate to a final-quality rate without flagging the mode difference.

### MiniMax — MiniMax-H3
Source: `https://platform.minimax.io/docs/guides/pricing-paygo`

Output pricing is per second:

- 768P: **$0.08/s**
- 2K: **$0.13/s**

Input-material rules matter: audio is free, the first five images are free, additional images cost **$0.04/image**, and video input is billed by input-video duration and output resolution. The page also lists separate regeneration and context-IR prices; do not fold those into ordinary generation pricing.

## Comparison discipline

For a simple 5-second no-video-input comparison, the direct output examples above normalize to:

- Wan 3.0: **$0.25 at 480P**, **$0.50 at 720P**, **$1.00 at 1080P**.
- Seedance 2.5: **$0.514 at 480P**, **$1.156 at 720P**.
- FLUX 3 regular: **$0.85 HD**, **$1.45 FHD**; Draft is **$0.30 HD**.
- MiniMax H3: **$0.40 at 768P**, **$0.65 at 2K**.

These are not a quality benchmark: 768P/720P/HD and 2K/1080P/FHD are different provider-defined bands. Present the resolution and generation mode beside every price, and recalculate when the user specifies a common duration, input type, or reseller.
