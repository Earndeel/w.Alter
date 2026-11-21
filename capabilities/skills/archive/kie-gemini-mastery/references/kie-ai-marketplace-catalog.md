# Kie.ai Full Marketplace Catalog (Discovered 2026-06-05, Updated 2026-06-26)

Complete model inventory from `GET https://api.kie.ai/api/v1/playground/model-paths` (authoritative, 176+ models) and `https://kie.ai/changelog` (`__NEXT_DATA__` extraction for navigation labels). Two namespaces: `market/` (English) and `cn/market/` (Chinese). Each model = one HTTP API endpoint under `/api/v1/jobs/createTask` (async) or `/v1/chat/completions` (sync for LLMs).

---

## Scraping Method (Updated 2026-06-26 — API-first)

**Ranking of approaches (best → worst):**

### 1. Internal API — `model-paths` (BEST: authoritative, no auth, all 176+ models)

```bash
curl -s "https://api.kie.ai/api/v1/playground/model-paths" \
  -H "User-Agent: Mozilla/5.0" | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
for p in sorted(data['data']):
    print(p)
"
```

Returns a flat JSON array of ALL model path slugs currently deployed. This is the single source of truth — if it's not here, it doesn't exist on Kie.ai.

**Provider grouping:**
```bash
curl -s "https://api.kie.ai/api/v1/playground/listModelProvider" \
  -H "User-Agent: Mozilla/5.0"
```
Returns provider names only (Google, ByteDance, Anthropic, etc.) — no model details.

### 2. Changelog `__NEXT_DATA__` (fallback: navigation labels only)

The changelog page embeds navigation data with model names and URLs:

```bash
curl -s -L "https://kie.ai/changelog" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  | python3 -c "
import sys, json, re
html = sys.stdin.read()
m = re.search(r'<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>', html)
if m:
    data = json.loads(m.group(1))
    nav = data['props']['pageProps']['navigationData']['navigationList']
    carousel = data['props']['pageProps'].get('listCarouselCommon', [])
    print('=== NAVIGATION (all models) ===')
    for item in nav:
        if item.get('children'):
            for child in item['children']:
                if child.get('children'):
                    for sub in child['children']:
                        print(f\"  {sub['title']}\")
                else:
                    print(f\"  {child['title']}\")
    print()
    print('=== CAROUSEL (recently featured) ===')
    for c in carousel:
        print(f\"  {c['title']}\")
"
```

**Caveat:** The `/market` page itself has minimal `__NEXT_DATA__` (no model data — just i18n strings). Only `/changelog` has the full navigation tree.

### 3. POST API — `pagePlaygroundGroup` (needs auth, returns 500 without token)

```bash
curl -s -X POST "https://api.kie.ai/api/v1/playground/pagePlaygroundGroup" \
  -H "Content-Type: application/json" \
  -d '{"pageNum":1,"groupName":"","tasks":"","provider":"","pageSize":100}'
```

Returns structured model records with pricing. **Requires auth token** — returns 401/500 without it.

**Alternative (docs.kie.ai):** `curl -s "https://docs.kie.ai"` returns API documentation with model paths. Use this for endpoint paths and credits, not for the full marketing catalog.

---

## Complete model-paths Snapshot (2026-06-26)

Captured via `GET /api/v1/playground/model-paths`. Diff against this to find new models.

<details>
<summary>Full 176 model paths</summary>

