# API and model-pricing comparisons, and access as a separate constraint

(Moved unchanged from SKILL.md on 2026-11-27.)

For current API/model prices, normalize the comparison before ranking it:

1. Freeze one baseline (for video, normally 5 seconds, 16:9, no video input) and state whether the comparison is output-only or includes input materials.
2. Preserve the provider's billing unit: per second, per image, per request, or token-based. Derive a common equivalent only when the source gives enough information; label derived values as approximate.
3. Keep resolution bands semantically separate. `HD`, `FHD`, `720P`, `768P`, `1080P`, and `2K` are not interchangeable merely because they sound similar.
4. Separate text/image-to-video from video-to-video, and no-video-input from video-input prices. Video-input models often apply duration-dependent minimums, so never reuse the no-input rate.
5. Capture hidden or adjacent charges: audio, reference images, input-video duration, regeneration, rounding of partial seconds, free quotas, preview/invitation status, taxes, and reseller margins.
6. Prefer the vendor's pricing page or API reference over marketplace listings. If a static extractor returns only shell/navigation or the extraction backend is search-only, switch to a rendered structured extractor and preserve the raw source URL plus the exact table context.
7. Treat conflicting billing units as an evidence problem, not a conversion problem. If a provider's page simultaneously says `per run`, `per second`, or `per 1M tokens`, preserve each exact label, identify which view produced it, and do not multiply a headline `From` price into a normalized total unless the provider exposes the parameterized formula or quote.
8. For regional first-party providers, preserve the native currency and the official worked examples first. Only convert to USD with a timestamped FX source and label the result approximate; do not let conversion hide a difference between a list price, a temporary promotion, and an adjacent model's price.

### Video-generation benchmark × provider comparison (AA + OpenRouter + Kie.ai)

When Monsieur asks for **all video models**, do not answer with only the models mentioned in the preceding exchange. Build the exhaustive comparison from the live Artificial Analysis video leaderboards, then join provider catalogs:

1. Fetch and parse all three AA tables: `/video/leaderboard/image-to-video`, `/video/leaderboard/text-to-video`, and `/video/leaderboard/video-editing`. Keep rank, Elo, 95% confidence interval, sample count, release month, creator, and AA's displayed API price. Deduplicate only for the cross-model table; retain the per-board scores because a model can be strong in editing but absent from T2V.
2. Fetch OpenRouter's dedicated generation catalog at `https://openrouter.ai/api/v1/videos/models`. Treat `pricing_skus` as discovery metadata, not always as a directly comparable clip tariff. For token-priced models (notably Seedance), fetch the public model page as well and prefer its `displayPricing` tiers, which expose normalized `/second` prices and resolution/audio/input variants. Preserve the raw token SKU in evidence but never invent a clip total from token price alone. Pitfall: the generic `/api/v1/models` list contains NO video models — a "flux" search over it returns zero hits while the videos catalog lists 24 (verified 2026-08-21). Always search the modality-specific catalog. Per-model API contracts are published as `https://openrouter.ai/<model-id>/llms.txt` (endpoint, request fields, job polling, response shape) — read that instead of guessing the wire format.
3. Fetch Kie.ai's public catalog with `POST https://api.kie.ai/client/v1/model-pricing/page`, body `interfaceType: "Video"` (or `"Image"`), `pageSize: 100`, `pageNum: N`. Verified response shape (2026-08-21): rows live in `data.records`; `data.pages` is an INTEGER total-page count, not a list — paginate `pageNum` from 1 to `data.pages` and dedupe rows across pages. Filter by `modelDescription`/`provider`, preserving `usdPrice`, `creditPrice`, `creditUnit`, resolution, audio/input mode, and anchor URL. Kie may expose a family route rather than the exact provider model ID; label those rows as family matches.
4. Freeze one baseline before normalizing: normally 5 seconds, 16:9, no video input, with audio/no-audio stated explicitly. Convert only genuine `/second` rates to a 5-second total. Keep `per video`, `per image`, `video_tokens`, minimum-generation charges, and unspecified-duration rates in their native units; do not call them exact 5-second prices.
5. Report three sets separately: (a) AA models with exact OpenRouter and/or Kie matches, (b) AA models missing from a provider catalog, and (c) provider-only generation models absent from AA, such as a newly listed Seedance version. Do not silently treat a family match as an exact match.
6. The AA video leaderboards are blind-preference Elo benchmarks, not a technical quality guarantee. State whether the page is the default With Audio view, and do not compare an AA model-level score as if it were a resolution-specific provider quote.

The validated extraction recipe, matching notes, and evidence fields are in `references/aa-video-provider-comparison.md`.

### Image-generation price normalization (GPT Image 2 class)

For image models that mix flat marketplace tiers with token-priced native/proxy APIs:

1. Freeze exact output dimensions and quality before comparing. Do not equate Kie `1K/2K/4K` with OpenRouter `low/medium/high`; they are different axes, and Kie’s flat tier does not by itself expose a public quality mapping.
2. Query Kie’s public image catalog with `interfaceType: "Image"`, preserve `creditPrice`, `creditUnit`, `usdPrice`, `discountPrice`, and `falPrice`, and report Kie’s `usdPrice` rather than the reseller/anchor `falPrice`.
3. Query OpenRouter’s dedicated image catalog (`/api/v1/images/models`) and model endpoint, not only the generic text-model list. Record the exact model ID and separate text-input, reference-image-input, and image-output token prices.
4. When OpenRouter has no flat per-image tariff, use the model’s official output-token calculator or a completed `usage.cost`; label derived output-only numbers as estimates and add prompt/reference-image charges separately.
5. State whether the comparison is output-only or all-in. For image-to-image, input reference images can materially change OpenRouter’s cost; never present a text-to-image output estimate as the total edit cost.

The GPT Image 2-specific live endpoints, calculator formula, and 2026-08-11 evidence snapshot are in `references/gpt-image-2-provider-pricing.md`.

## Access is a separate constraint from price

For provider-access decisions, rank two different outputs:

- **Absolute cheapest** — the lowest verified generation tariff, even if signup is region-locked.
- **Cheapest usable** — the lowest tariff available to the user's region with a durable account, supported billing, API access, and no fragile shared/temporary credential.

Verify the access path independently from the price:

1. Inspect the provider's real signup page and record whether it accepts the user's country/phone, email-only signup, or requires enterprise onboarding. A reseller's SMS page is not evidence that the first-party form accepts that country code.
2. Search the same vendor family for an international first-party service or regional endpoint before recommending rented OTP numbers. Verify that it exposes the same model family, exact API model ID, output modes, and billing unit.
3. Include access friction in the recommendation: identity verification, payment availability, account durability, regional terms, and whether an API key can actually be created. Do not recommend shared/recycled SMS numbers as a durable access strategy.
4. Calculate the break-even honestly. If an international first-party route is only a few percent more expensive than a region-locked route, it is normally the cheaper usable option once account risk and setup time are included.
5. State the verdict in the form: `absolute cheapest: X; cheapest usable from the user's region: Y; difference: Z`. Keep the two rankings separate rather than forcing a nominal winner.

See `references/video-model-pricing-normalization.md` for a reusable worksheet and a worked evidence snapshot. For the dated Seedance 2.5 provider-price evidence, including the international BytePlus access route, see `references/seedance-2-5-provider-pricing.md`. For the dated 2026-08-21 FLUX 3 price-and-access evidence (BFL direct Draft vs Standard, OpenRouter, Kie/fal/Replicate absence, Nous promo end), see `references/flux3-video-provider-pricing.md`.
