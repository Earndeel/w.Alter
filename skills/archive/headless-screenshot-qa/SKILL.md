---
name: headless-screenshot-qa
description: Visually QA local HTML artifacts via Playwright + Chromium when the hosted browser tool is unavailable. Covers serving the file locally, forcing IntersectionObserver-gated content visible before capture, DOM measurement as ground truth, and slicing tall full-page screenshots so vision models can actually read them. Use whenever browser_navigate is down/404 and a design or landing page still needs visual verification before delivery.
version: 1.0.0
metadata:
  hermes:
    tags: [qa, playwright, chromium, screenshot, vision, design, verification]
    related_skills: [claude-design, frontend-design, popular-web-designs]
---

# Headless screenshot QA

Use this skill when an HTML artifact (landing page, prototype, dashboard, deck) needs visual verification but `browser_navigate` is unavailable — hosted browser returns 404, Camofox is down, or you are running in a context with no remote browser at all. Playwright's bundled Chromium is the reliable fallback.

The skill exists because two things go wrong almost every time someone screenshots a modern landing page headlessly:

1. `IntersectionObserver`-gated content (`.reveal { opacity: 0 }` toggled on scroll) renders blank in a single full-page screenshot.
2. Vision models hallucinate "empty sections" on screenshots taller than ~6000px because of aggressive downsampling.

Ignoring either one leads to rewriting working CSS to fix a problem that does not exist.

## Workflow

1. **Serve the artifact locally.** Run `python3 -m http.server <port>` via `terminal(background=true)`. Pick a free port — `8765` is often taken; try `8766`+. If the server seems unreachable, `process(action='poll', session_id=...)` to confirm it did not exit with `OSError: [Errno 98] Address already in use`. `terminal` rejects shell-level backgrounding (`&`), so always use the `background=true` parameter.
2. **Confirm HTTP serves the exact source.** Before screenshotting, prove the bytes on the wire match the file on disk:
   ```bash
   curl -s -o /tmp/served.html -w 'HTTP %{http_code} %{size_download}B\n' http://127.0.0.1:<port>/index.html \
     && diff -q /tmp/served.html <source-path> && echo 'SERVED=SOURCE OK'
   ```
3. **Run the capture script** (`scripts/qa_screenshot.py`). It produces `hero.png` (1440x900 viewport), `full_revealed.png` (full page with reveal classes forced visible), `mobile.png` (390x844 full page), and optionally `dom_measure.json` (per-section offsets and child counts) and `slice_*.png` (vertical tranches of the full page for vision).
4. **Inspect with `vision_analyze`.** Use hero and mobile as primary evidence. Treat `full_revealed.png` as secondary — see pitfall 2.

## Interactive local test-lab smoke

When the artifact has a local API and controls that enqueue background work (extractors, crawlers, fixture matrices, test labs), validate the runtime contract in addition to pixels:

1. Wait for the health/scenario bootstrap to enable run controls before clicking them.
2. Keep fixtures deterministic and execute them through the same scorer/projector as the live path; make LIVE network mode visibly distinct and enable it only for a validated scenario.
3. Treat enqueue completion and worker completion as different states. Wait for terminal `accepted`/`rejected`/`error` badges, not merely for the number of queued rows.
4. Scope status-count assertions to the run-list container because a detail pane may render a second badge for the active run.
5. Click a result tab and assert normalized records exist for a valid fixture, while a noise fixture is rejected.
6. Capture browser console/page errors and assert desktop/mobile `scrollWidth === clientWidth`.

The reusable API contract, Playwright sequence, race pitfalls, and local-live URL guard are in `references/interactive-panel-smoke.md`.

Support files under this skill:

- `scripts/qa_screenshot.py` — ready-to-run capture script with reveal-forcing, DOM measurement, and slicing.
- `references/pitfalls.md` — detailed notes on the two failure modes below and the defenses against them.
- `references/static-portal-contract-checklist.md` — route, auth, checkout, DOM, and responsive regression matrix for redesigning an existing static portal.
- `references/branded-spa-regression.md` — validated checks for transparent logo assets, `/` + `/app` SPA routing, scroll-triggered reveals, and post-deploy CDN proof.
- `references/spa-interaction-contract.md` — landing-to-app route assertions, audio-card network/state checks, and 1440px/390px deployment regression matrix.

## SPA interaction regression contract