```
bytedance/seedance-2-mini
happyhorse-1-1/reference-to-video
happyhorse-1-1/text-to-video
happyhorse-1-1/image-to-video
kling/v3-turbo-image-to-video
kling/v3-turbo-text-to-video
omnihuman-1-5/subject-detection
omnihuman-1-5/human-identification
omnihuman-1-5
volcengine/video-to-video-lip-sync
claude-fable-5
grok-imagine-video-1-5-preview-extend
grok-imagine-video-1-5-preview
gemini-3-5-flash-openai
claude-opus-4-8
gemini-3-5-flash
gemini-omni-audio
gemini-omni-character
gemini-omni-video
happyhorse/video-edit
happyhorse/reference-to-video
happyhorse/image-to-video
happyhorse/text-to-video
gpt-5-5
gpt-image-2-text-to-image
gpt-image-2-image-to-image
claude-opus-4-7
wan/2-7-image-to-video
wan/2-7-text-to-video
wan/2-7-videoedit
wan/2-7-r2v
bytedance/seedance-2-asset
bytedance/seedance-2-fast
bytedance/seedance-2
wan/2-7-image-pro
wan/2-7-image
grok-imagine/extend
qwen2/text-to-image
claude-haiku-4-5
claude-opus-4-5
claude-opus-4-6
claude-sonnet-4-5
claude-sonnet-4-6
gemini-3-flash-v1betamodels
qwen2/image-edit
gpt-5-4
gpt-5.4-codex
kling-3.0/motion-control
gpt-5.1-codex
gpt-5.2-codex
gpt-5.3-codex
gpt-5-codex
nano-banana-2
wan/2-6-flash-video-to-video
wan/2-6-flash-image-to-video
seedream/5-lite-text-to-image
seedream/5-lite-image-to-image
gemini-3.1-pro
bytedance/seedance-2-image-to-video
bytedance/seedance-2-text-to-video
gpt-5-2
kling-3.0/video
sora-2-text-to-video-stable
sora-2-image-to-video-stable
sora-2-characters-pro
midjourney/upscale
midjourney/vary
midjourney/extend
kling/ai-avatar-pro
gemini-3-flash
elevenlabs/text-to-dialogue-v3
kling/ai-avatar-standard
gemini-2.5-flash
gemini-2.5-pro
kling-2.6/motion-control
grok-imagine/image-to-image
bytedance/seedance-1.5-pro
sora-2-characters
wan/2-6-video-to-video
wan/2-6-image-to-video
wan/2-6-text-to-video
gpt-image/1.5-image-to-image
gpt-image/1.5-text-to-image
seedream/4.5-edit
z-image
seedream/4.5-text-to-image
kling-2.6/image-to-video
kling-2.6/text-to-video
kling-o1/kling-hig-image-omni-flf-o1
kling-o1/kling-hig-video-reference-o1
kling-o1/kling-hig-video-edit-o1
kling-o1/kling-hig-image-reference-o1
flux-2/flex-image-to-image
flux-2/pro-image-to-image
flux-2/flex-text-to-image
flux-2/pro-text-to-image
nano-banana-pro
gemini-3-pro
grok-imagine/text-to-image
bytedance/v1-pro-fast-image-to-video
grok-imagine/upscale
grok-imagine/text-to-video
grok-imagine/image-to-video
hailuo/2-3-image-to-video-standard
hailuo/2-3-image-to-video-pro
sora2-remix
sora-2-pro-storyboard
sora-watermark-remover
v3-api
sora-2-pro-text-to-video
sora-2-pro-image-to-video
sora-2-text-to-video
sora-2-image-to-video
topaz/image-upscale
google/gemini-2.0-flash-exp
wan/2-5-text-to-video
wantest/2-5-text-to-video
kling/v2-5-turbo-text-to-video-pro
wan/2-5-image-to-video
kling/v2-5-turbo-image-to-video-pro
wan/2-2-animate-move
wan/2-2-animate-replace
hailuo/02-text-to-video-pro
hailuo/02-image-to-video-pro
hailuo/02-text-to-video-standard
hailuo/02-image-to-video-standard
topaz/video-upscale
kling/v1-tts
kling/v1-avatar-standard
kling/ai-avatar-v1-pro
bytedance/seedream-v4-text-to-image
bytedance/seedream-v4-edit
nano-banana-upscale
infinitalk/from-audio
infinitalk/from-text
recraft/remove-background
recraft/crisp-upscale
elevenlabs/audio-isolation
elevenlabs/sound-effect-v2
elevenlabs/text-to-speech-turbo-2-5
elevenlabs/speech-to-text
elevenlabs/text-to-speech-multilingual-v2
bytedance/seedream
wan/2-2-a14b-speech-to-video-turbo
qwen/image-to-image
qwen/text-to-image
google/nano-banana-edit
google/nano-banana
google/imagen4-fast
ideogram/character-remix
ideogram/character-edit
ideogram/character
features/flux1-kontext
qwen/image-edit
bytedance/omni-human
features/mj-api
openai/whisper-speech-to-text
kie/image-refiner
google/imagen4-ultra
google/imagen4
wan/2-2-a14b-image-to-video-turbo
wan/2-2-a14b-text-to-video-turbo
ideogram/v3-remix
ideogram/v3-reframe
ideogram/v3-edit
ideogram/v3-text-to-image
luma-dream-machine/modify
bytedance/v1-lite-text-to-video
bytedance/v1-lite-image-to-video
bytedance/v1-pro-text-to-video
bytedance/v1-pro-image-to-video
luma-dream-machine/ray-2-flash-reframe
kling/v2-1-standard
kling/v2-1-pro
kling/v2-1-master-image-to-video
kling/v2-1-master-text-to-video
```

</details>

---

## Text / Chat Models (OpenAI-compatible `/v1/chat/completions`)

