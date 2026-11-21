# Kie.ai live video pricing catalog

## Reproducible lookup

As of 2026-07-31, Kie.ai exposes the public pricing catalog at:

```text
POST https://api.kie.ai/client/v1/model-pricing/page
```

Use a browser-shaped `User-Agent` and this body:

```json
{
  "pageNum": 1,
  "pageSize": 100,
  "modelDescription": "",
  "interfaceType": "Video"
}
```

`pageSize` cannot exceed 100. Read `data.pages` and request every page. No generation API key is required for this catalog endpoint. The useful fields are:

- `modelDescription`
- `provider`
- `creditPrice`
- `creditUnit`
- `usdPrice`
- `falPrice`
- `discountRate`
- `anchor`

Do not treat `creditPrice` as a per-second price unless `creditUnit` says `per second`; some models are billed `per video` or `per image`.

## Snapshot used for the comparison on 2026-07-31

These were the live records returned by `interfaceType=Video`:

| Model / variant | Kie credits | Kie USD |
|---|---:|---:|
| `grok-imagine-video-1-5-preview`, image-to-video, 720p | 3 / second | $0.015 / second |
| `grok-imagine-video-1-5-preview`, image-to-video, 480p | 1.6 / second | $0.008 / second |
| `gemini-omni-video`, 720p, no video input, 4s | 63 / video | $0.315 |
| `gemini-omni-video`, 720p, no video input, 6s | 84 / video | $0.42 |
| `gemini-omni-video`, 720p, no video input, 8s | 105 / video | $0.525 |
| `gemini-omni-video`, 720p, no video input, 10s | 126 / video | $0.63 |
| `bytedance/seedance-2`, 720p, no video input | 41 / second | $0.205 / second |
| `bytedance/seedance-2`, 720p, with video input | 25 / second | $0.125 / second |
| `bytedance/seedance-2`, 1080p, no video input | 102 / second | $0.51 / second |
| `bytedance/seedance-2`, 4K, no video input | 208 / second | $1.04 / second |
| `bytedance/seedance-2 fast`, 720p, no video input | 33 / second | $0.165 / second |
| `bytedance/seedance-2-mini`, 720p, no video | 20.5 / second | $0.1025 / second |
| MiniMax H3 / Hailuo, text/image/reference/video, 2K | 36.5 / second | $0.1825 / second |
| MiniMax H3 / Hailuo, image input | 11 / image | $0.055 / image |

## Reporting rules

- State resolution and input mode beside every price.
- Normalize a clip total only when duration is explicit or the rate is truly per-second.
- Keep Kie’s displayed USD and credits together; do not silently convert from a stale exchange assumption.
- The current catalog labels Grok 1.5's priced row as `image-to-video`; mention that caveat when the user asks about pure text-to-video.
- H3 is listed at 2K, so comparing it directly with a 720p model requires an explicit resolution caveat.
