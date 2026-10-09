---
name: fal-mcp-integration
category: mcp
description: Complete fal.ai MCP integration via mcporter — 18 tools for image, video, audio generation across 600+ models. Covers catalog discovery, generation pipelines, model schemas, and Telegram delivery.
tags: [fal.ai, image-generation, video-generation, audio-generation, mcp, mcporter, media]
trigger: User wants to generate images, videos, audio, or music via fal.ai MCP; check fal.ai model catalog; use mcporter with fal server.
---

# fal.ai MCP Integration via mcporter

Installation and configuration of `fal-mcp-server` (v1.18.0) via `mcporter` for 18 tools spanning image, video, and audio generation across 600+ fal.ai models.

## Setup

### Installation
```bash
pip3 install --break-system-packages --ignore-installed pyjwt fal-mcp-server
```
Binaires: `/usr/local/bin/fal-mcp`, `fal-mcp-dual`, `fal-mcp-http`

### mcporter Config (`/root/.mcporter/mcporter.json`)
```json
{
  "mcpServers": {
    "fal": {
      "command": "fal-mcp",
      "args": [],
      "env": {
        "FAL_KEY": "uid:key"
      }
    }
  }
}
```
- **CRITICAL**: `FAL_KEY` format: `uid:key` (ex: `«secret:vault»`)
- Sans `FAL_KEY` exportee, `fal-mcp --help` retourne vide
- Validation: `mcporter list` doit afficher `fal (18 tools, ~0.7s)`

## Outils Disponibles (18)

### Decouverte
- **list_models** — 600+ modeles. Params: `category` (image/video/audio), `task`, `search` (nom/desc), `limit` (1-100)
- **recommend_model** — Reco IA. Params: `task` (requis), `category`, `limit`
- **get_pricing** — Prix par modele. Params: `models` (array IDs, 1-50). Peut retourner 404.
- **get_usage** — Historique depenses. Params: `start`, `end` (YYYY-MM-DD)

### Image (7 outils)
- **generate_image** — Text-to-image. Params: `prompt` (requis), `model`, `image_size` (square/landscape_4_3/landscape_16_9/portrait_3_4/portrait_9_16), `num_images` (1-4), `seed`, `negative_prompt`, `output_format`
- **generate_image_structured** — Prompt structure (scene, subjects, lighting, camera, etc.)
- **generate_image_variations** — Variations d'images. Params: `image_url`, `num_variations`
- **edit_image** — Edition text-guided. Params: `image_url`, `prompt`, `model`
- **resize_image** — Resize + smart outpainting. Params: `image_url`, `target_format`, `mode` (extend/crop/letterbox)
- **compose_images** — Overlay (watermark/logo). Params: `base_image_url`, `overlay_image_url`, `position`, `scale`, `opacity`
- **upscale_image** — Upscaling. Params: `image_url`

### Video (3 outils)
- **generate_video** — Text/ Image-to-video generique. Params: `prompt` (requis), `image_url` (optionnel), `model` (defaut: fal-ai/wan-i2v), `duration` (5s), `aspect_ratio` (16:9), `cfg_scale` (0.0-1.0, defaut 0.5), `negative_prompt`
- **generate_video_from_image** — Image-to-video dedie. Params: `image_url` (requis), `prompt` (requis), `model`
- **generate_video_from_video** — Video-to-video (Lucy restyle + Kling motion). Params: `video_url` (requis), `prompt`, `model`, + Kling specs (`character_orientation`, `keep_original_sound`, `generate_audio`), + Lucy specs (`strength`, `num_frames`)

## Kling Video — Model ID Patterns (CRITICAL)

**Kling V2.5 Turbo** — dashes, NOT slashes:
- `fal-ai/kling-video/v2.5-turbo/standard/image-to-video`
- `fal-ai/kling-video/v2.5-turbo/pro/image-to-video`
- `fal-ai/kling-video/v2.5-turbo/pro/text-to-video`
- `fal-ai/kling-video/v2.5-turbo/standard/text-to-video`

