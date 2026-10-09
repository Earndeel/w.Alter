# Bumble — Webtop Browsing Notes

## Auth: Cookie Extract + Brave in Webtop (NOT Camoufox)

Camoufox **cannot run Bumble's SPA**. The JS bundles (manifest, vendor, main from `us1.ecdn2.bumbcdn.com`) load with HTTP 200 but never execute — `window.Bumble` and `React` remain `undefined`, page stuck on `.app-loading` div indefinitely. This is caused by Camoufox's anti-detection fingerprint breaking the JS runtime.

**Working path**: Brave in Webtop container.

```bash
# Launch Brave
docker exec -d webtop bash -c "DISPLAY=:1 brave-browser --no-first-run --no-sandbox --disable-default-apps --remote-debugging-port=9224 --user-data-dir=/config/.config/brave-persistent 'https://bumble.com' > /tmp/brave-bumble.log 2>&1"

# Wait for CDP
sleep 6 && docker exec webtop bash -c "curl -s http://localhost:9224/json/version"
```

Cookie injection via Playwright CDP (`http://localhost:9224`), same as other services.

## Cookie Domains

Bumble uses these cookie domains:
- `.bumble.com` (main — session, device_id, aid, HDR-X-User-id, etc.)
- `bumble.com` (cookie_banner_closed)
- `us1.bumble.com` (cookie_banner_closed)

Key auth cookies: `session` (httponly, secure), `HDR-X-User-id`, `aid`, `device_id`.

SQL filter: `host_key LIKE '%bumble%'`

## Bumble SPA Navigation

### Conversation Click

Bumble conversation entries in the sidebar are `div.contact` elements with an `onclick` handler. Child elements (`contact__name-text`, `contact__info`) do NOT have click handlers.

**Wrong**: Clicking `.contact__name-text` or using broad selectors like `[class*="contact"]` (matches the entire list container, which has a huge bounding box).

**Correct approach**:
```python
# JS click on the specific contact div
page.evaluate("""() => {
    const items = document.querySelectorAll('.contact');
    for (const item of items) {
        if (item.textContent.includes('TARGET_NAME')) {
            item.click();
            break;
        }
    }
}""")
```

**Coordinate click gotcha**: If using `page.mouse.click(x, y)`, target the specific `.contact__name-text` element, NOT the `.contact` container (which spans the full sidebar height ~1000px, making the center point land on the wrong conversation).

### Overlay Interception

`sidebar-extra__actions` div intercepts pointer events over the conversation list. Use `force=True` with Playwright locator clicks, or use JS `element.click()` to bypass.

### URL Pattern

After clicking a conversation, the URL becomes `https://bumble.com/app/connections`. The main area shows the person's profile + chat messages.

### Profile Data Available in Chat View

When a conversation is open, the main area shows:
- Full name, age
- Job title + company
- Bio / About section
- Height, exercise, education, drinking, smoking
- Gender, looking for, kids, star sign, politics, religion
- Location + distance
- Spotify top artists
- Profile prompts (e.g., "After work you can find me", "My personal hell is", "My morning routine looks like")

### Message History

Messages are displayed chronologically in the main area with dates. The sidebar shows the last message preview per conversation.

## Tailscale Exit Node

Bumble may require residential IP. Activate Tailscale exit node to Mac:
```bash
tailscale set --exit-node=100.127.150.1
# Verify: curl -s ifconfig.me → should show Mac's IP (e.g. 124.122.129.22)
```
