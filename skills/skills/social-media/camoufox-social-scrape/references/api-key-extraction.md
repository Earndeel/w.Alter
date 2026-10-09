# Extracting Masked API Keys from Web Dashboards

## Problem

SPA dashboards (One-API, Sub2API, AIPrimeTech, OpenRouter, etc.) mask API keys in:
- **DOM**: `<code>«secret:vault»</code>` — truncated, not the full key
- **API responses**: `/api/v1/keys` returns `{"key": "«secret:vault»"}` — same masked value
- **Clipboard**: "Copy" buttons copy the masked value

The full key is only displayed **visually** in the "Use Key" / "Configure" modal.

## Solution: Screenshot + Vision

```python
import http.client, json, time, base64

TAB = "tab-id-here"

# 1. Navigate to API Keys page
camoufox("POST", "/tab/navigate", {"tabId": TAB, "url": "https://site.com/panel/apikeys"})
time.sleep(3)

# 2. Click "Use Key" or "Configure" button for target key
# Use JS evaluate to find and click
camoufox("POST", "/tab/evaluate", {"tabId": TAB,
    "expression": """
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.includes('Use Key') || btn.textContent.includes('Configure')) {
                btn.click(); break;
            }
        }
    """})
time.sleep(2)

# 3. Screenshot the modal
screenshot_b64 = camoufox("GET", f"/tab/screenshot?tabId={TAB}")["screenshot"]
with open("/tmp/api-key-modal.png", "wb") as f:
    f.write(base64.b64decode(screenshot_b64))

# 4. Read full key via vision_analyze
# → vision_analyze("/tmp/api-key-modal.png", "Read the EXACT full API key strings (sk-...)")
```

## Why this works

The modal renders the full key as visible text (for copy-paste). The DOM's innerHTML contains the full key. But:
- The API endpoint masks it server-side
- The table/list view shows a truncated version
- The modal is the only place with the complete value

Vision models read the rendered text, which is the full unmasked key.

## Pitfalls

1. **Don't waste time on DOM extraction** — `document.querySelector('code').textContent` returns the masked value in list view. Only the modal has the full key.
2. **Don't call the API** — `/api/v1/keys` returns masked keys by design. No query parameter reveals them.
3. **Modal may close on outside click** — take the screenshot immediately after opening.
4. **Multiple keys** — repeat the click+screenshot cycle for each key. Modals are usually per-key.
5. **Dark themes** — some modals use dark backgrounds. Vision models handle this fine, but ensure good contrast.

## Tested on

- AIPrimeTech (Sub2API) — "Use Key" modal shows full `sk-...` key + env variable config