| Model | Endpoint Path | Credits/Call | Notes |
|-------|---------------|--------------|-------|
| **Gemini 3.5 Flash** | `gemini-3-5-flash-openai` | **0.01** | `-openai` suffix required |
| **Gemini 3.1 Pro** | `gemini-3.1-pro` | **27** | Dots in version (3.1), not hyphens |
| **Gemini 3 Pro** | `gemini-3-pro` | — | **NEW 2026-06-26** |
| **Gemini 3 Flash** | `gemini-3-flash` | — | **NEW 2026-06-26** — now deployed |
| **Gemini 2.5 Pro** | `gemini-2.5-pro` | — | |
| **Gemini 2.5 Flash** | `gemini-2.5-flash` | — | |
| **Claude Opus 4.6** | `claude/claude-opus-4-6` | **0.25** | Via `kie-claude` provider (Anthropic Messages) |
| **Claude Opus 4.7** | `claude/claude-opus-4-7` | ~0.25 | |
| **Claude Opus 4.8** | `claude/claude-opus-4-8` | ~0.25 | |
| **Claude Sonnet 4.5** | `claude/claude-sonnet-4-5` | — | **NEW 2026-06-26** |
| **Claude Sonnet 4.6** | `claude/claude-sonnet-4-6` | **0.25** | |
| **Claude Sonnet 4.5** | `claude/claude-sonnet-4-5` | — | **NEW 2026-06-26** |
| **Claude Haiku 4.5** | `claude/claude-haiku-4-5` | **0.25** | |
| **Claude Fable 5** | `claude-fable-5` | — | **NEW via model-paths** |
| **GPT-5.5** | `chat/gpt-5-5` | **0.48** | Responses API on `/codex/v1/responses` |
| **GPT-5.4** | `chat/gpt-5-4` | **0.48** | **NEW 2026-06-26** |
| **GPT-5.2** | `chat/gpt-5-2` | — | **NEW 2026-06-26** |
| **Codex API** | `codex` | — | Dedicated coding endpoint |

---

## Video Generation (Async `/api/v1/jobs/createTask`)

| Model | Endpoint Path | Type |
|-------|---------------|------|
| **Wan 2.7** | `wan/2-7-text-to-video`, `wan/2-7-image-to-video` | **NEW 2026-06-26** |
| **Wan 2.6 Flash** | `wan/2-6-flash-text-to-video`, `wan/2-6-flash-image-to-video` | |
| **Wan 2.5** | `wan/2-5-*` | |
| **Wan 2.2** | `wan/2-2-a14b-*`, `wan/2-2-animate-*` | |
| **Veo 3 API** | — | Google |
| **Veo 3.1 API** | — | Google **NEW 2026-06-26** |
| **Seedance 2.0** | `bytedance/seedance-2` | **NEW 2026-06-26** |
| **Seedance 2 Fast** | `bytedance/seedance-2-fast` | Text-to-video, Image-to-video |
| **Seedance 1.5 Pro** | `bytedance/seedance-1-5-pro` | |
| **Kling 3.0** | `kling/kling-3-0` | **NEW 2026-06-26** |
| **Kling 2.6** | `kling/v2-6-*` | **NEW 2026-06-26** |
| **Kling 2.5** | `kling/v25-turbo-*` | |
| **Kling 2.1** | `kling/v2-1-*` | |
| **Hailuo 2.3** | `hailuo/2-3-*` | **NEW 2026-06-26** |
| **Grok Imagine** | `grok-imagine/text-to-video`, `grok-imagine/image-to-video` | xAI |
| **Happyhorse** | `happyhorse/text-to-video`, `happyhorse/image-to-video`, `happyhorse/reference-to-video`, `happyhorse/video-edit` | |
| **HappyHorse 1.1** | `happyhorse-1-1/text-to-video`, `happyhorse-1-1/image-to-video`, `happyhorse-1-1/reference-to-video` | **NEW via model-paths** |
| **Kling O1** | `kling-o1/kling-hig-image-omni-flf-o1`, `kling-o1/kling-hig-video-reference-o1`, `kling-o1/kling-hig-video-edit-o1`, `kling-o1/kling-hig-image-reference-o1` | **NEW via model-paths** |
| **Kling V3 Turbo** | `kling/v3-turbo-text-to-video`, `kling/v3-turbo-image-to-video` | **NEW via model-paths** |
| **Kling AI Avatar** | `kling/ai-avatar-pro`, `kling/ai-avatar-standard`, `kling/ai-avatar-v1-pro`, `kling/v1-avatar-standard` | **NEW via model-paths** |
| **OmniHuman 1.5** | `omnihuman-1-5`, `omnihuman-1-5/subject-detection`, `omnihuman-1-5/human-identification` | **NEW via model-paths** |
| **Sora 2** | `sora2/sora-2-text-to-video`, `sora2/sora-2-image-to-video`, `sora2/sora-2-pro-*` | |
| **Sora 2 Pro Storyboard** | `sora-2-pro-storyboard` | **NEW via model-paths** |
| **VolcEngine Lip Sync** | `volcengine/video-to-video-lip-sync` | **NEW via model-paths** |
| **Grok Imagine Video** | `grok-imagine-video-1-5-preview`, `grok-imagine-video-1-5-preview-extend`, `grok-imagine/text-to-video`, `grok-imagine/image-to-video` | **NEW via model-paths** |
| **Luma Dream Machine** | `luma-dream-machine/modify`, `luma-dream-machine/ray-2-flash-reframe` | **NEW via model-paths** |
| **InfiniTalk** | `infinitalk/from-audio`, `infinitalk/from-text` | **NEW via model-paths** |

