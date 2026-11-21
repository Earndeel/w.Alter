#!/usr/bin/env python3
"""
Scrape Artificial Analysis model page for the Intelligence vs. Cost per Task table.

Usage:
  python scripts/scrape_aa_cost_per_task.py deepseek-v4-pro > /tmp/aa_cost_task.json

Notes:
  - Uses Playwright because the relevant AA table is rendered client-side.
  - Clicks the "Intelligence vs. Cost per Task" view if present.
  - Emits JSON rows with: label, url, intelligence_index, cost_per_intelligence_index_task_usd.
  - This is non-paid browser scraping; it must not call model inference APIs.
"""
import json
import re
import sys

from playwright.sync_api import sync_playwright

slug = sys.argv[1] if len(sys.argv) > 1 else "deepseek-v4-pro"
url = f"https://artificialanalysis.ai/models/{slug}"

EXTRACT_JS = r"""
() => {
  for (const b of document.querySelectorAll('button')) {
    if ((b.innerText || '').trim().includes('Intelligence vs. Cost per Task')) {
      b.click();
      break;
    }
  }
  const rows = [];
  const links = Array.from(document.querySelectorAll('a[href*="/models/"]'));
  for (const a of links) {
    const row = a.closest('tr') || a.closest('[role="row"]') || a.parentElement;
    if (!row) continue;
    const text = (row.innerText || '').replace(/\s+/g, ' ').trim();
    if (!text || !/\$/.test(text)) continue;
    rows.push({label: (a.innerText || '').trim(), href: a.href, text});
  }
  return Array.from(new Map(rows.map(r => [r.href + '|' + r.text, r])).values());
}
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1200})
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)
    raw_rows = page.evaluate(EXTRACT_JS)
    browser.close()

out = []
for r in raw_rows:
    nums = re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)|\b([0-9]+(?:\.[0-9]+)?)\b", r["text"])
    flat = [float(a or b) for a, b in nums]
    if not flat:
        continue
    # AA row text usually includes Intelligence Index plus one or more dollar task costs.
    dollars = [float(x) for x in re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", r["text"])]
    intelligence = None
    for n in flat:
        if 0 < n <= 100 and n not in dollars:
            intelligence = n
            break
    out.append({
        "label": r["label"],
        "url": r["href"],
        "intelligence_index": intelligence,
        "cost_per_intelligence_index_task_usd": dollars[0] if dollars else None,
        "row_text": r["text"],
    })

print(json.dumps({"source_url": url, "rows": out}, ensure_ascii=False, indent=2))
