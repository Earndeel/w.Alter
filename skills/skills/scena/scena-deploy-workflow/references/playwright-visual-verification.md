# Playwright Visual Verification for Scena Pages

Reusable recipe for verifying a designed HTML artifact in headless Chromium before declaring a Cloudflare Pages deploy done. Built from a Scena portal landing redesign session where a full-page screenshot fooled the vision model into reporting empty middle sections on a page that was actually fine.

## When to use

- Designed artifact for scena-portal / scena-admin needs visual confirmation before delivery
- Browser MCP unavailable or unreliable in this runtime
- You need both: DOM truth + visual sanity check

## Setup

Playwright Chromium is the right pick on this host. The Ubuntu chromium-browser package is a transitional snap stub that refuses to launch headless. Install once:

playwright install chromium

## Recipe outline

1. Serve the artifact locally via python3 http.server on an ephemeral high port (8766+). Pick a fresh port — 8765 is often taken.
2. Launch Playwright Chromium headless with args=['--no-sandbox'], viewport 1440x900.
3. page.goto(url, wait_until='networkidle', timeout=20000), then wait 1500ms.
4. **Force IntersectionObserver reveal classes BEFORE capture** — page.evaluate adds .in to every .reveal element. Otherwise scroll-reveal animations leave the page mostly at opacity 0 in the screenshot.
5. DOM truth pass — page.evaluate returns an array of every section with tag, id, className, top, height, childCount. This is the source of truth.
6. Capture full_page=True, then a viewport-only hero shot.
7. Re-open a 390x844 context for the mobile screenshot.

## Pitfalls

### 1. Full-page screenshots above ~3000px hallucinate empty sections

Vision models receive a heavily downscaled image when a PNG is 1440x8000+. Middle bands become low-detail and the model often reports blank space or missing content. This is a sampling artifact, NOT a real layout bug.

Fix: trust the DOM measurement first. Then slice the full-page PNG into 3 to 4 vertical tranches with PIL and re-ask vision on each tranche separately. If the DOM says section.cls=pipeline-section, height=1452, childCount=36, the section is there. A vision-says-empty verdict against that DOM evidence is a vision error, not a CSS bug.

### 2. IntersectionObserver-driven .reveal classes stay at opacity 0

If the artifact uses .reveal { opacity: 0 } plus IntersectionObserver to add .in on scroll, a headless screenshot captures the unrevealed state — most of the page looks invisible. Always force-add the visibility class before capture, or scroll-step through the page first.

### 3. Local HTTP server port collisions

python3 -m http.server 8765 exits with OSError [Errno 98] Address already in use if the port is taken. Pick a fresh high port and verify with process(action=poll) after starting in background — background=True runs silently and a crashed server looks identical to a running one from the agent's side. Always poll once after launch.

### 4. Background plus shell ampersand combo is rejected

Foreground terminal with trailing ampersand is blocked. Use terminal(background=True, ...) and capture the session_id for process(action=poll or kill). Don't pair shell ampersand backgrounding with foreground mode.

## Full verification checklist before saying delivered

1. File written at the stated path, byte count matches expectations.
2. HTTP server returns 200 and curl output diffs identical to source.
3. DOM measurement shows all expected sections with non-trivial heights and childCount greater than 0.
4. Reveal-style visibility classes forced before screenshotting.
5. Desktop 1440x900 hero screenshot inspected by vision — accent color, typography, key UI elements all visible.
6. Mobile 390-wide screenshot inspected — no overflow, no broken grid.
7. If full-page screenshot triggered an empty-section vision flag, tranche the image and re-verify, or trust DOM heights.

A negative vision verdict against a positive DOM verdict means re-tranche, not re-build.

## Integration with the deploy flow

Run this verification on the local artifact BEFORE wrangler pages deploy. After deploy, the Post-Deploy Verification block in the main SKILL.md takes over (curl prod, diff with preview hash). The two checks are complementary: this one validates the artifact is visually correct, the deploy block validates it actually went live.
