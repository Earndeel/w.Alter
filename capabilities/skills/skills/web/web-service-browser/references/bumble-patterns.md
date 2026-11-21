# Bumble Web Patterns (tested 2026-06-02)

## Cookie Injection
- Cookies required: `session`, `aid`, `device_id`, `HDR-X-User-id`, `buzz_lang_code`, `has_secure_session`, `session_cookie_name`
- Domain: `.bumble.com` (all cookies)
- `session` cookie is httpOnly — not visible in `document.cookie` but sent with requests
- Bumble SPA JS bundles **do NOT execute in Camoufox** — the page stays on `app-loading` forever. Use **Brave in Webtop** (port 9224) instead.

## Brave in Webtop (Working Path)
```bash
# Launch Brave
docker exec -d webtop bash -c "DISPLAY=:1 brave-browser --no-first-run --no-sandbox --disable-default-apps --remote-debugging-port=9224 --user-data-dir=/config/.config/brave-persistent 'https://bumble.com' > /tmp/brave-bumble.log 2>&1"

# Inject cookies via Playwright CDP
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9224")
context = browser.contexts[0]
context.add_cookies(cookies)
page = context.pages[0]
page.goto("https://bumble.com/app", wait_until="domcontentloaded", timeout=30000)
```

## DOM Structure
- Sidebar conversations: `.contact` divs inside `.sidebar__contact-list`
- Name element: `.contact__name-text` (child of `.contact__info`)
- Message preview: sibling of `.contact__name`
- "Your move" indicator: appears when woman messaged last, waiting for man to respond
- Chat area: opens in main panel when clicking a `.contact` div
- Profile panel: right side, scrollable, contains photos + bio + basics
- Page class: `.page.page--chat`
- Messages header: `.messages-header`
- Messages list: `.messages-list`
- Message bubbles: `.message--in` (received), `.message--out` (sent)
- Message text: `.message-bubble__text`
- Expiration notice: `.messages-notice.expiration-status-average`

## Chat Input (Message Sending)
```python
# Textarea for typing messages
textarea = page.query_selector('.message-field textarea.textarea__input')
# Send button
send_btn = page.query_selector('button.message-field__send')

# ALTERNATIVE: coordinates-based click (more reliable)
# Textarea at approximately (441, 1036) — 1018x24
# Send button at approximately (1555, 1029) — 38x38
page.mouse.click(550, 1048)  # click textarea
page.keyboard.type(message_text, delay=30)
time.sleep(0.5)
page.mouse.click(1574, 1048)  # click send
```

**Pitfall**: `page.get_by_text()` and standard selectors may not find the textarea. Use coordinate-based click as fallback. Always verify the message appears in the chat body after sending.

## Click Selector (IMPORTANT)
```javascript
// CORRECT — coordinates on .contact__name-text bounding box
const names = document.querySelectorAll('.contact__name-text');
for (const name of names) {
    if (name.textContent.trim() === 'TargetName') {
        const rect = name.getBoundingClientRect();
        // Click at rect.x + rect.width/2, rect.y + rect.height/2
    }
}

// WRONG — page.get_by_text hits the container which intercepts clicks
// WRONG — page.locator('[class*="contact"]').filter(has_text="Name") resolves to the list container
```

## Profile Photos — SCREENSHOTS ONLY
- Photos are in `.profile__entry img` and `.scroll__inner img`
- **NEVER modify CDN URL `size=` parameter** — Bumble CDN returns WRONG/different images when the size is changed. A `size=600x900` request may return a completely different person's photo (tested: golf player instead of the actual woman).
- **Correct method**: Take screenshots of the visible profile panel, then scroll the right panel and take more screenshots.
- Profile panel is at x>1400 in the page layout (right side).
- Scroll the profile panel with JS:
```python
page.evaluate("""() => {
    const scrollContainers = document.querySelectorAll('[class*="scroll"]');
    for (const sc of scrollContainers) {
        if (sc.scrollHeight > sc.clientHeight && sc.querySelector('img[src*="ecdn2"]')) {
            sc.scrollTop = N;  // 0, 400, 800, 1200, 1600, 2000
        }
    }
}""")
page.screenshot(path=f"/tmp/profile-scroll-{N}.png")
```
- `vision_analyze` each screenshot for OSINT + psychological analysis.
- 21 photos in DOM = profile with multiple images (may include friend photos, not all are the person).

## Conversation Timestamps
- Bumble shows relative timestamps: "37 minutes ago", "yesterday", "13 hours ago", "26 May 2026"
- Sidebar order = most recent activity first (not necessarily most recent incoming message)
- "Conversation expires in N hours" = woman messaged, man hasn't responded yet
- "Your move" = woman messaged last
- Must click into conversations to compare timestamps — do NOT assume top of sidebar = most recent incoming message
- **CRITICAL: Convert relative timestamps to user's timezone.** "10 hours ago" at 06:48 UTC = sent at 20:48 UTC = 03:48 Bangkok (UTC+7). Always add the offset. Getting this wrong creates false narratives (e.g. "she was drunk at 3am" when she actually sent it at a reasonable hour in her timezone). (Error from 2026-06-03 session.)

## Instagram from Bumble Bio
- Bio may contain IG handle (e.g. "IG : sunn.f")
- Navigate to `https://www.instagram.com/{handle}/` in Camoufox
- Public profiles show: full name, posts count, followers, following, bio, location
- Private profiles show: name, counts, "This profile is private" — still valuable OSINT
- Close tab after extraction: `DELETE /tabs/{tabId}?userId=walter`

## Tailscale Exit Node
- Required for Cloudflare-protected features
- `tailscale set --exit-node=100.127.150.1` → routes through Mac's residential IP
- Verify: `curl -s ifconfig.me` should show Mac's IP, not VPS IP
- Container inherits host routing automatically

## Dating Message Style (User Preference)
- **3 propositions systématiques** pour chaque réponse
- **Langue de la conversation** (si elle écrit en anglais → anglais)
- **Style** : sexy, drôle, provoquant, mais pertinent (profil + contexte)
- **Pas orienté "rencontre physique" directe** — teasing, pas pression
- **Courts** — max 2 parties courtes
- **Pas toujours d'emoji** — varier
- **Jamais de répétition** entre les 3 options (structures et mots différents)
- **Timestamps** : TOUJOURS recalculer en UTC+7 (Bangkok), jamais UTC brut
- Examples of preferred style:
  - "Sober you has 'no drama' in her bio but drunk you is out here asking about French kisses… which one should I trust?"
  - "The girl who matched me out of boredom now wants to know what a French kiss feels like? Sounds like I'm upgrading from backup plan to main event"
  - NOT: "Hey! Would you like to grab a drink this week?" (too direct/transactional)
  - NOT: every message ending with 😏 (don't overuse emojis)