**Kling V3** — slashes:
- `fal-ai/kling-video/v3/pro/text-to-video`
- `fal-ai/kling-video/v3/pro/image-to-video`
- `fal-ai/kling-video/v3/standard/image-to-video`

⚠️ **Pitfall**: `fal-ai/kling-video/v2.5/turbo/...` (with slashes) returns **404**. The V2.5 Turbo slug uses **dashes** (`v2.5-turbo`), while V3 uses **slashes** (`v3/pro`). Mixing them up silently fails.

### Kling 2.5 Turbo

| Endpoint | Pricing |
|----------|---------|
| `fal-ai/kling-video/v2.5-turbo/standard/image-to-video` | $0.042/s video |
| `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` | $0.07/s video |
| `fal-ai/kling-video/v2.5-turbo/pro/text-to-video` | $0.07/s video |
| `fal-ai/kling-video/v2.5-turbo/standard/text-to-video` | $0.0002/compute-sec |

**⚠️ URL vs ID naming:** The model page URL uses dashes (`v2.5-turbo`) but the MCP model ID also uses dashes. Do NOT confuse with `v2.5/turbo` (slashes) — that returns 404.

### Kling Video V3 - Schema Input Complet

**Endpoints** : `fal-ai/kling-video/v3/pro/text-to-video` | `fal-ai/kling-video/v3/pro/image-to-video` | `fal-ai/kling-video/v3/standard/image-to-video`

### Parametres Communs

| Paramètre | Type | Défaut | Options |
|---|---|---|---|
| `prompt` | string | - | maxLength 2500 |
| `negative_prompt` | string | `"blur, distort, and low quality"` | maxLength 2500 |
| `cfg_scale` | number | `0.5` | 0.0 - 1.0 |
| `generate_audio` | boolean | `True` | Audio natif (CH/EN) |
| `duration` | string | `"5"` | `"3"` a `"15"` (secondes) |
| `shot_type` | string | `"customize"` | `"customize"` \| `"intelligent"` |
| `multi_prompt` | array | null | Multi-shot : `[{"prompt": "...", "duration": "5"}, ...]` |

### Text-to-Video (Pro uniquement)

| Paramètre | Type | Défaut | Options |
|---|---|---|---|
| `aspect_ratio` | string | `"16:9"` | `"16:9"` \| `"9:16"` \| `"1:1"` |

### Image-to-Video (Pro + Standard)

| Paramètre | Type | Défaut | Notes |
|---|---|---|---|
| `start_image_url` | string | **REQUIRED** | jpg/png/webp/gif/avif, max 10MB, ratio 0.40-2.50 |
| `end_image_url` | string\|null | null | Frame de fin optionnelle |
| `elements` | array\|null | null | Personnages avec reference (voir ci-dessous) |

### Elements (personnages/objets persistants)

```json
{
  "frontal_image_url": "url",
  "reference_image_urls": ["url1", "url2"],
  "video_url": "url",
  "voice_id": "voice_id"
}
```
Reference dans le prompt via `@Element1`.

