# AA Agentic Index — RSC Extraction Method

## Source

https://artificialanalysis.ai/models/capabilities/agentic

## Method

The Agentic Index page is a Next.js App Router page that streams data via React Server Components. The data is NOT in the v2 API, NOT in a Recharts DOM graph — it's in a `self.__next_f.push` payload inside an inline `<script>` tag.

### Step-by-step extraction

```python
import json, re, codecs
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    page = browser.new_page()
    page.goto('https://artificialanalysis.ai/models/capabilities/agentic', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(5000)
    
    # 1. Extract the inline script containing headlineValue
    script_text = page.evaluate("""() => {
        for (const s of document.querySelectorAll('script:not([src])')) {
            if ((s.textContent || '').includes('headlineValue')) return s.textContent;
        }
        return '';
    }""")
    
    # 2. Extract the push payload: self.__next_f.push([1,"<data>"])
    idx = script_text.find('self.__next_f.push([1,"')
    start = idx + len('self.__next_f.push([1,"')
    end = script_text.index('"])', start)
    data_str = script_text[start:end]
    
    # 3. Decode unicode escapes (critical step!)
    decoded = codecs.decode(data_str, 'unicode_escape')
    
    # 4. Remove "c:" prefix and parse RSC payload
    if decoded.startswith('c:'):
        decoded = decoded[2:]
    rsc = json.loads(decoded)  # ["$","$L2d",null,{models:[...]}]
    
    # 5. Extract models from the 4th element
    models = rsc[3]['models']  # 171 models
    
    browser.close()
```

### Output fields per model

```python
for mod in models:
    {
        'name': mod['shortName'],           # e.g. "Claude Opus 5 (max)"
        'slug': mod['slug'],                # e.g. "claude-opus-5"
        'agentic_index': mod['headlineValue'],  # 0-100, average of component benchmarks
        'total_cost': mod['evalCost']['total'],  # USD, full evaluation cost
        'cost_per_task': mod['costPerTask']['total'],  # USD, per-task cost
        'price_1m_blended': mod['price1mBlended0To3To1'],  # USD per 1M tokens
        'intelligence_index': mod['intelligenceIndex'],  # For comparison only
        'creator': mod['modelCreator']['name'],
    }
```

### Key differences from Intelligence Index

The Agentic Index penalizes non-agentic models more severely:

| Model | Intel Index | Agentic Index | Δ |
|---|---|---|---|
| Claude Opus 5 (max) | 60.7 | 55.3 | −5.4 |
| GPT-5.6 Luna (max) | 51.2 | 45.6 | −5.6 |
| DeepSeek V4 Pro (max) | 44.3 | 36.4 | **−7.9** |

DeepSeek drops the most because it's weaker at tool-use and autonomous workflows despite strong general intelligence.

### Session reference (2026-07-29)

Full extraction results: `/tmp/aa_agentic_models.json` (171 models)
Pareto analysis: filtered to agentic > 30, min gain 0.5 → 11 models on pragmatic frontier.
