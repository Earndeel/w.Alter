# Headless screenshot QA — pitfalls in depth

Two failure modes account for almost every wrong verdict when verifying an HTML artifact via Playwright + vision. This document expands the SKILL.md summary with the diagnostic patterns.

## Pitfall 1: IntersectionObserver-gated content captures blank

### Symptom

A full-page screenshot shows the hero rendered correctly, but sections below the first viewport are mostly black or appear to be "missing content." The DOM is fine; the screenshot is the artifact of how scroll-driven reveals interact with Playwright's full-page capture mode.

### Why it happens

`page.screenshot(full_page=True)` resizes the viewport to the full document height and captures in one pass. It does not actually scroll through the document at human pace, so `IntersectionObserver` callbacks for elements that need visible scroll position to trigger may never fire — or fire too late relative to the capture.

Any CSS pattern like:

```css
.reveal { opacity: 0; transform: translateY(24px); transition: opacity .8s, transform .8s; }
.reveal.in { opacity: 1; transform: translateY(0); }
```

with a corresponding JS observer that adds `.in` on intersection will fail to apply `.in` to off-screen elements during the screenshot.

### Fix

Force the visible state before the screenshot:

```python
await page.evaluate("""() => {
  const selectors = ['.reveal', '.in-view', '.visible', '[data-animate]'];
  selectors.forEach(sel => document.querySelectorAll(sel).forEach(e => {
    e.classList.add('in', 'in-view', 'visible');
    if (e.dataset && 'animate' in e.dataset) e.dataset.animate = 'in';
  }));
}""")
await page.wait_for_timeout(300)  # let transitions settle
await page.screenshot(path='full_revealed.png', full_page=True)
```

### Generalization

The same pattern applies to any class-gated visibility:

- Tailwind animate-on-scroll plugins (`.animate-fade-in-up`)
- Framer Motion `whileInView` (rare in static HTML but possible via CDN)
- AOS library (`data-aos`, `aos-animate`)
- Custom data attributes like `data-state="hidden"`

When in doubt, inspect the page's CSS for `opacity: 0` rules tied to class toggles and force the resolved state.

## Pitfall 2: Vision hallucinates empty sections on very tall screenshots

### Symptom

A full-page PNG that is 6000+ px tall is passed to `vision_analyze`. The model reports a confident verdict like "the entire middle of the page is empty, only the hero and the footer rendered." The DOM contains all the sections; `curl` returns the full HTML; `page.evaluate` confirms section heights and child counts are reasonable. The vision model is simply wrong.

### Why it happens

Vision pipelines downsample input images to a fixed model resolution (often ~1024-2048 px on the long edge). A 1440×8283 screenshot becomes 178×1024 — each section that occupied 1200px vertically now occupies ~150px and any dark-themed design with subtle accents collapses into a near-uniform dark band the model interprets as empty.

### Defenses

In order of preference:

**1. Cross-check the DOM. Always.**

Before acting on a "section missing" vision verdict, measure the DOM:

```python
data = await page.evaluate("""() => {
  const out = [];
  document.querySelectorAll('header, section, footer').forEach(s => {
    const r = s.getBoundingClientRect();
    out.push({
      tag: s.tagName,
      id: s.id || '',
      cls: (s.className || '').toString().slice(0, 60),
      top: Math.round(r.top + window.scrollY),
      height: Math.round(r.height),
      childCount: s.querySelectorAll('*').length
    });
  });
  return { docHeight: document.documentElement.scrollHeight, sections: out };
}""")
```

If the DOM shows a section at `top=2645, height=1452, childCount=36`, that section is on the page and rendering. The vision verdict is wrong; do not edit the CSS.

**2. Slice the full page with PIL.**

Downsample-resilient inspection:

```python
from PIL import Image
im = Image.open('full_revealed.png')
w, h = im.size
n = max(2, min(6, h // 2000))  # 2-6 slices, ~2000px each
sh = h // n
for i in range(n):
    im.crop((0, i * sh, w, (i + 1) * sh)).save(f'slice_{i}.png')
```

Each slice is short enough (1440×~2000) that the vision pipeline does not destroy mid-image detail. Inspect each slice independently.

**3. Prefer per-viewport screenshots over one tall full-page capture.**

For QA, scroll-and-shoot at known offsets is more reliable:

```python
heights = await page.evaluate('document.documentElement.scrollHeight')
for i, y in enumerate(range(0, heights, 900)):
    await page.evaluate(f'window.scrollTo(0, {y})')
    await page.wait_for_timeout(200)
    await page.screenshot(path=f'scroll_{i:02d}.png', full_page=False)
```

Each 1440×900 image is well within the vision model's reading range.

### Diagnostic decision rule

| Vision says | DOM says | Verdict |
|---|---|---|
| section present | section present | trust the page |
| section missing | section present, non-zero height, normal child count | screenshot/vision artifact — do not edit CSS |
| section missing | section absent or height ~0 | real bug, fix the CSS or HTML |
| section present | section absent | impossible; re-check selectors |

DOM measurement wins ties.

## Quick reference: environment quirks observed in practice

- **Ubuntu chromium-browser is a snap stub.** `/usr/bin/chromium-browser` prints `requires the chromium snap to be installed` and exits 0 with no screenshot. Use `playwright install chromium` and drive Playwright's bundled binary instead. Do not attempt `apt install chromium`.
- **Port collisions are silent in background mode.** `python3 -m http.server <port>` started via `terminal(background=true)` exits immediately with `OSError: [Errno 98] Address already in use` if the port is taken. `curl` then returns HTTP 000 and the agent guesses the wrong cause. Always `process(action='poll', session_id=...)` if a probe fails.
- **Shell-level backgrounding is rejected.** `terminal` refuses `python3 ... &` in foreground mode. Use the `background=true` parameter explicitly.
- **`browser_console` with JS evaluation is not available on Camofox.** If `browser_navigate` works but `browser_console` rejects an `expression`, switch to Playwright `page.evaluate` for DOM inspection.
