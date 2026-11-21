# AA Video × OpenRouter × Kie.ai — validated comparison recipe

Use this reference when Monsieur asks for a complete comparison of video-generation models, benchmark quality, and provider prices. It records the live extraction pattern validated on 2026-08-11; the counts and prices are a parser smoke test, not a reusable current snapshot.

## Scope and completeness rule

“All video models” means the union of the current Artificial Analysis video leaderboards, not only the two models named in the previous exchange:

- `https://artificialanalysis.ai/video/leaderboard/image-to-video`
- `https://artificialanalysis.ai/video/leaderboard/text-to-video`
- `https://artificialanalysis.ai/video/leaderboard/video-editing`

The three tables can contain different model variants and different scores. Keep one record per board first, then build a deduplicated cross-provider table. Never discard a model because it is absent from one mode. Also report provider-only models that are present in OpenRouter/Kie but absent from AA; this catches newly listed models such as a new Seedance version.

A validated run returned 65 AA board rows and 31 unique model labels, 22 OpenRouter video-generation catalog entries, and 219 Kie video-pricing records. Treat these as smoke-test expectations only: live catalogs change.

## AA extraction contract

The AA video pages expose usable HTML tables even when the visual page is client-rendered. Parse every table row with these columns:

```text
rank, rank_range, creator, model, elo, ci95, samples, released, aa_api_price_1080p_per_min
```

`API Pricing` is AA’s displayed cost for one minute of 1080p video through the model creator’s API at default settings. It is not automatically the OpenRouter or Kie tariff and must not be substituted for either provider’s price.

The default leaderboard view is **With Audio**. Record that state in the report. Elo is a blind-preference benchmark, not a technical guarantee; do not present it as a resolution-specific score or as proof that one provider route produces identical output quality.

Retain the confidence interval and sample count. A four-point Elo lead with overlapping intervals is not the same evidence as a large non-overlapping lead.

## OpenRouter extraction contract

Start with the dedicated generation catalog:

```text
GET https://openrouter.ai/api/v1/videos/models
```

The response contains exact model IDs, supported resolutions/durations, and `pricing_skus`. The catalog is the authoritative model-availability check, but its token-priced SKUs are not always convenient clip tariffs.

For each matched model, fetch its public model page, for example:

```text
https://openrouter.ai/bytedance/seedance-2.5
```

OpenRouter’s page embeds a `displayPricing` array in escaped Next/RSC data. The validated extraction pattern is:

```python
m = re.search(
    r'\\"displayPricing\\":(\[.*?\]),\\"compareHref\\"',
    html,
    re.S,
)
display_pricing = json.loads(
    bytes(m.group(1), 'utf-8').decode('unicode_escape')
)
```

Prefer `displayPricing` for normalized `/second` tiers such as `720p`, `1080p`, and `4K`; preserve the raw `pricing_skus`/`/M tokens` entries in the evidence record. Do not manufacture a 5-second amount from a raw `video_tokens` rate unless OpenRouter exposes the corresponding normalized tier or a completed usage cost.

OpenRouter model pages may expose separate prices for:

- video with audio;
- video without audio;
- video with video input;
- reference/image input;
- resolution tiers;
- continuation segments.

Keep these as separate fields. An image-input surcharge is not the same thing as a video-input generation rate.

## Kie.ai extraction contract

Use the public pricing catalog, not a cached landing-page table:

```text
POST https://api.kie.ai/client/v1/model-pricing/page
Content-Type: application/json

{
  "pageNum": 1,
  "pageSize": 100,
  "modelDescription": "",
  "interfaceType": "Video"
}
```

`pageSize > 100` is rejected. Read `data.pages`, fetch every page, then filter the full result set by `modelDescription` and `provider`.

Preserve these fields for every candidate row:

```text
modelDescription, provider, creditPrice, creditUnit,
usdPrice, discountRate, discountPrice, falPrice, anchor
```

Kie’s `usdPrice` is the displayed Kie price. Do not report `falPrice` as Kie’s tariff. Preserve the billing unit exactly: `per second`, `per video`, `per image`, or another literal unit. Kie may expose a route for a model family rather than the exact model variant; mark that as `family_match`, not `exact_match`.

