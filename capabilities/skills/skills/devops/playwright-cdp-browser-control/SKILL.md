---
name: playwright-cdp-browser-control
category: devops
description: Control a real Chromium browser via Playwright CDP through the webtop Docker container. Full click/type/navigate/screenshot capabilities. Use when native browser tools fail or when you need cookie persistence.
metadata:
  hermes:
    fallback_for_tools: [computer_use]
---

# Playwright CDP Browser Control

Interactive browser control via Playwright connecting to Chromium running inside the webtop Docker container over CDP.

## When to Use (priority order)

1. **Native browser tools** (`browser_navigate`, `browser_click`) — try first, they're faster
2. **Playwright CDP** (this skill) — when native tools fail, or you need persistent cookies/sessions
3. **Scrapling stealthy_fetch** — last resort, fetch-only, no interaction

## Architecture

```
[terminal python3] → Playwright → CDP (port 9223) → socat → Chromium (port 9222) → webtop container
```

## Startup

```bash
bash ~/.hermes/scripts/start-chromium-cdp.sh
```

Verify:
```bash
CONTAINER_IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' webtop)
curl -s "http://${CONTAINER_IP}:9223/json/version" | python3 -c "import sys,json;print(json.load(sys.stdin)['Browser'])"
```

## Python Template (via terminal tool, NOT execute_code)

```python
from playwright.sync_api import sync_playwright
import time

pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://172.17.0.3:9223")
context = browser.contexts[0]
page = context.pages[0] if context.pages else context.new_page()
page.set_viewport_size({"width": 1920, "height": 1080})

page.goto("https://example.com", wait_until="domcontentloaded", timeout=30000)
time.sleep(2)

# Interact here...

page.screenshot(path="/tmp/result.png")
pw.stop()
```

## Form Filling Patterns

### Standard (works most of the time)
```python
page.fill('input[type=email]', 'user@example.com')
page.fill('input[type=password]', 'secret')
page.click('button[type=submit]')
```

### React/SPA forms (when standard fill doesn't trigger validation)
```python
page.evaluate("""(email, pass) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    const inputs = document.querySelectorAll('input[type="text"], input[type="password"]');
    setter.call(inputs[0], email);
    inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
    inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
    setter.call(inputs[1], pass);
    inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
    inputs[1].dispatchEvent(new Event('change', { bubbles: true }));
}""", email, password)
```

### Checkboxes outside viewport
```python
# JS click is more reliable than Playwright click for offscreen checkboxes
page.evaluate("document.querySelector('input[type=checkbox]').click()")
```

### Submit buttons outside viewport
```python
page.evaluate("""() => {
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Submit'));
    if (btn) { btn.scrollIntoView(); btn.click(); }
}""")
```

## Discovery Patterns

### Find all form fields
```python
inputs = page.query_selector_all("input, button, a")
for el in inputs:
    tag = el.evaluate("el => el.tagName")
    itype = el.get_attribute("type") or ""
    name = el.get_attribute("name") or ""
    text = el.inner_text()[:60] if tag in ["BUTTON", "A"] else ""
    print(f"  {tag}: type={itype} name={name} text='{text}'")
```

### Find CAPTCHA
```python
captcha = page.evaluate("""() => {
    const iframes = document.querySelectorAll('iframe');
    return Array.from(iframes).filter(i =>
        (i.src||'').match(/captcha|recaptcha|hcaptcha|turnstile/)
    ).map(i => i.src.substring(0, 80));
}""")
```

### Get page text for analysis
```python
body = page.inner_text("body")
for line in body.split("\n"):
    line = line.strip()
    if line and any(kw in line.lower() for kw in ["error", "success", "invalid"]):
        print(f"  {line}")
```

## Account Creation Workflow

