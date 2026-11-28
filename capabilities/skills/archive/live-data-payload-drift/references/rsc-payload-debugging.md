# Next.js inline RSC payload dissection (artificialanalysis.ai)

Backend technique used to diagnose the Aug 2026 AA Agentic drift: the inline
flight prefix moved from `c:` to `d:`, silently killing both parsers and the
nightly cron for ~6 days.

## What the page contains

The interesting data is NOT in the rendered DOM chart (page-dependent subset).
It lives in an inline non-src `<script>` whose text is a sequence of
`self.__next_f.push([1,"<escaped>"]);` calls. The script text is escaped
strings — not valid JSON until each push is unescaped.

## Extraction (Playwright)

```python
from playwright.sync_api import sync_playwright
PUSH = re.compile(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)')

def decode_rsc_string(encoded):
    try:
        return json.loads(f'"{encoded}"')
    except json.JSONDecodeError:
        return bytes(encoded, "utf-8").decode("unicode_escape")

def strip_rsc_prefix(decoded):
    # generic: any one-letter prefix, e.g. c: -> d: without hardcoding either
    if len(decoded) >= 2 and decoded[0].isalpha() and decoded[1] == ":":
        return decoded[2:]
    return decoded
```

Find the script:

```js
Array.from(document.querySelectorAll('script:not([src])'))
  .map(s => s.textContent || '')
  .find(t => t.includes('headlineValue') && t.includes('costPerTask')) || ''
```

For the intelligence model page the marker strings are
`intelligenceIndexCostPerTask` + `intelligenceIndex`.

## Decode + walk

For each `PUSH` match:
1. `decoded = decode_rsc_string(m.group(1))`
2. `decoded = strip_rsc_prefix(decoded)`  ← the step that was missing
3. `payload = json.loads(decoded)` (skip on JSONDecodeError)
4. recursively walk for a list where the first item is a dict containing the
   marker field:
   - Agentic: marker = `"headlineValue" in item`
   - Intelligence: marker = `"intelligenceIndex" in item and
     "intelligenceIndexCostPerTask" in item`

## Validation baselines (Aug 2026)

- Agentic page: 139 models in the list, ~132 with `costPerTask.total`.
- Intelligence model-context page: ~580+ merged rows across `models` +
  `currentModel` (merge by exact slug, currentModel authoritative).
- Cost is `null` when missing — never treat missing as zero.

## Current AA row schema (frontier output)

`model` (display name incl. tier), `slug`, `score`, `cost_per_task_usd`,
`score_per_dollar`, plus `kie_*` fields (null / `skipped` unless `--with-kie`).
Notable: the field is `cost_per_task_usd`, NOT `cost` — an easy KeyError trap
when hand-rebuilding tables.
