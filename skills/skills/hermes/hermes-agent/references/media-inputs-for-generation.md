# Media inputs for generation workflows

Use this when the user asks how to send images/video/audio to Hermes so they can be used as inputs to Kie.ai, Fal.ai, or similar generation APIs.

## Inbound channels

### Telegram / messaging gateway

Users can send media as native attachments. The Telegram adapter downloads and caches:

- photos and image documents -> `~/.hermes/cache/images/` via `cache_image_from_bytes`
- videos (`.mp4`, `.mov`, `.webm`, `.mkv`, `.avi`) -> `~/.hermes/cache/videos/`
- voice/audio -> `~/.hermes/cache/audio/`
- supported documents -> `~/.hermes/cache/documents/`

The agent sees local cache paths in the prepared message, e.g. `[User sent an image: /root/.hermes/cache/images/img_...jpg]`, or native inline images when the current model supports vision.

For best fidelity, tell the user to send images as **documents** rather than compressed photos when exact pixels matter.

### Hermes API server

The OpenAI-compatible API server accepts text + image parts for Chat Completions/Responses:

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "Use this as the product reference"},
    {"type": "image_url", "image_url": {"url": "https://example.com/product.png"}}
  ]
}
```

It accepts `http(s)` image URLs and `data:image/...` data URLs. It rejects `file` / `input_file` parts and non-image `data:` payloads. For video/audio/document inputs through the API server, prefer an externally accessible URL in the text or a pre-upload flow; do not expect file parts to work.

## Handoff to external generation APIs

Kie.ai and Fal.ai generally need **publicly reachable URLs**, not Hermes local cache paths. If the user sends media via Telegram, first upload/cache it somewhere external before calling the generation provider:

- Fal: use `upload_file` via fal MCP/client or provider storage where available.
- Kie.ai: use its file upload API or a stable object store/CDN.
- Cloudflare R2/public Worker proxy is a good generic option for Scena-style flows.

Do not pass `/root/.hermes/cache/...` local paths directly to Kie/Fal request bodies unless the provider tool explicitly uploads them first.

## Provider field mapping reminders

Kie.ai video:

```json
{
  "input": {
    "first_frame_url": "https://...",
    "last_frame_url": "https://...",
    "reference_image_urls": ["https://..."],
    "reference_video_urls": ["https://..."],
    "reference_audio_urls": ["https://..."]
  }
}
```

Kie GPT Image 2 image-to-image:

```json
{"input": {"prompt": "...", "input_urls": ["https://..."], "aspect_ratio": "auto"}}
```

Fal.ai:

- `fal-ai/nano-banana-2/edit`: `image_urls` array
- `fal-ai/flux/dev/image-to-image`: `image_url` singular string

## Recommended user-facing guidance

Ask for a caption that states role + target, e.g.:

```text
Use this media as input.
Goal: image-to-video
Provider/model: Kie Seedance 2 Fast
Format: 9:16
Duration: 5s
Style: premium ad, slow push-in, keep product identical
```

If multiple assets are sent, label them: `image 1 = product`, `image 2 = logo`, `video = motion reference`, etc.
