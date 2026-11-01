# Video model pricing — Wan 3.0 / Seedance 2.5 / FLUX 3 / MiniMax H3 — 2026-08-07

Four-model comparison, verified 2026-08-07 against official/provider pages and
current aggregator articles. Dated snapshot — re-check before reuse.

## Comparative table (USD per second of output)

| Model | Best / official rate | Variants | Notes |
|---|---|---|---|
| MiniMax H3 (Hailuo 3) | **$0.13/s** (2K), $0.09/s (768p) | fal.ai $0.26/s · Kie.ai ~$0.1825/s (36.5 credits/s) · OpenRouter $0.13/s | 768P in closed beta; unchanged since the 07-31 H3 reference |
| FLUX 3 (BFL) | **$0.06/s** draft HD → $0.17/s HD → $0.29/s FHD | t2v/i2v; v2v = $0.12 / $0.41 / $0.53/s | Audio included; up to 20 s per generation |
| Seedance 2.5 | Fal.ai **~$0.4730/s (720p)**, ~$0.2205/s (480p) | Kie.ai **$0.315/s (720p, no video input)**, $0.190/s (720p, with video input); Fal bills $0.0214/1K tokens | Fal public endpoints are live; 5s 720p 16:9 is ~$2.31 by the authoritative token formula |
| Wan 3.0 | Open-weight Apache 2.0 (1.3B + 14B, ~Apr 2026) — **no stable hosted API SKU yet** | Reference commercial point: Wan 2.7 = **$0.10/s** (fal.ai & OpenRouter) | API access "rolling out" per wan27.org (2026-08-02); not on OpenRouter/Replicate as of 08-06 |

## Key facts per model

- **FLUX 3 (official BFL pricing, via the-decoder & bfl.ai):** Draft mode is
  HD-only at $0.06/s t2v & i2v, $0.12/s v2v. Full quality HD $0.17/s (t2v/i2v),
  $0.41/s v2v. Full HD (1080p) $0.29/s, $0.53/s v2v. Audio included.
- **Seedance 2.5:** Fal.ai's public text-to-video, image-to-video, and reference-to-video endpoints are live. Fal charges **$0.0214 per 1,000 tokens**, with `tokens = (output_height × output_width × duration_seconds × 24) / 1024`; the page's 5s 720p 16:9 example is 108,000 tokens, **~$2.31**. The page shows the common 16:9 approximation **~$0.4730/s at 720p** and **~$0.2205/s at 480p**. Video inputs apply a 0.6 multiplier to the rate but are also charged for their input duration. Kie.ai's live public pricing catalog lists **$0.315/s (63 credits/s) at 720p without video input**, **$0.190/s (38 credits/s) with video input**, **$0.140/s at 480p without video input**, and **$0.085/s with video input**; its `falPrice` fields mirror Fal's displayed per-second approximations.
- **Wan 3.0:** flagship open-weight release (1.3B consumer + 14B pro, Apache 2.0,
  weights ~April 2026). New ecosystem models July 2026: WanSong (music),
  Wan-Dancer-14B (dance), Wan-Streamer (real-time). No SKU priced on
  fal/OpenRouter/Replicate as of 08-06; Wan 2.7 is the commercial reference.

## Sources

- the-decoder.com/black-forest-labs-makes-flux-3-video-generally-available... (BFL pricing)
- bfl.ai/models/flux-3 · bfl.ai/pricing
- fal.ai/models/bytedance/seedance-2.5/text-to-video · fal.ai/models/bytedance/seedance-2.5/image-to-video · fal.ai/models/bytedance/seedance-2.5/reference-to-video (live pricing, 2026-08-07)
- api.kie.ai/client/v1/model-pricing/page with `interfaceType: Video` (live Kie catalog, 2026-08-07)
- evolink.ai/seedance-2-5 (release status + historical Volcengine/BytePlus token rates)
- wan27.org/blog/latest-wan-model (2026-08-02) · wan27.org/blog/wan-3-0-everything-we-know
- platform.minimax.io (H3 video packages) · openrouter.ai/minimax/hailuo-3
- Previous: `h3-cross-platform-pricing-july-2026.md` (2026-07-31, H3 detail)

## Verification workflow quirks (video-pricing class)

1. **OpenRouter `/api/v1/models` JSON does NOT list video models.** The public
   endpoint (400 models) had no wan/seedance/flux/hailuo entry even for models
   confirmed live elsewhere. Absence there proves nothing — check the model page
   or search instead.
2. **OpenRouter model-page curl heuristic:** a live model page ≈ 300 KB HTML with
   `<script id="__NEXT_DATA__">`; a 404 page ≈ 148 KB with no NEXT_DATA. Use the
   byte-size + NEXT_DATA presence to distinguish live from dead slugs.
3. **fal.ai blocks plain curl with a Vercel Security Checkpoint.** Don't hammer
   it; get fal prices from web_search results / aggregator articles, or use the
   browser stack if a live page is required.
4. **web_extract with the Brave-search backend cannot fetch URL bodies** (search
   only) — use `curl` + regex-strip for server-rendered pages (the-decoder,
   evolink, wan27 all work) or `browser_navigate` for JS-heavy SPAs.
5. **web_search intermittently returns HTTP 429 under parallel batches** — fire
   price queries sequentially, not 3–4 at once.
6. **Per-token pricing must be converted with the provider's formula, not guessed.**
   Seedance 2.5 is now public on Fal.ai: use $0.0214 per 1,000 tokens and the
   published frame-area formula; for the standard 5s 720p 16:9 case, the page
   gives 108,000 tokens and ~$2.31. Keep the displayed per-second figure
   (~$0.4730/s) labeled as a 16:9 approximation. Kie.ai's live catalog provides
   its separate per-second USD and credit rates.
7. **New open-weight releases (Wan 3.0) have no commercial SKU for weeks.**
   Search first, check hosters (OpenRouter/Replicate/fal) directly, and fall
   back to the previous commercial generation (Wan 2.7, $0.10/s) as the
   reference point — labeled as reference, not as the model's own price.