When creating accounts on websites:
1. Fill form via Playwright CDP
2. If reCAPTCHA blocks → inform user, offer manual creation
3. Generate password: `"Svc-" + secrets.token_urlsafe(16) + "!9"`
4. Save credentials to Bitwarden immediately:
```bash
export BW_SESSION=$(bw unlock --passwordenv BW_MASTER_PW --raw)
bw get template item | python3 -c "
import sys,json
t=json.load(sys.stdin)
t['name']='ServiceName'
t['login']={'username':'email','password':'pass'}
t['uris']=[{'uri':'https://service.com'}]
print(json.dumps(t))
" | bw encode | bw create item
```

## CAPTCHA Solving

See `references/captcha-solving.md` for full details. Quick summary:
- **undetected-chromedriver + grecaptcha.execute()** — FREE, bypasses invisible reCAPTCHA (preferred)
- **capsolver.com** / **2captcha.com** — paid services, $1-3/1000 solves, reliable fallback
- **playwright-recaptcha** — free audio challenge, unreliable
- **Sitekey**: extract from `data-sitekey` attribute or iframe `k=` param
- **Injection**: set `g-recaptcha-response` textarea + trigger callback
- **Escape hatches**: undetected-chromedriver > API bypass > OAuth > paid solver > audio > ask user

## References

- `references/captcha-solving.md` — CAPTCHA solving services, libraries, injection patterns

## Pitfalls

- **Webtop CDP interaction findings** — viewport sizing, focus vs click, anti-bot status, stale page after navigation. See `references/webtop-cdp-interaction-findings.md` for tested patterns and what breaks.
- **NEVER clear ALL cookies** — `context.clear_cookies()` wipes EVERY domain (X, Google, xAI, etc.). The user gets logged out of everything and must manually re-login. Always target specific domains or delete specific cookies by name. This is the #1 CDP footgun.
- **execute_code doesn't have playwright** — always use `terminal` tool with `python3 << 'EOF'`
- **Container IP changes** — verify with `docker inspect` if connection fails
- **`page.fill()` doesn't trigger React state** — use `evaluate()` with `nativeInputValueSetter` + `dispatchEvent`
- **Elements outside viewport** — `el.click()` times out. Use `page.evaluate()` with `scrollIntoView()` or direct JS click.
- **Google OAuth via CDP** — After logging into Google in a persistent profile (via noVNC), connect via CDP to reuse the session. Use `page.evaluate("fetch(...)")` to call authenticated APIs. Do NOT start a new browser instance — it won't have the session cookies.
- **Vast.ai authenticated API** — Use `page.evaluate("async () => { const r = await fetch('/api/v0/auth/apikeys/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:'...'})}); return r.json(); }")` from a Vast.ai page to create API keys. Cookie-based auth works only from within the page context.
- **60s terminal timeout** — wrap long scripts in `timeout 45 python3 << 'PYEOF'` to avoid hard kill
- **User data dir** — `/tmp/chro-cdp` = clean sessions. Real profile path = persistent cookies/logins.
- **Snap Chromium AppArmor restriction** — Snap Chromium CANNOT write user data dirs under `/root/` or `~/.hermes/`. Fails with `SingletonLock: Permission denied (13)`. Always use `/tmp/` for persistent profiles: `--user-data-dir=/tmp/chrome-google-profile`. Symlink to `~/.hermes/chrome-profiles/` for discoverability: `ln -sf /tmp/chrome-google-profile ~/.hermes/chrome-profiles/google-main`.
- **`context.clear_cookies()` nukes ALL domains** — Calling `context.clear_cookies()` wipes cookies for EVERY domain in that browser context (X, Google, xAI, everything). If you only need to fix one site's auth, use `page.evaluate("document.cookie.split(';').forEach(c => { document.cookie = c.trim().split('=')[0] + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=.' + location.hostname; })")` or navigate to the specific domain and clear only its cookies via the CDP protocol (`Network.deleteCookies`). Never broad-nuke cookies on a shared browser profile.
- **NEVER `context.clear_cookies()`** — this wipes ALL cookies across ALL domains, logging the user out of everything (X, Google, etc.). To clear cookies for one site, use `context.cookies(urls=[domain])` to inspect, then `context.clear_cookies(urls=[domain])` or `browser_context.clear_cookies(urls=[specific_url])`. If you must clear cookies, do it per-domain only.

