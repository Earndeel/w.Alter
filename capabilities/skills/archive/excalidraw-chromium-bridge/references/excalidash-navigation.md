# ExcaliDash Navigation Patterns (Playwright)

ExcaliDash is a SPA with broken client-side routing for deep links. This reference documents reliable navigation patterns.

## URL Routing

| URL Format | Works? | Notes |
|------------|--------|-------|
| `https://domain/d/{id}` | ❌ | Redirects to `/` — client-side routing broken |
| `https://domain/editor/{id}` | ✅ | Correct format for opening a specific drawing |
| `https://domain/` | ✅ | Dashboard — shows all drawings as cards |
| `https://domain/login` | ✅ | Login page |

**Critical:** The API returns drawing URLs as `/d/{id}` but this format DOES NOT WORK in the browser. Always use `/editor/{id}` instead.

## Playwright Login + Navigate Pattern

```python
from playwright.sync_api import sync_playwright
import time

DOMAIN = "draw.walter-ai.cloud"
EMAIL = "lucas@walter-ai.cloud"
PASSWORD = "{{bw:draw.walter-ai.cloud:password}}"
DRAWING_ID = "1bd29c80-2439-4cc8-a92e-7731f48ae0dd"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    
    # Step 1: Login
    page.goto(f"https://{DOMAIN}/login", timeout=30000)
    time.sleep(5)
    page.fill('input[type="email"], input[name="email"]', EMAIL)
    page.fill('input[type="password"]', PASSWORD)
    time.sleep(1)
    page.click('button:has-text("Sign in"), button[type="submit"]')
    time.sleep(8)
    
    # Step 2: Navigate directly to drawing
    page.goto(f"https://{DOMAIN}/editor/{DRAWING_ID}", timeout=30000)
    time.sleep(10)
    
    # Step 3: Verify
    url = page.url
    print(f"URL: {url}")
    
    # Step 4: Screenshot
    page.screenshot(path="/root/diagrams/drawing.png", full_page=False)
    
    browser.close()
```

**Key points:**
- Login session cookie persists across page.goto() calls
- After login, navigate directly to /editor/{id} — no need to go through dashboard
- Wait 8-10 seconds after login for session to stabilize
- Wait 10 seconds after navigating to drawing for canvas to render

## Dashboard Navigation (Alternative)

| Action | Result |
|--------|--------|
| Click text link on card | ❌ Redirects to / |
| Double-click card thumbnail | ✅ Opens drawing in editor |
| Double-click wrong area | ⚠️ May create NEW empty drawing |

**Double-click is unreliable** — prefer direct URL navigation.

## Zoom to Fit

```python
page.keyboard.press("Control+Shift+1")
time.sleep(3)
```

## Verification

```python
canvas_info = page.evaluate("""
() => {
    const svgEl = document.querySelector('svg');
    const texts = document.querySelectorAll('svg text');
    const paths = document.querySelectorAll('svg path');
    return {hasSvg: !!svgEl, texts: texts.length, paths: paths.length};
}
""")
# paths > 0 = diagram loaded
```

## Known Issues

1. Blank canvas after navigation: wait 15-20s for SPA hydration
2. Wrong drawing opened: double-click may target wrong card — use direct URL
3. New empty drawing created: double-click on empty area triggers "New Drawing"
4. Update banner blocks view: close it first or wait for auto-dismiss
