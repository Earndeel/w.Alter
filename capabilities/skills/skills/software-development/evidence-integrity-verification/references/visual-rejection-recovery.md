# Visual rejection recovery reference

## Why this exists

A frontend can pass `npm run lint`, `npm run build`, accessibility selectors, and console checks while still looking wrong. This reference records the evidence pattern used after the Irene Laoshi landing page was rejected as visually unacceptable.

## Failure pattern to recognize

The rejected iteration had three incompatible mascot roles at once:

- a pose-swapped mascot inside the hero lesson card;
- a second scroll-driven `sticky` journey/companion layer;
- a mentor portrait that repeated the same character at another scale.

The attempted fix made the composition worse because it moved the duplicate instead of choosing one visual role. The durable repair was architectural: remove the old mascot JSX, React state, GSAP journey timeline, and all associated CSS/media-query overrides, then introduce one contextual portrait in the mentor section. The right invariant was not merely “no ghosting”; it was “one intentional mascot presentation on the landing page, with zero legacy stage/journey elements.”

## Evidence sequence

1. Freeze deployment and reproduce the current candidate.
2. Capture the initial hero at `1440×900` and `390×844`.
3. Scroll through the page in viewport-sized steps and capture the method, product preview, mentor, FAQ, and final CTA sections. Wait after each scroll so ScrollTrigger/in-view reveals have executed.
4. Inspect the captures as images and write a defect list before editing.
5. After the refactor, run the same captures and compare both visual evidence and structural invariants.
6. Keep the candidate in a local preview until the user explicitly approves the design.

A `fullPage` screenshot taken immediately after navigation is not sufficient for an animated page: reveal elements may be intentionally hidden below the fold. It is useful as a labeled initial-state artifact, not as proof that the full page is visible.

## Reusable Playwright probe

Adapt the URL and screenshot directory; do not rely on a single full-page capture.

```js
import { chromium } from 'playwright'

const browser = await chromium.launch({ headless: true })
const cases = [
  ['desktop', 1440, 900],
  ['mobile', 390, 844],
]

for (const [name, width, height] of cases) {
  const page = await browser.newPage({
    viewport: { width, height },
    reducedMotion: 'no-preference',
  })
  const errors = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(String(error)))
  await page.goto('http://127.0.0.1:5175/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(700)

  const before = await page.evaluate(() => ({
    mascotCount: document.querySelectorAll('main img[src*="/mascot/"]').length,
    heroMascotCount: document.querySelectorAll('.rebuild-hero img[src*="/mascot/"]').length,
    legacyJourneyCount: document.querySelectorAll('.rebuild-irene-journey, .rebuild-mascot-stage').length,
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }))

  await page.screenshot({ path: `/tmp/visual-${name}-hero.png` })
  await page.locator('#mentor').scrollIntoViewIfNeeded()
  await page.waitForTimeout(900)
  await page.screenshot({ path: `/tmp/visual-${name}-mentor.png` })

  const after = await page.evaluate(() => {
    const figure = document.querySelector('.rebuild-mentor-figure')
    const image = document.querySelector('.rebuild-mentor-mascot')
    const rect = figure?.getBoundingClientRect()
    return {
      mentorVisible: Boolean(figure && rect && rect.width > 0 && rect.height > 0),
      figureWidth: rect ? Math.round(rect.width) : 0,
      figureHeight: rect ? Math.round(rect.height) : 0,
      imageLoaded: image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0,
      mascotCount: document.querySelectorAll('main img[src*="/mascot/"]').length,
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      revealOpacity: document.querySelector('.rebuild-mentor')
        ? getComputedStyle(document.querySelector('.rebuild-mentor')).opacity
        : null,
    }
  })

  console.log(JSON.stringify({ name, before, after, errors }))
  await page.close()
}

await browser.close()
```

## Assertions that matter

- `mascotCount === 1` for the landing page after the redesign.
- `heroMascotCount === 0` when the chosen art direction places the character contextually later.
- `legacyJourneyCount === 0`; do not leave old selectors or containers hidden by CSS.
- `scrollWidth === clientWidth` on desktop and mobile.
- The mentor figure has non-zero bounds after scrolling to it and its image reports a loaded natural width.
- No console errors or page errors.
- A second pass that scrolls through the lower sections confirms FAQ and final CTA are visible; do not infer this from an unscrolled full-page capture.

## Asset-ratio guard

Before changing `object-fit`, inspect the actual asset dimensions. In the Irene case the source illustration was `320×480`, a `2:3` ratio. A `3:4` frame with `object-fit: cover` silently cropped the lower body. Matching the frame to `2 / 3` preserved the full figure while retaining the editorial crop shape.

## Mobile-control guard

A text action with an underline/border should normally use intrinsic width. Applying `width: 100%` to a mobile text button made its underline span the entire content width and read as an accidental section divider. Keep full width only for a deliberately full-width primary control; set the text action to `width: max-content` and align it intentionally.

## Model provenance

If the user forces a design model, resolve and call the exact model ID and keep the provider response/artifact identifier in the review notes. For this iteration the forced ID was `meta/muse-spark-1.3-contributor`; no fallback model was acceptable without user permission.
