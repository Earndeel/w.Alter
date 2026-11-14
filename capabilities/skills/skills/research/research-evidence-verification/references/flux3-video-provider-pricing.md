# FLUX 3 video — provider price & access evidence (snapshot 2026-08-21)

Baseline: 5 s clip, 16:9, no video input. All prices USD, read live on 2026-08-21.

## Verdict
- Absolute cheapest FLUX 3 access: **BFL direct Draft mode, $0.06/s 720p** (text/image→video) → $0.30 per 5 s. Draft is exclusive to BFL's own API; no reseller exposes it.
- Cheapest usable without a new account: none — the Nous free-promo route ended; OpenRouter only replicates BFL's standard rate.

## Evidence matrix

| Route | Rate | 5 s total | Status | Source |
|---|---|---|---|---|
| Nous gateway (`bfl_flux3_*`) | free promo | — | REJECTED — promo period ended | gateway refusal message, 2026-08-21 |
| BFL direct — Draft 720p | $0.06/s | $0.30 | Live quote | bfl.ai/pricing (JSON-LD + Sanity `videoRates`) |
| BFL direct — Standard 720p | $0.17/s | $0.85 | Live quote | same |
| BFL direct — Standard 1080p | $0.29/s | $1.45 | Live quote | same |
| BFL direct — v2v 720p draft / std | $0.12 / $0.41 per s | — | Live quote | same |
| OpenRouter `black-forest-labs/flux-3-video` | $0.17/s 720p · $0.29/s 1080p · continuation $0.41/$0.53 per s | $0.85 | Live quote | `/api/v1/videos/models` `pricing_skus` |
| Kie.ai | no FLUX rows | — | Rejected — all 245 video models checked, zero FLUX/BFL | `api.kie.ai/client/v1/model-pricing/page` |
| fal.ai | no flux-3-video (only FLUX.2 family + trainers) | — | Rejected — model search | fal.ai/models?q=flux+3+video |
| Replicate | images only (`flux-3`, plus `flux-video-upscale`); no flux-3-video | — | Rejected | replicate.com/black-forest-labs |

## Extraction notes
- BFL pricing page embeds machine-readable rates: `application/ld+json` Product offers AND Sanity CMS blobs with `videoRates` objects `{effort, t2v720, v2v720, t2v1080, v2v1080}` in cents/second. Static curl + regex beats rendering here.
- OpenRouter Video API: `POST /api/v1/videos` (async job → poll `GET /api/v1/videos/{id}`); params: duration 5–20, resolution 720p/1080p, aspect_ratio, `frame_images` (first_frame/last_frame), `input_references`, `generate_audio`, `callback_url`. Full per-model contract at `openrouter.ai/black-forest-labs/flux-3-video/llms.txt`.
- The generic `/api/v1/models` list contains NO video models — searching it for "flux" returns zero hits while `/api/v1/videos/models` lists 24. Always search the modality-specific catalog.
- OpenRouter credit balance at snapshot: $6.88 remaining (280 credited − 273.12 used) ≈ 40 s of FLUX 3 720p standard.

## Cheaper non-FLUX alternatives seen same day
Veo 3.1 Lite (Kie $0.03–0.05/s; OpenRouter $0.05/s no-audio 720p) · Kling v3 std (OpenRouter $0.084/s) · Pixverse v6 extend 720p (Kie $0.036/s).