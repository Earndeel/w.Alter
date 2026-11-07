# Landing Page Cloning & Adaptation Workflow

## Pattern
Scrape existing landing page → analyze structure → adapt to new product → generate replacement images → deploy.

## Steps
1. **Scrape original** — Use `mcp_scrapling_fetch` with `extraction_type: markdown` for content structure, then `extraction_type: html` for layout details.
2. **Download product references** — `curl -sL` the actual product images from source (AliExpress, supplier site) into `/tmp/` for visual reference.
3. **Map sections** — Identify every section type: nav, hero, problems/pain points, features grid, how-it-works, gallery, reviews, FAQ, CTA, footer.
4. **Generate images** — Use Atlas Cloud GPT Image 2 (`openai/gpt-image-2/text-to-image`, quality: "low") with prompts crafted from real product images + desired style (from original page). Prompt pattern: `"Professional e-commerce product photography of [specific product details from real images], [styling: isolated on pure white background / lifestyle scene with soft light], studio lighting, premium style"`.
5. **Poll + download** — Submit all prompts in parallel, poll every 3s until complete, download to `/tmp/landing/dist/images/`.
6. **Build HTML** — Single-file HTML with inline CSS (mobile-responsive, animations). Use same section mapping as original but with adapted text and new image filenames.
7. **Deploy** — Create CF Pages project via API, deploy with `npx wrangler pages deploy`.

## Image Section Mapping (Akusoli-style page)
| Section | Image Type | Prompt Focus |
|---------|-----------|--------------|
| Hero | `hero_product` | Main product on white background |
| Hero | `hero_lifestyle` | Product worn/used in natural setting |
| Problems | `symptoms_bites` | Illustration of pain point |
| Why/Problems | `problem_no_protection` | Before/without scenario |
| Why/Benefit | `benefit_protection` | After/with scenario |
| Features (4x) | `feature_*` | Close-up product detail shots |
| How-it-works (3x) | Mixed | Step photos (lifestyle + product) |
| Gallery (4x) | `gallery_*` | Usage scenarios |
| Variants | `variant_*` | Color/style variations |
| FAQ | `faq_illustration` | Calming/solution illustration |

## Pitfalls
- **ERNIE vs GPT for product pages**: ERNIE produces generic/unrecognizable product shapes. For e-commerce landing pages where images must match the actual product, always use GPT Image 2.
- **Deploy cache-busting**: Cloudflare Pages caches 4h. Always verify with `curl -s <url> | head` after deploy.
- **All CSS inline**: Cloudflare Pages deploys static files — no build step. Single HTML file with `<style>` tag is most reliable.
- **Responsive first**: Akusoli uses Tailwind-like classes. When recreating, include `@media (max-width)` breakpoints for mobile.
- **Scrapling extraction**: Always use both markdown (for content) and html (for layout) — markdown alone misses CSS class names and media queries.