- **SingletonLock cleanup** — After undetected-chromedriver or a crash, stale lock files block Chromium startup. Always clean before launching: `rm -rf /path/profile/Singleton*`. Check with `fuser /path/profile/SingletonLock` to detect live holders.
- **Chromium headless mode** — use `--headless=new` not `--headless` (deprecated)
- **reCAPTCHA invisible** — Don't try to find `#recaptcha-anchor` checkbox; invisible reCAPTCHA has no visible checkbox. Use `grecaptcha.execute()` via undetected-chromedriver to get a valid token, then submit it with the form.
- **MUI (Material UI) forms** — ActionChains `click().send_keys()` works better than `page.fill()` for MUI textfields. React state updates reliably with keyboard input simulation.
- **Login page 404** — Some SPAs (React/Next.js) don't have a `/login/` route. Login is via a modal triggered by a nav button. Check `body_text` for "Login" clickable elements instead of navigating to `/login/`.
- **409 on registration** — Means account already exists (email or username taken). Don't retry with same email; try different username or switch to password reset flow.
- **Stripe Elements (cross-origin iframes)** — Stripe Payment Element uses cross-origin iframes that resist programmatic fill. `type()` and `fill()` work momentarily but fields reset on blur/submit. `createPaymentMethod` requires Elements (PCI compliance). For adding payment methods to services: use Selkies desktop (`https://100.91.35.121:3001/`) for manual entry, or find the service's direct API endpoint to bypass Stripe UI entirely.
- **Selkies desktop exists** — Always check `https://100.91.35.121:3001/` first before building Xvfb+x11vnc+noVNC stacks. Selkies gives Lucas a shared visible desktop.

## Remote Mac Browser via SSH Tunnel (Brave/Chrome)

To control Brave or Chrome on a remote Mac from the VPS via Tailscale SSH + CDP port forwarding, see **`references/remote-mac-cdp-ssh-tunnel.md`**. Covers: quit-first requirement, binary path (not `open -a`), tunnel setup, Playwright connect, cleanup, and measured performance.

Key pitfall: **macOS ignores `--remote-debugging-port` if the browser is already running.** Must quit completely, then relaunch via the binary path directly. `open -a` silently drops args on already-running apps.

## OAuth Flows via CDP

When an OAuth provider needs browser interaction but the agent runs on a headless VPS, use CDP + reverse SSH tunnel. Full procedure: `references/oauth-via-cdp.md`.

## Connecting to Brave/Chrome on a Remote Mac via SSH Tunnel

When you need to control a browser running on the user's Mac (not the VPS):

### 1. Launch browser with CDP on Mac
```bash
# Must quit existing browser first (relaunch with flag doesn't work if already running)
ssh -i ~/.ssh/id_ed25519 user@mac 'osascript -e "tell application \"Brave Browser\" to quit"'
sleep 2
ssh -i ~/.ssh/id_ed25519 user@mac 'nohup "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --remote-debugging-port=9222 > /dev/null 2>&1 &'
```

**Pitfall:** If the browser was already running, `open -a "Brave Browser" --args --remote-debugging-port=9222` opens a new window but does NOT enable the debug port. You must quit completely and relaunch the binary directly.

### 2. Create SSH tunnel from VPS to Mac
```bash
ssh -f -N -L 9222:localhost:9222 -i ~/.ssh/id_ed25519 user@mac
```

### 3. Verify
```bash
curl -s http://localhost:9222/json/version
# → {"Browser": "Chrome/148.0.7778.167", ...}
```

### 4. Connect via Playwright
```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9222")
context = browser.contexts[0]
page = context.pages[0] if context.pages else context.new_page()
page.goto("https://example.com")
```

### CDP Performance (v0.14.0+)
The "180x faster" improvement in v0.14.0 means **CDP call overhead** (connection reuse), NOT page load speed. With persistent WebSocket: ~100-150ms per JS evaluation call vs ~2800ms when creating a new connection each time. Page load time is unchanged (network-bound).

