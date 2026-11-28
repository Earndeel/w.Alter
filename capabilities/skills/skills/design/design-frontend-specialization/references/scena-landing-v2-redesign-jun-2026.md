# Scena landing page V2 redesign (June 2026)

Use this when redesigning the Scena public site, or as a reference for dark-theme landing page patterns with GSAP + canvas.

## Context

Project: `/root/projects/scena-cloudflare/`
Portal pages: `pages/portal/`
The V1 landing (`index.html`) uses a warm orange/amber cinematic palette. The V2 landing (`index-v2.html`) is a radical aesthetic pivot: icy/electric dark theme with canvas particles, GSAP premium plugins, terminal-style hero demo, and asymmetric step layouts. V1 is preserved untouched.

## V2 design decisions

### Palette shift: warm to icy/electric

| Token | V1 | V2 |
|---|---|---|
| Page bg | `#0a0908` (warm black) | `#03040c` (deep space blue-black) |
| Elevated bg | `#131110` | `#1e2640` (iteratively tuned) |
| Accent | `#e8a857` (amber) | `#6fb4ff` (ice blue) to `#a06bff` (electric purple) gradient |
| Serif | Instrument Serif | Instrument Serif (kept) |
| Mono | none | JetBrains Mono (technical labels, terminal, metadata) |
| Texture | SVG grain only | SVG grain + scanline overlay + aurora drift + particle canvas |

### Hero demo: Telegram chat to Terminal CLI

V1 shows a CSS-animated Telegram chat bubble with typing dots and video thumbnails.
V2 replaces this with a terminal window (macOS-style dots bar + JetBrains Mono body) showing a simulated CLI session: user prompt, Scena analysis, style/ratio/duration params, generation status, 3 video thumbnail grid. Feels more "engine" and less "chatbot".

### New interactive layers (vanilla JS, no build step)

1. **Particle canvas** — 70 particles (ice blue + electric purple), connection lines when distance < 140px. Respects `prefers-reduced-motion`.
2. **Spotlight tracking** — 600px radial gradient follows mouse, ice-blue glow.
3. **Magnetic hover** — primary buttons translate 12% toward cursor on mousemove.
4. **GSAP animations** — ScrollTrigger reveals, count-up stats, staggered gallery/pricing entrances. Loaded from local `/assets/gsap/` copies.

### Layout changes

- **How it works**: V1 uses 3 equal cards. V2 uses asymmetric rows (80px num | content | 280px visual card) with left accent line that fills on hover.
- **Gallery**: same 4-column 9:16 grid, hover scales art inside frame (1.1x) and lifts card with ice-glow shadow.
- **Pricing**: same 3 plans/prices, featured plan gets gradient top border + ice-glow shadow.

### Preserved contracts

All functional elements identical to V1: 6 Google OAuth links, same pricing (0€/49€/149€), same FAQ, same footer, same nav links.

## Pitfalls discovered

### 1. ScrambleTextPlugin destroys HTML markup

Initial V2 used `gsap.from(heroH1, { scrambleText: { text: heroH1.innerHTML } })` for a binary-scramble entrance on the H1. The plugin replaced the element's content with scrambled plain text, stripping all `<br>` and `<span class="accent-grad">` tags. The headline rendered as raw visible HTML source code.

**Fix**: Replaced with `gsap.from(heroH1, { opacity: 0, y: 30 })` + separate `gsap.from(accentWord, { opacity: 0, filter: 'blur(8px)' })`. Preserves markup, still looks premium.

**Rule**: ScrambleTextPlugin is only safe on plain-text elements. For headlines with inline tags, use opacity/y/blur entrance or SplitText.

### 2. Vision model cannot evaluate dark-theme contrast

After the ScrambleText fix, the vision model repeatedly rated pricing card contrast as 1-2/10 across 5 iterations of progressively lightening `--bg-elevated` (`#0b0e1a` to `#0f1322` to `#141a2e` to `#1a2138` to `#1e2640`). Each time it claimed cards were "invisible."

Numerical verification via Playwright `page.evaluate()` confirmed:
- Page bg: `rgb(3, 4, 12)` = #03040c
- Card bg: `rgb(26, 33, 56)` = #1a2138
- WCAG contrast ratio: ~4.8:1 (dim text on card) to ~12:1 (bright text on card) — both pass AA

**Rule**: For dark themes, verify contrast with `getComputedStyle` RGB extraction + luminance math, not vision model screenshots. The vision model compresses dark PNGs and loses subtle luminance differences. Trust the numbers.

### 3. Dark theme contrast starting point

When building a dark theme with `--bg-deep: #03040c`, start `--bg-elevated` at **at least** `#1a2138` or lighter. The delta between page bg and card bg should be >= 15 luminance points in each RGB channel.

### 4. Particle canvas sizing

Canvas height must match the hero section height, not window height. Use `canvas.parentElement.offsetHeight` in the resize function. Otherwise particles only fill the viewport-visible portion.

## Verification workflow

```bash
# Local preview
cd /root/projects/scena-cloudflare/pages/portal
python3 -m http.server 4178 --bind 127.0.0.1

# HTTP smoke
curl -s -o /dev/null -w "%{http_code} %{size_download}B" http://127.0.0.1:4178/index-v2.html

# GSAP asset check
for f in gsap.min.js ScrollTrigger.min.js SplitText.min.js ScrambleTextPlugin.min.js; do
  curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:4178/assets/gsap/$f"
done

# Playwright visual + console + H1 check
python3 -c "
from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    errors = []
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
    page.goto('http://127.0.0.1:4178/index-v2.html', wait_until='networkidle', timeout=15000)
    time.sleep(3)
    page.screenshot(path='/tmp/scena-v2-hero.png')
    h1 = page.evaluate('document.querySelector(\".hero-h1\").textContent')
    assert '<' not in h1, f'H1 contains raw HTML: {h1}'
    print('Console errors:', errors[:5] if errors else 'none')
    print('H1 OK:', h1.strip()[:60])
    browser.close()
"
```

## Deploy

Do NOT deploy to production before Lucas approves the visual direction. After approval, deploy via `wrangler pages deploy pages/portal --project-name=scena-portal`. If deploying V2 as default, rename `index-v2.html` to `index.html` (after backing up V1 as `index-v1.html`).
