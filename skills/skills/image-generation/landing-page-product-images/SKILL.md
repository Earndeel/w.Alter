---
name: landing-page-product-images
description: Build product landing pages with faithful product photography using GPT Image 2 image-to-image via Kie.ai.
category: creative
---

# Landing Pages with Product-Faithful AI Images

## When to use
- Building a landing page for a specific e-commerce product (AliExpress, Amazon, etc.)
- Adapting an existing landing page design to a new product
- User wants product images that look like the **real product**, not AI hallucinations

## Workflow

### Existing-site image replacement
When the user asks to adapt/replace images on an already-built landing page while preserving the page style, follow the detailed workflow in `references/site-image-replacement-workflow.md`: scrape the page image manifest + screenshot, generate same-filename/same-dimension replacements via Kie GPT Image 2 I2I/T2I as appropriate, create contact sheets for QA, and deliver a Drive folder with images + ZIP + mapping doc.

If the user asks to copy/deploy the site with the new images included, follow `references/static-site-copy-with-replacement.md`: clone HTML/CSS/JS/assets, replace exact filenames (including CSS backgrounds), verify the deployed preview visually, and upload a ZIP of the copied static site.

### 1. Scrape both sites
```python
# Scrape the reference site (design/structure)
mcp_scrapling_fetch(url="https://reference-site.com", extraction_type="markdown")

# Scrape the product page (analyze what you are selling)
mcp_scrapling_fetch(url="https://product-page.com", extraction_type="markdown")
```

### 2. Download product images as PNG references
AliExpress product images often come in `.avif` format. Convert to PNG for Kie.ai compatibility:
```python
from PIL import Image
img = Image.open("/tmp/ali_refs/product.avif")
img.save("/tmp/product_ref.png", "PNG")
```

Then host references publicly (they must be accessible to Kie.ai):
- Upload to a temporary public path via Cloudflare Pages deploy
- Or use any public URL service

### 3. Generate I2I images via Kie.ai GPT Image 2

**CRITICAL: Use `gpt-image-2-image-to-image` via Kie.ai, NOT text-to-image.**

Text-to-image generates different products (wrong shape, colors, nonexistent variants). Image-to-image preserves the actual product identity while transforming the background and style.

```python
payload = {
    "model": "gpt-image-2-image-to-image",
    "input": {
        "prompt": "Professional e-commerce product photo of this exact [product] isolated on pure white background, studio lighting, premium product photography",
        "input_urls": ["https://public-url.com/product_reference.png"],
        "aspect_ratio": "1:1",
        "resolution": "1K"
    }
}
```

**Image size guidance:**
- `resolution: "1K"` produces approximately 70-200KB per image, fine for web landing pages
- `resolution: "2K"` produces 1-5MB per image, **far too large for web pages** (causes loading failures)
- Always compress: resize to 1024px max, save as JPEG quality 85

**Prompt engineering for I2I:**
- Reference the actual product: "this exact mosquito repellent bracelet"
- Specify the transformation: "isolated on white background", "warm lifestyle photo"
- Preserve constraints: "maintain identical product colors, shape and design"
- Remove unwanted elements: "remove text overlays, watermarks, background clutter"

### 4. Poll Kie.ai results
Use `GET /api/v1/jobs/recordInfo?taskId=...` -- not `getTaskDetail` for Market models.

### 5. Deploy
- Place images in `images/` directory
- Reference them as `images/name.jpg` in HTML
- Total site should stay under 10MB to avoid slow loading
- Use `wrangler pages deploy` with wrangler

## Critical Pitfalls

### write_file corrupts large HTML files
**NEVER use `write_file` for large HTML files over 10KB.** It injects line number prefixes into the document body (e.g., `1|     1|     1|<!DOCTYPE html>`), breaking the entire page. The page renders as plain black text on white with no CSS applied.

**Correct approach for large HTML:**
- Write a Python generator script with `write_file`, then run it with `execute_code`
- Or use `terminal` with a bash heredoc

### Image-to-Image vs Text-to-Image
- **Text-to-image (t2i):** Generates different products with wrong shapes, colors, dimensions. Creates imaginary variants that do not exist.
- **Image-to-image (i2i):** Preserves the exact product while changing background, style, and composition. Always use the actual product photo as `input_url`.

### Kie.ai does not support .avif format
AliExpress product images are typically `.avif`. Convert to `.png` before using as I2I input, otherwise you get `code: 500, msg: "File type not supported"`.

### Do not use 2K resolution for web deployment
2K images from GPT Image 2 are 1-5MB each. A landing page with 15 images at 2K equals 75MB total, which fails to load in browsers. Use 1K and compress post-download.

### Cloudflare Pages deploy "Uploaded 0 files"
Wrangler skips files whose hash has not changed. After modifying HTML, `touch` the file before deploy, or delete the `.wrangler` directory to force a full upload.

### When building a v2 variant
When creating a v2/v3 landing page variant, ALWAYS diff the v1 image directory against v2's to catch missing assets. The user will notice if any product image from v1 is absent in v2. Run: `diff <(ls v1/images) <(ls v2/images)` before deploying. Copy any missing images from v1 to v2.


## Auth
- Kie.ai key from vault: `kie/api_key`
- Base URL: `https://api.kie.ai/api/v1/jobs/createTask`
- Poll URL: `https://api.kie.ai/api/v1/jobs/recordInfo?taskId=...`

## Related Skills
- `cloudflare-pages-deploy` -- deploy the final landing page
- `atlas-cloud-image-gen` -- alternative for text-to-image (use only when I2I is not needed)