### Browser-specific notes
- **Brave**: Chromium-based, full CDP support. Use same binary path pattern as Chrome.
- **Safari**: Does NOT support CDP. Cannot be controlled this way.
- **Firefox**: Has CDP support via `--remote-debugging-port` but Playwright's `connect_over_cdp` is optimized for Chromium.

## Persistent Chrome Profile (Google OAuth sessions)

For services using Google OAuth, use a persistent Chrome profile so the Google session survives across runs. Once logged into Google in the profile, all future "Continue with Google" flows are automatic.

```bash
# MUST be /tmp/ for Snap Chromium (AppArmor blocks /root/)
options.add_argument('--user-data-dir=/tmp/chrome-google-profile')
options.add_argument('--profile-directory=Default')
# Symlink for discoverability
ln -sf /tmp/chrome-google-profile ~/.hermes/chrome-profiles/google-main
```

**Full noVNC + tunnel stack** for initial Google login (see `webtop-chromium-session-persistence` skill):
```bash
Xvfb :99 -screen 0 1920x1080x24 &
DISPLAY=:99 chromium-browser --no-sandbox --user-data-dir=/tmp/chrome-google-profile --remote-debugging-port=9222 https://accounts.google.com/signin &
x11vnc -display :99 -forever -nopw -rfbport 5900 &
/usr/share/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 &
cloudflared tunnel --url http://localhost:6080  # exposes noVNC via HTTPS
```
User opens the tunnel URL, logs into Google once, session persists forever.

**Startup script**: `~/.hermes/scripts/start-chrome-google.sh` — launches Chromium with persistent profile + CDP for Lucas to do initial Google login.

**Webtop container**: The `svc-chromium` s6 service may be broken (`unable to read svc-chromium/type`). If so, start Xvfb + Chromium manually or use host-side undetected-chromedriver with `--user-data-dir` instead.

## undetected-chromedriver (reCAPTCHA bypass)

For reCAPTCHA-heavy sites where Playwright CDP fails, use `undetected_chromedriver` which patches ChromeDriver to avoid bot detection.

```bash
pip install undetected-chromedriver selenium
apt-get install -y chromium-chromedriver  # ARM64 compatible
```

```python
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

options = uc.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--headless=new')
options.binary_location = '/usr/bin/chromium-browser'

driver = uc.Chrome(
    options=options,
    browser_executable_path='/usr/bin/chromium-browser',
    driver_executable_path='/usr/bin/chromedriver'  # ARM64 from apt
)

# Get valid reCAPTCHA token (works for invisible reCAPTCHA)
driver.get("https://target-site.com/register/")
time.sleep(10)
token = driver.execute_script("""
    return new Promise((resolve) => {
        grecaptcha.ready(function() {
            grecaptcha.execute('SITEKEY_HERE', {action: 'register'}).then(resolve);
        });
    });
""")
# Token can be submitted via API or injected into form

# Fill MUI/React forms with ActionChains
inputs = [i for i in driver.find_elements(By.CSS_SELECTOR, "input") if i.is_displayed()]
actions = ActionChains(driver)
actions.move_to_element(inputs[0]).click().send_keys("user@email.com").perform()
time.sleep(0.3)
actions.move_to_element(inputs[1]).click().send_keys("password").perform()

# Intercept network requests to find API endpoints
driver.execute_cdp_cmd('Network.enable', {})
driver.get_log('performance')  # Clear
# ... submit form ...
logs = driver.get_log('performance')
for entry in logs:
    msg = json.loads(entry['message'])
    if msg['message']['method'] == 'Network.requestWillBeSent':
        req = msg['message']['params']['request']
        if req.get('method') == 'POST':
            print(f"POST {req['url']}")
            print(f"Body: {req.get('postData', '')[:500]}")
```

**Key insight**: `grecaptcha.execute()` runs client-side and returns a valid token without showing any challenge. Works because undetected-chromedriver avoids the headless detection that normally prevents reCAPTCHA from loading.
