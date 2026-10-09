#!/usr/bin/env python3
"""Headless screenshot QA for local HTML artifacts.

Use when browser_navigate is unavailable. Captures hero viewport, full-page
(with .reveal classes forced visible), and mobile, plus optional DOM section
measurements and PIL slicing for vision QA.

Usage:
    python3 qa_screenshot.py <url> <output_dir> [--slice] [--measure]

Requires: playwright + chromium installed (playwright install chromium).
"""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright


async def capture(url: str, outdir: Path, do_slice: bool, do_measure: bool) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        ctx = await browser.new_context(viewport={'width': 1440, 'height': 900})
        page = await ctx.new_page()
        await page.goto(url, wait_until='networkidle', timeout=20000)
        await page.wait_for_timeout(1500)

        # Force class-gated visibility (.reveal pattern + common variants) so the
        # full-page screenshot does not show empty below-the-fold sections.
        await page.evaluate(
            """() => {
              const sels = ['.reveal', '.in-view', '.visible', '[data-animate]'];
              sels.forEach(sel => document.querySelectorAll(sel).forEach(e => {
                e.classList.add('in', 'in-view', 'visible');
                if (e.dataset && 'animate' in e.dataset) e.dataset.animate = 'in';
              }));
            }"""
        )
        await page.wait_for_timeout(300)

        # Hero viewport (above the fold)
        await page.screenshot(path=str(outdir / 'hero.png'), full_page=False)
        # Full page, with reveals forced
        await page.screenshot(path=str(outdir / 'full_revealed.png'), full_page=True)

        if do_measure:
            data = await page.evaluate(
                """() => {
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
                }"""
            )
            (outdir / 'dom_measure.json').write_text(json.dumps(data, indent=2))

        # Mobile
        await page.set_viewport_size({'width': 390, 'height': 844})
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(outdir / 'mobile.png'), full_page=True)

        await browser.close()

    if do_slice:
        try:
            from PIL import Image
        except ImportError:
            print('PIL not available, skipping slice', file=sys.stderr)
            return
        im = Image.open(outdir / 'full_revealed.png')
        w, h = im.size
        n = max(2, min(6, h // 2000))  # ~2000px per slice, 2-6 slices
        sh = h // n
        for i in range(n):
            im.crop((0, i * sh, w, (i + 1) * sh)).save(outdir / f'slice_{i}.png')
        print(f'sliced into {n} parts of ~{sh}px')

    print('OK')


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    url = sys.argv[1]
    outdir = Path(sys.argv[2])
    do_slice = '--slice' in sys.argv[3:]
    do_measure = '--measure' in sys.argv[3:]
    asyncio.run(capture(url, outdir, do_slice, do_measure))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
