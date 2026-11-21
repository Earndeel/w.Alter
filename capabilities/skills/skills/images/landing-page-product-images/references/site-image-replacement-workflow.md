# Existing Landing Page Image Replacement Workflow

Use when a client has adapted a landing page from another product and asks for replacement images that preserve the page's current layout/style while matching a new product.

## Workflow learned

1. **Scrape the page HTML and full-page screenshot**
   - Extract all `<img>` sources, dimensions, classes, alt text, and nearby section text.
   - Take a full-page screenshot and run visual analysis to understand the page's actual art direction, not just filenames.
   - Build a manifest: `file`, `dimensions`, `class`, `alt`, `section context`.

2. **Identify replacement targets vs. non-photo assets**
   - Replace product/lifestyle/review images with same filenames and same pixel dimensions.
   - Usually leave utility/brand assets alone unless explicitly requested: logos, flags, stars, payment icons, decorative bubbles/effects, small pictograms.
   - Note residual copy/branding issues separately (e.g. old product name in footer, wrong alt text, mismatch between promo badge and CTA discount).

3. **Retrieve authoritative product references**
   - Pull original product photos from Drive or supplier source.
   - Use one strong reference per variant (e.g. black model + white model) and keep them as image-to-image inputs.
   - Describe the exact product details in prompts: strap holes, front module shape, chrome trim, LED, button, markings.

4. **Host references publicly for Kie.ai**
   - Kie GPT Image 2 I2I needs public HTTP(S) URLs.
   - A reliable pattern is to deploy a tiny Cloudflare Pages project containing only the reference images and an index page.
   - Verify with `curl -I https://.../ref.png` before submitting generation tasks.

5. **Generate with filename/dimension discipline**
   - Use `gpt-image-2-image-to-image` when the asset must preserve the exact product; use `gpt-image-2-text-to-image` when the asset is a pure background/problem/context image that should NOT show the product.
   - Create one prompt per existing asset, preserving the page role and the surrounding text:
     - hero backgrounds / footer backgrounds → separate landscape/background image, no product, clean empty zones for text and product overlays;
     - hero/product PNG cutouts → isolated premium product, transparent/detoured result if possible or chroma/white background for post-processing;
     - problem sections → lifestyle/context illustrating the pain/problem only; explicitly say `Do NOT show the product` unless the existing section is a solution/product section;
     - illustrative/diagram assets → product as a clean composite/diagram with visual elements, not a normal photo;
     - review images → authentic phone-photo/customer style with the product when review copy talks about using/wearing it;
     - feature closeups → macro/detail of the actual product only when the section text is about the product feature.
   - Determine Kie `aspect_ratio` from the target asset and layout role (`16:9` for wide landscape/banners, `4:3` for cards, `3:4` for vertical product sections, `1:1` for square/near-square grids); still resize/crop every result to the exact original pixel dimensions.
   - Keep extensions compatible with the site: PNG RGBA for product cutouts/illustrations, JPEG for lifestyle/review/background photos.

6. **Batch generation pattern**
   - Submit tasks with Kie `/api/v1/jobs/createTask`, then poll `/api/v1/jobs/recordInfo?taskId=...`.
   - Download successful result URLs immediately; `tempfile.aiquickdraw.com` links expire quickly.
   - If a single task stalls, do not block the whole delivery forever: kill/skip it after a reasonable wait, resubmit only that asset with a shorter clearer prompt.

7. **Quality control before upload**
   - Create contact sheets grouped by asset type: product PNGs, lifestyle main, review/grid images.
   - Run visual QA on the sheets: reject outputs that became the old product, shoes/insoles, watches/fitness trackers, have text/logos, or lose variant identity.
   - Verify file count, dimensions, alpha/no-alpha expectations, and compressed sizes.

8. **Deliver to Drive**
   - Create a new subfolder under the product's Drive folder.
   - Upload all final images, a ZIP, an asset manifest, and a concise analysis/mapping Markdown file.
   - The Markdown should include: what was analyzed, asset mapping table, files intentionally not replaced, and non-image site issues to fix.

## Prompt guardrails

Include strong negative constraints for reused landing pages:

- "Do not turn it into insoles, shoes, a watch, a fitness tracker, or a generic bracelet."
- "No text, no captions, no logos, no watermark."
- "Use the input image only as product identity reference; preserve exact product details."

For review/customer images, explicitly request `authentic customer snapshot style` but still `clean, realistic` to avoid overly polished product renders.

## Deliverable checklist

- [ ] All replacement images exist with original filenames.
- [ ] Dimensions match original manifest exactly.
- [ ] PNG product assets preserve transparency or are usable as cutouts.
- [ ] JPEG lifestyle/review assets are compressed for web.
- [ ] Contact sheets reviewed.
- [ ] ZIP created.
- [ ] Drive folder uploaded and verified by listing contents.
- [ ] Analysis/mapping doc included.
