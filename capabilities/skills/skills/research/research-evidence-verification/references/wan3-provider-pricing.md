# Wan 3.0 provider pricing — evidence snapshot 2026-08-24

Question: cheapest API for Alibaba Wan 3.0 among kie.ai, OpenRouter, fal.ai.

## Verdict matrix

| Provider | Listing status | Evidence level | Price |
|---|---|---|---|
| fal.ai | Listed & billed | Live quote (model-page HTML fetched directly) | $0.05/s 480p · $0.10/s 720p · $0.20/s 1080p; vendor worked example: 5s @ 720p = $0.50 |
| kie.ai | Announced, price unpublished | Indicative lead only | Google-indexed i2v market card "starting from $0.28 · 55 Credits/5s" (~$0.056/s equiv.) — not confirmable live |
| openrouter.ai | Not verifiably listed | Provisional rejection | generic `/api/v1/models` (422 rows): zero wan entries; detail URL renders 404 |

Model context: Wan3.0 = Alibaba multimodal video model, up to 30 s native generation, native audio, public beta since ~Aug 2026.

## Extraction recipes that worked

### fal.ai (static HTML fast path)
`curl -sL https://fal.ai/models/alibaba/wan-3.0/text-to-video`, strip `<script>`/`<style>`, grep `\$0\.\d+` with context. Tariff sentence appears verbatim: "For every second of video you generate, you will be charged $0.05 480p, $0.10 720p, or $0.20 1080p." Same tier text on `alibaba/wan-3.0/reference-to-video`. Note: fal's marketing hub `/wan-3` still said "pricing not announced" (dated Aug 12, 2026) — individual model pages are fresher than hub pages; check the model page, not the landing page.

### kie.ai
Product page `/wan-3-0`, `/pricing`, docs.kie.ai, `/market/wan`: zero prices in HTML. Market pages are client-rendered; browser-backed extraction captured XHR endpoints (`/api/v1/playground/pagePlaygroundGroup`) but not the price payload. Correct route: `POST https://api.kie.ai/client/v1/model-pricing/page` (`interfaceType: "Video"|"Image"`) — documented in `kie-video-generation-operations`. Not executed this session, so Kie's actual Wan3.0 tariff remains OPEN.

### openrouter.ai
- Generic `/api/v1/models` carries NO video models (re-confirms the 2026-08-21 finding). The authoritative check is `/api/v1/videos/models` — NOT executed this session; the "not listed" verdict rests on rendered-404 detail page + generic-catalog absence, so keep it provisional until the videos catalog is queried.
- SPA trap: `GET https://openrouter.ai/alibaba/wan-3.0` returns HTTP 200 + Next.js app shell (title "OpenRouter") to curl/scrapling, while a real browser renders "404: Not Found". Never cite the status code as proof of listing.
- Stale-snippet trap: search results quoted "Wan 2.7 … $0.10 per second" from an OpenRouter URL; the live generic catalog contains no wan models at all. Snippets outlive delistings — verify against the live catalog.

## Follow-up
Before any paid decision: query the kie.ai pricing API for wan3.0 rows; if present, compare against the fal 720p band, accounting for Kie top-up bonus (+10%) semantics and resolution mapping (Kie 580P/720P bands vs fal 480p/720p/1080p).
