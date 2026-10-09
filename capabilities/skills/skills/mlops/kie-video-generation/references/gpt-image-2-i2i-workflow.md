# GPT Image 2 Image-to-Image via Kie.ai — Product Creative Workflow

## When to use
Generating product marketing/landing page images that must match the **exact** product from AliExpress/supplier photos. Raw text-to-image produces generic/fake products; I2I preserves the real product identity while transforming the background, lighting, and context.

## Workflow

### 1. Download product reference images
```bash
# AliExpress images are usually .avif — convert to PNG
python3 -c "from PIL import Image; img = Image.open('ref.avif'); img.save('ref.png', 'PNG')"
```

### 2. Host reference images at public URLs
Kie.ai requires publicly accessible URLs. Options:
- Deploy to a Cloudflare Pages project first (images served from `*.pages.dev`)
- Use any CDN or public file host
- **Must be PNG or JPG** — `.avif`, `.webp`, `.gif` all get `"File type not supported"` error (code 500)

### 3. Submit I2I tasks
```json
{
  "model": "gpt-image-2-image-to-image",
  "input": {
    "prompt": "Professional e-commerce product photo of this exact mosquito repellent bracelet isolated on pure white background, studio lighting. Maintain identical product colors, shape and design details.",
    "input_urls": ["https://your-cdn.com/ref_hero_black.png"],
    "aspect_ratio": "1:1",
    "resolution": "2K"
  }
}
```

### 4. Poll for results
```bash
curl "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=$TASK_ID" \
  -H "Authorization: Bearer $KIE_KEY"
```
When done: `data.state="success"`, then parse `data.resultJson` as JSON to get `resultUrls[0]`.

### 5. Download immediately
- Result URLs are on `tempfile.aiquickdraw.com` — **they expire quickly** (presigned, ~20 min)
- Download to local disk immediately after success

## Prompt Strategy for Product I2I
- Always start with "this exact [product]" to reinforce product identity
- Add "maintain identical product colors, shape and design details"
- For backgrounds: describe the scene, NOT the product (the product comes from the reference)
- For e-commerce: "isolated on pure white background, studio lighting, clean minimal shadows"
- For lifestyle: "[scene description], premium product photography style"
- For features: "close-up detail shot showing [feature], macro photography"

## ⚠️ Pitfalls

1. **`.avif` not supported** — Kie returns `"File type not supported"` (code 500). Always convert to PNG or JPG first.
2. **Input image must be accessible** — Kie's server downloads the image; localhost or private URLs fail silently.
3. **Result URLs are temporary** — `tempfile.aiquickdraw.com` URLs expire within ~20 minutes. Download immediately.
4. **Image quality matters** — Higher resolution reference images produce better I2I results. Use the largest variant available (960x960+).
5. **T2I produces wrong products** — GPT Image 2 text-to-image hallucinates product designs. For actual products, always use I2I with real reference images.

## Pricing
- ~0.5-1.0 credits per I2I generation (varies by resolution)
- 1M token context for understanding the reference image