### Pricing (verified via MCP `get_pricing`, May 2026)
- **V3 Pro & Standard** : **$0.14/s** of output video (audio off). Audio adds ~50%.
- **V2.1 Pro** : $0.098/s — **V2.1 Standard** : $0.056/s
- **V2.5 Turbo** : $0.0002/**compute-second** (different unit — see pitfall #11). Model page 404, may be deprecated.
- Coût calcul : `durée_video_s × prix_par_seconde`. Ex: 5s V3 Pro = $0.70.

### Audio/Musique (1 outil)
- **generate_music** — Text-to-music. Params: `prompt` (requis), `model` (defaut: fal-ai/lyria2), `duration_seconds` (5-300), `lyrics_prompt`, `negative_prompt`

### Utility
- **upload_file** — Upload local vers fal.ai storage. Params: `file_path` (absolu)

## Model IDs Importants (recents)

### Image
`fal-ai/nano-banana-2` — `fal-ai/nano-banana-pro` — `fal-ai/flux-2-pro` — `fal-ai/flux-pro/v1.1-ultra` — `xai/grok-imagine-image` — `fal-ai/z-image/turbo` — `fal-ai/ideogram/v3`

### Video
`bytedance/seedance-2.0/text-to-video` — `bytedance/seedance-2.0/fast/text-to-video` — `bytedance/seedance-2.0/image-to-video` — `fal-ai/kling-video/v3/pro/text-to-video` — `fal-ai/kling-video/v3/pro/image-to-video` — `fal-ai/kling-video/v3/standard/image-to-video` — `fal-ai/kling-video/v2.5-turbo/standard/image-to-video` — `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` — `fal-ai/veo3.1/fast` — `fal-ai/sora-2/text-to-video` — `xai/grok-imagine-video/image-to-video` — `fal-ai/pixverse/v6/image-to-video`

### Audio
`fal-ai/lyria2` — `inworld-tts`

## Pièges

1. **`z-image/turbo` n'existe PAS** — c'est `fal-ai/z-image/turbo`
2. **cfg_scale video = 0.0-1.0** — normalise, pas 7-12
3. **Seedance 2.0** n'a pas de prefix `fal-ai/`: `bytedance/seedance-2.0/text-to-video`
4. **Seedance 2.0 Early Access** — le modele est liste par `list_models` mais rejeté à l'appel: `User "Kwixotic" cannot access application 'fal-ai/seedance-2'`. Requires early access/waitlist grant. v1.5 fonctionne normalement.
5. **get_pricing retourne 404 parfois** via mcporter — verifier sur dashboard
6. **Direct REST API model listing** (rest.fal.ai, api.fal.ai) = 404 — tout passe par MCP ou browser
7. **fal-client direct** (python) vs MCP — les IDs sont identiques, mais `fal_client.submit()` retourne la vraie erreur API. Si le MCP echoue, tester avec `fal_client` pour debugger.
8. **Sandbox `terminal()` herite pas de FAL_KEY** — la variable d'environnement n'est pas passee aux sous-processus Python dans le sandbox. Contournement : mettre `FAL_KEY` dans `/root/.hermes/.env` et charger avec `from dotenv import load_dotenv; load_dotenv('/root/.hermes/.env')`, ou utiliser `execute_code` qui ne peut pas l'exporter non plus. **Ne JAMAIS utiliser le sandbox pour les appels `fal_client`** — toujours `terminal()` direct.
9. **Timeout `terminal()` sur appels fal_client** — les appels `fal_client.submit()` avec `handle.get()` peuvent prendre 30-120s selon le modele. Avec `timeout=60` ca coupe les videos longues. Utiliser `background=true` + `process(action="wait")` pour les generations video.
10. **Extraction de schemas OpenAPI** — fal.ai expose un OpenAPI JSON brut accessible via `curl -s 'https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<model_id>'`. C'est la methode la plus fiable pour decouvrir les parametres exacts d'un modele quand le MCP MCP ne les expose pas tous. Le retour est un JSON OpenAPI 3.0.4 avec `components.schemas` contenant `<ModelName>Input`.
11. **fal.ai pricing unit ambiguity** — `get_pricing` returns TWO different units depending on model vintage: newer models (V3, V2.1) use **"per seconds" of output video** (e.g. $0.14/s = $0.70 for a 5s video). Older models (V2.5 Turbo) use **"per compute-second"** (processing time), which is a completely different metric — a 5s video might take 50-200 compute-seconds. Always check the unit string. If it says "compute seconds" instead of "seconds", the model is likely deprecated.
12. **Kling version lifecycle** — V2.5 Turbo pages return 404 on fal.ai (May 2026). V2.1, V3 Pro, V3 Standard are active. When comparing pricing across providers, ensure you're comparing the same version — providers may carry different Kling versions.

## Pipeline Generation + Telegram

```bash
URL=$(mcporter call fal.generate_image prompt="cyberpunk Paris" | grep -oP 'https?://[^\s"]+')
curl -sL "$URL" -o /tmp/gen_output.jpg
BOT_TOKEN="..."
CHAT_ID="1146774717"
curl -s -F photo=@/tmp/gen_output.jpg "https://api.telegram.org/bot${BOT_TOKEN}/sendPhoto?chat_id=${CHAT_ID}"
```
