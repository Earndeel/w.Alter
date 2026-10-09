# Branded SPA regression: logo, routes, reveal motion

Use this reference when a branded Vite/React SPA is redesigned into a public landing plus a learning/product surface and deployed to Cloudflare Pages.

## Acceptance contract

- `/` renders the public, outcome-led landing page.
- `/app` renders the product surface on a fresh load, not only after a client-side click.
- Cloudflare Pages serves the SPA entry for `/app` via `public/_redirects`:

```text
/* /index.html 200
```

- The client surface resolver accepts both `/app` and `/app/`, and treats `#app` only as a backwards-compatible alias if one already exists.
- The product can return to `/` with `history.pushState` without a full reload.

## Transparent logo verification

Never trust a filename, a viewer with a white canvas, or a single screenshot. For every raster logo variant:

1. Decode the PNG as RGBA.
2. Inspect corner alpha values and the full alpha histogram.
3. Composite the asset over the real light brand background and a dark background.
4. Look for a rectangular matte, pale halo, clipped strokes, and unwanted white negative-space fills.
5. Fetch at least one logo variant back from the deployed CDN and repeat the corner-alpha check.

For a logo rasterized against white, a practical non-destructive cleanup is to derive opacity from the pixel distance to white and combine it with the existing alpha. Use a threshold for near-white background noise; preserve colored and mid-tone logo pixels. Do not vectorize or redraw a supplied mark unless the user explicitly accepts a change to its drawing.

## Reveal-animation QA

`gsap.fromTo(..., { opacity: 0 }, { opacity: 1, scrollTrigger })` uses inline styles and is not necessarily revealed by a generic QA harness that only adds `.in`/`.visible` classes. A full-page screenshot can therefore show blank below-the-fold sections even when the page is correct.

Use both checks:

- DOM measurement: list each `header`, `section`, and `footer` with top, height, and child count; all expected sections must have non-zero heights.
- Scroll-and-shoot: scroll each key section into the viewport, wait for its trigger, assert computed opacity is near `1`, and capture representative desktop/mobile viewports.

Treat DOM + actual scroll state as stronger evidence than one downsampled full-page image. Keep full-page slices as a second visual opinion.

## Public deployment proof

After `wrangler pages deploy dist --project-name <name>`:

1. Record the immutable deployment URL printed by Wrangler.
2. Probe both the immutable URL and the project’s main `pages.dev` URL with `curl`; require HTTP 200.
3. Probe `/app` directly and require the SPA index response.
4. Parse the served HTML to locate the current JS/CSS bundle paths, then fetch the bundles and assert a distinctive landing marker and route/audio marker.
5. Fetch a logo asset from the immutable URL and verify RGBA corners remain transparent.
6. Run the public Playwright smoke: direct `/app`, return `/`, one landing interaction, one product interaction, no page errors, and `scrollWidth === clientWidth` at desktop and mobile.

Classify blocked external font/CDN requests separately from local asset failures; do not call an artifact fully network-clean if only an external resource was blocked by the QA environment.