Visual QA must cover the behavior surface that a screenshot cannot prove. For a branded Vite/React landing, assert the exact pathname after every `Student space` entry point (header, product preview, footer/mobile menu), assert the rendered audio-card count, click one card and observe both its `/audio/` request and playing state, and collect console/page errors plus `scrollWidth === clientWidth` at 1440px and 390px. A body-text assertion can pass while the app is actually on `/undefined`; URL assertions are mandatory.

For responsive complaints, capture the affected viewport and measure the panel rectangle, computed `padding-inline`, and child rectangles. Give full-width colored panels explicit horizontal padding and keep grid/flex children shrinkable with `min-width: 0`; do not treat a global `overflow: hidden` as proof that the layout is correct. See `references/spa-interaction-contract.md` for the reusable matrix.

## Pitfall 1: IntersectionObserver-gated content is invisible to Playwright by default

A design that uses `.reveal { opacity: 0 }` toggled by `IntersectionObserver` only triggers reveals on sections near the top of the viewport during a full-page screenshot scroll. Below-the-fold sections capture with `opacity: 0`. The vision model then honestly reports "empty black sections" — a real screenshot bug, not a hallucination.

Force reveal classes to their visible state before the full-page screenshot:

```python
await page.evaluate("document.querySelectorAll('.reveal').forEach(e => e.classList.add('in'));")
await page.wait_for_timeout(300)
await page.screenshot(path='full_revealed.png', full_page=True)
```

Apply the same pattern for any class-gated visibility: `.in-view`, `.visible`, `data-animate="in"`, framer-motion overlays, etc. The provided `qa_screenshot.py` handles the common selectors automatically.

## Pitfall 2: Vision models hallucinate "empty sections" on very tall full-page screenshots

A full-page PNG that is 8000+ px tall gets aggressively downsampled by the vision pipeline. Mid-document content can collapse into a thin strip of nearly-uniform pixels, and the model confidently reports "absent / not rendered / loading failed."

Defenses, in order of preference:

1. **Cross-check the DOM before believing the vision verdict.** Run `page.evaluate` to list `header, section, footer` with their `top`, `height`, and `childCount`. If the DOM shows the sections exist at the expected offsets with non-zero height and reasonable child counts, the page is fine and the vision model is wrong. The capture script writes this to `dom_measure.json` when `--measure` is passed.
2. **Slice the full page into 3-4 vertical tranches with PIL** and analyze each slice separately. Each slice is short enough that vision can read it. The capture script does this with `--slice`.
3. **Trust per-viewport screenshots (hero, scrolled positions, mobile)** over one mega-tall full-page image. Scroll-and-shoot is more reliable than a single giant capture.

**DOM measurement is the source of truth; vision is the second opinion.** A vision verdict of "section missing" with a DOM verdict of "section present, 1452px tall, 36 children" means the screenshot is the problem, not the artifact. Never rewrite working CSS on the strength of a vision hallucination alone.

## Environment notes

- On Ubuntu where `/usr/bin/chromium-browser` is the transitional snap shim that says `requires the chromium snap to be installed`, do not `apt install` — use Playwright's bundled Chromium: `playwright install chromium`, then drive it from Python.
- The `terminal` tool rejects `&` backgrounding. Always use `terminal(background=true)` and pair with `process(action='poll', ...)` for any local server.
- Pick a unique port per run if the previous server might still be alive; `Address already in use` exits the new server silently in the background and HTTP probes return 000.

## Static portal contract checks

For a redesign of an existing static portal, visual screenshots are not enough. Before capture, preserve and verify the behavior surface: route files and clean aliases, form IDs, auth/session calls, storage keys, checkout payloads, streaming hooks, and links into authenticated app pages. Keep a small route/contract matrix in a sibling frontend-design skill reference when the portal is likely to be revisited.

After serving the artifact, use Playwright to visit every public route at both desktop and mobile widths and assert:

- response status is successful;
- `document.documentElement.scrollWidth === document.documentElement.clientWidth`;
- no `console` errors, `pageerror`, or failed asset requests;
- no `[data-reveal]` element remains opacity `0` after load;
- headings, image `alt` attributes, form labels, and duplicate IDs are structurally sane.

Common static-portal regressions are transformed ticker/marquee elements expanding document width, reveal CSS leaving below-the-fold sections blank in screenshots, and colored bands inheriting the wrong button text color. Correct these in the shared CSS and re-run the same matrix rather than patching one viewport.

## When NOT to use this skill

- The hosted `browser_navigate` is working. Use it — it's faster and gives you click/console/network.
- The artifact is not a self-contained HTML file. For real apps, use the framework's own dev server and integration testing instead.
- You only need to confirm the file was written. `read_file` + line count is enough; you do not need pixels.
