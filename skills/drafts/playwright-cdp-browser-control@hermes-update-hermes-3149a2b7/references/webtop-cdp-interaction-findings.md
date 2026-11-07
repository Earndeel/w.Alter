# Webtop CDP Interaction Findings — 2026-05-21

## Test Environment
- Webtop Docker container `lscr.io/linuxserver/webtop:ubuntu-xfce`
- Chromium 145.0.7632.75, CDP on port 9222→9223 via socat
- Container IP: 172.17.0.3
- Playwright `connect_over_cdp("http://172.17.0.3:9223")`

## Viewport & Screenshots
- **Outer window:** 1920×1080
- **Inner viewport:** 1912×937 (minus browser chrome / XFCE taskbar)
- **DPR:** 1.5 → screenshots rendered at 2880×1620 pixels
- Screenshots are **viewport-only** (no browser chrome/address bar visible) — ideal for vision analysis
- **Setting viewport:** `page.set_viewport_size({"width": 1920, "height": 1080})` works but must be done BEFORE navigation, not after. Calling it on an existing page that already navigated causes `TargetClosedError`.

## Interaction Chain That Works
```python
# 1. Use existing context (preserves cookies)
context = browser.contexts[0]
page = context.pages[0] if context.pages else context.new_page()
page.set_viewport_size({"width": 1920, "height": 1080})

# 2. Navigate
page.goto("https://example.com", wait_until="load", timeout=15000)
time.sleep(2)

# 3. Focus (more reliable than click on CDP)
search = page.query_selector('textarea[name="q"]')
search.focus()
time.sleep(0.3)

# 4. Type via keyboard
page.keyboard.type("search term", delay=30)

# 5. Enter
page.keyboard.press("Enter")
time.sleep(3)

# 6. Scroll
page.evaluate("window.scrollBy(0, 500)")

# 7. Screenshot
page.screenshot(path="/tmp/result.png")
```

## What Breaks

### `page.set_viewport_size()` after navigation → TargetClosedError
If you navigate first and then call `set_viewport_size()`, the page crashes. Set viewport BEFORE goto, or create a new context with viewport:
```python
context = browser.new_context(viewport={"width": 1920, "height": 1080})
page = context.new_page()
page.goto(...)  # viewport is already set
```

### `element.click()` then `page.keyboard.type()` → TargetClosedError
On CDP, `search.click()` can cause the page to close (race condition with focus). Use `search.focus()` instead — it's more reliable.

### After navigation, `query_selector` → TargetClosedError
After `page.keyboard.press("Enter")` triggers a navigation, the page object becomes stale. Must wait for navigation to complete and re-query:
```python
page.keyboard.press("Enter")
page.wait_for_load_state("domcontentloaded")  # wait for new page
# Now safe to query
first_result = page.query_selector('#search a')
```

### Google → CAPTCHA "unusual traffic"
Webtop Chromium has no anti-detect. Google detects the automated browser + datacenter IP and shows reCAPTCHA after any search query. **Not fixable with cookies** — it's fingerprint + IP based. Use Camoufox or Mac Brave CDP instead.

### Facebook → Page closes entirely
Facebook's anti-bot detects CDP automation and closes the page (`TargetClosedError`). Even with injected cookies, the fingerprint is detected. **Fix:** Either inject Mac Brave cookies into Camoufox (anti-detect) or navigate via Mac Brave CDP directly.

## Anti-Bot Status by Site

| Site | Webtop Chromium | Camoufox | Mac Brave CDP |
|------|----------------|----------|---------------|
| Google Search | ❌ CAPTCHA | ⚠️ Thai locale, may work | ✅ |
| Facebook | ❌ Page closes | ⚠️ May detect | ✅ (if running) |
| Reddit | ✅ | ✅ | ✅ |
| GitHub | ✅ | ✅ | ✅ |
| Most sites | ✅ | ✅ | ✅ |

## Recommended Workflow for Authenticated Browsing

1. **Extract cookies from Mac Brave** (via SSH tunnel + CDP `Storage.getCookies`)
2. **Inject into Playwright context** on Webtop:
   ```python
   cookies = [...]  # from Mac Brave CDP
   context = browser.new_context(viewport={"width": 1920, "height": 1080})
   context.add_cookies(cookies)
   page = context.new_page()
   ```
3. **For anti-bot sites** (Google, Facebook): skip Webtop Chromium entirely. Use Mac Brave CDP directly or Camoufox with injected cookies.
4. **For normal sites**: Webtop Chromium + injected cookies works fine.

## Key Patterns

### Reliable input sequence
```python
element.focus()  # NOT .click()
time.sleep(0.3)
page.keyboard.type("text", delay=30)  # NOT element.type()
```

### Scroll + screenshot cycle
```python
page.evaluate("window.scrollBy(0, 500)")
time.sleep(0.5)
page.screenshot(path="/tmp/scroll-N.png")
```

### Getting page dimensions for coordinate-based clicks
```python
dims = page.evaluate("""() => ({
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio,
    scrollY: window.scrollY,
    scrollHeight: document.body.scrollHeight
})""")
```
