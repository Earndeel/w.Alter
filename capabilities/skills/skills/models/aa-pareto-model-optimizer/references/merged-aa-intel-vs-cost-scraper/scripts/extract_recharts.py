#!/usr/bin/env python3
"""Extract cost_per_task + intelligence from AA Recharts scatter chart.
Usage: python3 extract_recharts.py [model_slug]  (default: gpt-5-5)
Returns JSON with 26 models: {label, x: cost_per_task_USD, y: intel_index, url, reasoning}
Needs: playwright (pip install playwright && python -m playwright install chromium)
"""
import json, sys
from playwright.sync_api import sync_playwright

MODEL_SLUG = sys.argv[1] if len(sys.argv) > 1 else "gpt-5-5"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36',
        viewport={'width': 1400, 'height': 1000}
    )
    page = context.new_page()
    
    url = f'https://artificialanalysis.ai/models/{MODEL_SLUG}'
    page.goto(url, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(8000)
    
    # Click "Intelligence vs. Cost per Task" toggle
    page.evaluate("""() => {
        const buttons = document.querySelectorAll('button');
        for (const b of buttons) {
            if ((b.innerText || '').trim().includes('Cost per Task')) {
                b.click(); return;
            }
        }
        for (const b of buttons) {
            if ((b.innerText || '').trim().includes('Intelligence vs. Cost')) {
                b.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    
    # Scroll through candidate positions (chart moves between pages)
    for scroll_pos in [6900, 5000, 3000, 1500, 8000]:
        page.evaluate(f"window.scrollTo(0, {scroll_pos})")
        page.wait_for_timeout(1000)
    
    # Extract Recharts React fiber payload
    result = page.evaluate("""() => {
        const svgs = document.querySelectorAll('svg');
        let targetSvg = null;
        
        // Primary: find SVG with $0.XX or "Cost per Task" text + circles
        for (const svg of svgs) {
            const r = svg.getBoundingClientRect();
            if (r.width > 300 && r.height > 200 && svg.querySelector('circle')) {
                const txt = svg.textContent || '';
                if (txt.includes('$0.') || txt.includes('Cost per Task') || txt.includes('Intelligence')) {
                    targetSvg = svg; break;
                }
            }
        }
        
        // Fallback: any SVG with 10+ circles and $ signs
        if (!targetSvg) {
            for (const svg of svgs) {
                const circles = svg.querySelectorAll('circle');
                if (circles.length >= 10) {
                    const txt = svg.textContent || '';
                    if ((txt.match(/\\$/g) || []).length >= 5) {
                        targetSvg = svg; break;
                    }
                }
            }
        }
        
        if (!targetSvg) return {error: 'no svg found', svg_count: svgs.length};
        
        const circles = Array.from(targetSvg.querySelectorAll('circle'));
        const out = [];
        
        circles.forEach((c, idx) => {
            const keys = Object.keys(c);
            const reactKey = keys.find(k => k.startsWith('__reactFiber') || k.startsWith('__reactProps'));
            if (!reactKey) return;
            
            let fiber = c[reactKey];
            let depth = 0;
            let payload = null;
            while (fiber && depth < 30) {
                const p = fiber.memoizedProps || fiber.pendingProps;
                if (p && p.payload && p.payload.label) {
                    payload = p.payload;
                    break;
                }
                fiber = fiber.return;
                depth++;
            }
            if (payload) {
                out.push({
                    idx,
                    label: payload.label,
                    x: payload.x,  // cost per task in USD
                    y: payload.y,  // intelligence index
                    url: payload.url,
                    reasoning: payload.reasoning,
                });
            }
        });
        
        return {data: out, circle_count: circles.length};
    }""")
    
    print(json.dumps(result, indent=2))
    browser.close()
