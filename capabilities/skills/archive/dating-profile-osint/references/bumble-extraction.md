# Bumble Profile Extraction

## Photo CDN URL Pattern

```
https://us1.ecdn2.bumbcdn.com/p{NNN}/hidden?euri={encoded}&size={WxH}&ck={hash}&wm_size=72x72&wm_offs=-5x-5&h={code}&gs={type}&t=42.1.0.0
```

- `size=75x75` = thumbnail in sidebar
- `size=450x675` = main profile photo (first photo)
- `size=453x1536` = full-res profile photo (carousel)
- `gs=server_get_user%3A%3Aprofile_photo` = main photo
- `gs=o` = other carousel photos
- `wm_size` / `wm_offs` = watermark (can be omitted for download)

## Download Command

```bash
curl -sL -o photo.jpg -H "Referer: https://bumble.com/" "$URL"
```

**CRITICAL**: No Referer = 403 from CDN.

## DOM Extraction (Playwright)

```python
# Get all profile photo URLs (full-res only)
photo_urls = page.evaluate("""() => {
    return Array.from(document.querySelectorAll('img'))
        .map(i => i.src)
        .filter(s => s.includes('ecdn2') && s.includes('size=453x1536'));
}""")

# Get ALL images (includes badges, icons — filter by size)
all_imgs = page.evaluate("""() => {
    return Array.from(document.querySelectorAll('img'))
        .filter(i => i.naturalWidth > 200)
        .map(i => ({src: i.src, w: i.naturalWidth, h: i.naturalHeight, alt: i.alt}));
}""")
```

## Profile Data Selectors

| Data | Selector | Notes |
|------|----------|-------|
| Name | `.contact__name-text` or profile heading | First name only |
| Age | In profile heading | Combined with name |
| Bio | `.about__text` or profile text block | May be empty |
| Basics | `.badge__label` elements | Height, education, etc. |
| Prompts | `.prompt` or `.profile-prompt` | Question + answer pairs |
| Spotify | `.spotify-artists` or similar | Top artists list |
| Location | Location text below profile | City + distance |
| Instagram | Link or text in profile | Handle only |

## Conversation History Extraction

```python
# Get all messages in a conversation
body_text = page.query_selector('body').inner_text()
# Messages appear as date headers + text blocks
# Format: "DD Month YYYY\nMessage text\n..."
```

## Sidebar Navigation

```python
# Click a specific conversation by name
entry = page.locator('[class*="contact"]').filter(has_text="TargetName").first
entry.click(force=True)  # force=True needed — overlay intercepts pointer events

# Or use JS click (more reliable)
page.evaluate("""(name) => {
    const items = document.querySelectorAll('.contact');
    for (const item of items) {
        if (item.textContent.includes(name)) { item.click(); break; }
    }
}""", target_name)
```

## Camoufox vs Brave for Bumble

**Camoufox**: FAILS — SPA bundles load but JS never executes. `window.Bumble` stays `undefined`.
**Brave in Webtop**: WORKS — real Chromium engine, JS executes correctly.

Launch Brave:
```bash
docker exec -d webtop bash -c \
  "DISPLAY=:1 brave-browser --no-first-run --no-sandbox --disable-default-apps \
   --remote-debugging-port=9224 --user-data-dir=/config/.config/brave-persistent \
   'https://bumble.com/app' > /tmp/brave-bumble.log 2>&1"
```

Inject cookies via Playwright CDP:
```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9224")
context = browser.contexts[0]
context.add_cookies(cookies)
page = context.pages[0]
page.goto("https://bumble.com/app", wait_until="domcontentloaded", timeout=30000)
```

## Tailscale Exit Node for Residential IP

Some dating sites check IP reputation. Route through Mac's residential IP:

```bash
tailscale set --exit-node=100.127.150.1  # Mac
curl -s ifconfig.me  # Verify: should show Mac's IP, not VPS
# Deactivate after: tailscale set --exit-node=""
```