---

## Image Generation (Async `/api/v1/jobs/createTask`)

| Model | Endpoint Path |
|-------|---------------|
| **GPT Image 2** | `gpt/gpt-image-2-text-to-image`, `gpt/gpt-image-2-image-to-image` |
| **GPT Image 1.5** | `gpt-image/1-5-text-to-image`, `gpt-image/1-5-image-to-image` |
| **Nano Banana 2** | `google/nanobanana2` **NEW 2026-06-26** |
| **Nano Banana Pro** | `google/pro-image-to-image` |
| **Nano Banana / Edit** | `google/nano-banana`, `google/nano-banana-edit` |
| **Seedream 5.0 Lite** | `seedream/5-lite-text-to-image`, `seedream/5-lite-image-to-image` **NEW 2026-06-26** |
| **Seedream 4.5** | `seedream/4-5-text-to-image` |
| **Seedream 4** | `seedream/seedream-v4-text-to-image` |
| **Flux. 2** | `flux2/pro-text-to-image`, `flux2/pro-image-to-image`, `flux2/flex-*` **NEW 2026-06-26** |
| **Flux.1 Kontext** | — |
| **4o Image API** | — |
| **Imagen 4** | `google/imagen4`, `google/imagen4-ultra`, `google/imagen4-fast` |
| **Ideogram V3** | `ideogram/v3-text-to-image`, `ideogram/v3-edit`, `ideogram/v3-remix` |
| **Ideogram Character** | `ideogram/character-*` |
| **Qwen Image Edit** | `qwen2/text-to-image`, `qwen2/image-edit` |
| **Z-Image** | `z-image/z-image` |
| **Recraft** | `recraft/remove-background`, `recraft/crisp-upscale` |

---

## Audio / Other

| Category | Endpoints |
|----------|-----------|
| **ElevenLabs V3** | `elevenlabs/text-to-speech-*`, `elevenlabs/speech-to-text`, `elevenlabs/sound-effect-v2`, `elevenlabs/audio-isolation` **NEW 2026-06-26** |
| **Suno** | `suno-api/generate-sounds`, `suno-api/suno-voice-*` |
| **Gemini Omni** | `gemini-omni-video`, `gemini-omni-audio`, `gemini-omni-character` |
| **Codex** | `codex/gpt-codex` |
| **Common** | `common-api/get-account-credits`, `common-api/download-url`, `common-api/webhook-verification` |
| **File Upload** | `file-upload-api/upload-file-*` |

---

## API Patterns

### Sync (LLMs) - OpenAI Compatible
```
POST https://api.kie.ai/{model-path}/v1/chat/completions
Headers: Authorization: Bearer *** Content-Type: application/json
Body: { "model": "{model-id}", "messages": [...], "stream": true }
```

### Async (Video/Image) - Job Based
```
POST https://api.kie.ai/api/v1/jobs/createTask
Headers: Authorization: Bearer *** Content-Type: application/json
Body: { "model": "{model-path}", "input": {...} }
Response: { "task_id": "..." }
Poll: GET https://api.kie.ai/api/v1/jobs/{task_id}
```

### Google Native (Gemini only)
```
POST https://api.kie.ai/gemini/v1/models/{model_id}:generateContent
Headers: Authorization: Bearer *** Content-Type: application/json
Body: { "contents": [{ "parts": [{ "text": "prompt" }]}] }
```

---

## Real Million Token Pricing Summary (Verified June 2026)

| Model | Input Price ($/Mtok) | Output Price ($/Mtok) | Credits Input/Output |
|-------|----------------------|-----------------------|----------------------|
| **Claude Opus 4.8** | **$2.00** | **$10.00** | 400 / 2000 |
| **Claude Opus 4.7 / 4.6** | **$1.425** | **$7.15** | 285 / 1430 |
| **Gemini 3.5 Flash** | **$0.45** | **$2.70** | 90 / 540 |
| **Gemini 3.1 Pro** | **$0.50** | **$3.50** | 100 / 700 |
| **GPT-5.5** | **$1.40** | **$8.40** | 280 / 1680 |
| **GPT-5.4** | **$0.70** | **$5.60** | 140 / 1120 |
| Video/Image models | Not published | — |

---

## Blog Posts (as of 2026-06-26)

- "Claude Fable 5 Return: Bedrock & Claude Code Signals"
- "GPT-5.6 Preview Leak: What the Internal Route Shows"
