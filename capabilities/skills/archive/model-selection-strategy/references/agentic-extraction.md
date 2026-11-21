# Agentic Index Extraction — Live Method

Data source: `https://artificialanalysis.ai/models/capabilities/agentic`

## Extraction pipeline

The page is Next.js App Router with React Server Components. Model data lives in a `self.__next_f.push` call inside an inline `<script>` tag:

```python
import json, re, codecs
from playwright.sync_api import sync_playwright

# 1. Load page (Playwright required — client-rendered, fetchers return empty HTML)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    page = browser.new_page(viewport={'width': 1400, 'height': 2000})
    page.goto('https://artificialanalysis.ai/models/capabilities/agentic', 
              wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(5000)
    
    # 2. Find inline script with headlineValue
    raw = page.evaluate("""() => {
        const all = document.querySelectorAll('script:not([src])');
        for (const s of all) {
            if ((s.textContent || '').includes('headlineValue')) return s.textContent;
        }
        return '';
    }""")
    browser.close()

# 3. Extract push payload: self.__next_f.push([1,"<escaped JSON>"])
idx = raw.find('self.__next_f.push([1,"')
start = idx + len('self.__next_f.push([1,"')
end = raw.index('"])', start)
data_str = raw[start:end]

# 4. Decode: Next.js escapes quotes as \". Use unicode_escape.
decoded = codecs.decode(data_str, 'unicode_escape')
if decoded.startswith('c:'):
    decoded = decoded[2:]  # remove RSC stream prefix

# 5. Parse RSC payload: ["$","$L2d",null,{"models":[...]}]
rsc = json.loads(decoded)
models = rsc[3]['models']  # 4th element = props

# 6. Extract per model
for mod in models:
    record = {
        'name': mod.get('shortName') or mod.get('name'),
        'slug': mod.get('slug'),
        'agentic_index': mod['headlineValue'],       # 0-100
        'total_cost_usd': mod['evalCost']['total'],
        'cost_per_task': mod['costPerTask']['total'],
        'price_1m_blended': mod.get('price1mBlended0To3To1'),
        'is_reasoning': mod.get('isReasoning'),
    }
```

## Why Playwright

- `Fetcher` / `StealthyFetcher` return empty HTML (client-rendered page).
- Camoufox browser tools don't support `evaluate()`.
- Playwright is installed on this VPS.

## Why codecs.decode

Plain `json.loads()` on the raw extract fails with "Expecting value" — the string contains literal `\"` sequences from Next.js inline script escaping. `unicode_escape` properly handles these.

## What the page actually contains

The data is NOT in `__NEXT_DATA__` (contrary to earlier assumptions). It's streamed via RSC with `self.__next_f.push([1,"c:[...]"])`. The RSC payload is a 4-element array where element 3 holds the props with the `models` array.
