# Static site copy + contextual image replacement

Use when a user asks to copy an existing landing page and include newly generated replacement images.

## Key lesson
Do not treat “replace images” as “put the product everywhere.” First infer the role of each asset from HTML/CSS placement and surrounding copy:

- Hero is often split: a CSS landscape/background image plus a separate PNG product cutout.
- Problem/pain images should illustrate the problem only and often should NOT show the product.
- Product/solution/review sections can show the actual product.
- Some images are not photos: diagrams, product cutouts, visual explainers, decorative composites.
- CSS `background-image` assets are just as important as `<img>` tags and must be included in the replacement set.

## Static copy workflow
1. Fetch the page HTML with `requests` and save it with Python file I/O (avoid `read_file` → write loops on HTML).
2. Fetch local CSS and JS referenced by the page.
3. Parse HTML `<img>` sources and CSS `url(...)` assets, download all local images.
4. Replace generated assets by exact filename into the copied `images/` directory.
5. If the source site logo is still an image of the old brand, replace that image asset with a simple local SVG wordmark if the user expects a preview, but do not rewrite copy unless asked.
6. Add a local favicon if the original favicon points to the old brand.
7. Add `_headers` with `Cache-Control: no-cache` for preview deployments.
8. Deploy with Cloudflare Pages and verify using the main `*.pages.dev` URL if the hash URL is slow to propagate.

## Targeted one-image swaps after deployment
Use this when the user asks for a small follow-up like “replace just the header product image by herov2”:

1. Identify the exact placement(s) for that visual only. Hero product images often appear in 3 places: mobile `<img>`, desktop `<source srcset>`, and desktop fallback `<img>`.
2. Copy the requested source reference directly if the user asks for the original product file (`herov2`, `white_variant`, etc.); do not regenerate or restyle unless they ask.
3. Prefer a new cache-busting filename (for example `images/herov2-header.png`) plus `?v=<timestamp>` rather than overwriting the old asset, so Cloudflare/browser caches cannot hide the change.
4. Patch HTML with Python file I/O (`Path.read_text`/`write_text`) and exact string replacements. Do **not** use `read_file` → `write_file` on HTML.
5. Keep scope tight: do not change other product images, copy, CSS backgrounds, or downstream sections when the request says “just” one placement.
6. Deploy, then verify both the hash URL and the main Pages URL contain the new filename and no old hero-specific references.
7. Take a screenshot of the deployed hero and visually confirm the correct product/reference is shown before reporting done.

## Verification checklist
- `head -3 index.html` starts with `<!DOCTYPE html>` and has no line-number prefixes.
- Key replacement assets return HTTP 200.
- CSS still references the intended filenames: `header-bg`, `middle`, `foot-pain`, `limited-promo`, etc.
- For targeted swaps, `curl`/`grep` the deployed HTML for the new cache-busted filename and absence of old hero-specific references.
- Take a browser/scrapling screenshot of the deployed page and visually verify hero split: new background, separate product image, no broken layout.
- Zip the copied static site and upload it to the same Drive folder as the assets if the user asks for a copy.

## Prompt/asset role reminders
- For pure backgrounds: prompt `Do NOT show the product` and leave empty zones for overlay text/product.
- For problem sections: no product unless the surrounding copy explicitly talks about using/wearing it.
- For diagrams/explainers: ask for “clean ecommerce illustration/composite, no written labels.”
- For review photos: use authentic customer snapshot style with the exact product from I2I reference.
