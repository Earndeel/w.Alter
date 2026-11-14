# Agentic Index Extraction — Proven Technique

Source: `https://artificialanalysis.ai/models/capabilities/agentic`

The page is Next.js App Router with React Server Components. Model data
is embedded in a `self.__next_f.push([1,"c:..."])` RSC payload inside
an inline `<script>` tag. 171 models as of July 2026.

## Playwright Extraction

```python
import json, re, codecs
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    page.goto('https://artificialanalysis.ai/models/capabilities/agentic',
              wait_until='domcontentloaded', timeout=60000)
    page.wait_for_timeout(5000)

    raw = page.evaluate("""() => {
        for (const s of document.querySelectorAll('script:not([src])')) {
            const txt = s.textContent || '';
            if (txt.includes('headlineValue') && txt.includes('evalCost'))
                return txt;
        }
        return '';
    }""")

    idx = raw.find('self.__next_f.push([1,"')
    start = idx + len('self.__next_f.push([1,"')
    end = raw.index('"])', start)
    data_str = raw[start:end]

    decoded = codecs.decode(data_str, 'unicode_escape')
    if decoded.startswith('c:'):
        decoded = decoded[2:]

    rsc = json.loads(decoded)
    models = rsc[3]['models']  # 4th element = props
```

## Relevant Fields

| Field | Meaning |
|---|---|
| `headlineValue` | Agentic Index (0-100) |
| `evalCost.total` | Total evaluation cost (USD) |
| `costPerTask.total` | Cost per task (USD) |
| `shortName` / `name` | Display name |
| `slug` | URL slug |
| `isReasoning` | Reasoning variant? |
| `modelCreator.name` | Provider |

## Data Shape

```json
{
  "name": "Claude Opus 5 (max)",
  "slug": "claude-opus-5",
  "agentic_index": 55.3,
  "total_cost_usd": 1681.31,
  "cost_per_task_usd": 4.3767,
  "price_1m_blended": 15.00,
  "is_reasoning": true,
  "creator": "Anthropic"
}
```