## Matching rules

Use exact OpenRouter IDs where available. For AA labels, maintain an explicit canonical map rather than relying only on fuzzy text:

```text
Dreamina Seedance 2.0 720p -> bytedance/seedance-2.0
MiniMax H3 Open Weights -> minimax/hailuo-3
grok-imagine-video-1.5 -> x-ai/grok-imagine-video-1.5
HappyHorse-1.1 -> alibaba/happyhorse-1.1
HappyHorse-1.0 -> alibaba/happyhorse-1.0
Wan 2.7 / Wan2.7-260612 -> alibaba/wan-2.7 (family/variant match)
Veo 3.1 -> google/veo-3.1
Veo 3.1 Fast -> google/veo-3.1-fast
Veo 3.1 Lite -> google/veo-3.1-lite
Kling 3.0 Pro -> kwaivgi/kling-v3.0-pro
Kling 3.0 Standard -> kwaivgi/kling-v3.0-std
Seedance 1.5 pro -> bytedance/seedance-1-5-pro
Wan 2.6 -> alibaba/wan-2.6
Aleph 2.0 -> runway/aleph-2
```

Do not map `Kling 3.0 Omni` to ordinary `Kling 3.0` as an exact match. Do not map `Seedance 2.5` to AA’s `Seedance 2.0` score. Keep “absent from AA” and “absent from provider catalog” as explicit statuses.

## Normalization worksheet

Freeze the comparison baseline before reading prices:

```text
output duration: 5 seconds
aspect ratio: 16:9 when supported
video input: none
reference images: none unless the model requires one
audio: state no-audio or with-audio explicitly
```

Convert only a genuine per-second price:

```text
clip_total_5s = price_per_second * 5
```

Do not convert these into fake 5-second prices:

- `per video` where the duration is not exposed;
- `per image` reference charges;
- `video_tokens` or `/M tokens` without a normalized tier or usage cost;
- minimum-generation charges;
- a 4-second or 6-second Kie quote presented as an exact 5-second quote.

When a provider exposes only 4s/6s/8s/10s package prices, list the exact package values and label the 5-second baseline unavailable. When resolution differs, keep separate rows; `768p`, `720p`, `1080p`, `2K`, and `4K` are not interchangeable.

## Output contract

Produce three views:

1. **AA-ranked model table:** model, creator, I2V Elo/rank, T2V Elo/rank, editing Elo/rank, confidence/sample data.
2. **Provider comparison:** exact OpenRouter ID and price fields, Kie catalog route and price fields, resolution/mode/unit, and `exact_match` vs `family_match` vs `missing`.
3. **Provider-only appendix:** OpenRouter/Kie video models with no AA leaderboard record.

A compact row should look like:

```text
model | AA scores by board | OpenRouter 5s baseline | Kie 5s/package baseline | match status | evidence URL
```

Lead with the practical verdict, but explain whether it is based on benchmark quality, nominal price, or cheapest usable route. There is no universal provider winner: the validated comparison showed OpenRouter cheaper for several ByteDance/HappyHorse routes, Kie cheaper for Grok/Wan/Veo/Kling routes, and a near-tie for H3 at 2K.

## Verification checklist

- [ ] All three AA leaderboards were fetched, not only a named-model page.
- [ ] AA board rows were retained before deduplication.
- [ ] AA default audio state is stated.
- [ ] OpenRouter availability came from `/api/v1/videos/models`.
- [ ] Token-priced OpenRouter models were checked against the model-page `displayPricing` array.
- [ ] Kie catalog pagination completed with `pageSize=100`.
- [ ] `usdPrice` and the original Kie billing unit were preserved.
- [ ] Exact and family matches are separated.
- [ ] Resolution, audio, input-video, reference-image, and continuation charges are not conflated.
- [ ] Per-video and token units were not silently converted to exact 5-second totals.
- [ ] Provider-only models were reported.
- [ ] Source URLs and retrieval timestamp are included.
