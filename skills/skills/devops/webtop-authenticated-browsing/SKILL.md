---
name: webtop-authenticated-browsing
description: "Authenticated browsing via Camoufox or Webtop Chromium with Mac Brave cookies. Cookie extraction, injection, anti-detect navigation, screenshots, click/scroll/keyboard interaction."
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [browser, cdp, cookies, auth, camoufox, webtop, brave, mac, anti-detect]
    related_skills: [hermes-camoufox-setup, playwright-cdp-browser-control]
---

# Webtop Authenticated Browsing

Browse sites where Lucas is logged in on Mac Brave, using anti-detect Camoufox or Webtop Chromium with injected cookies. Covers the full pipeline: extract → inject → navigate → interact → screenshot.

## When to Use

- Need to browse a site where Lucas has an active session on Mac Brave
- Scrapling/headless tools get blocked by anti-bot (Facebook, Cloudflare, etc.)
- Need screenshots + click/scroll/keyboard interaction on authenticated pages
- Need human-like browsing behavior (not API calls)

## Architecture

```
Mac Brave (CDP:9222) ──SSH──→ Cookies ──inject──→ Camoufox host (port 9377, headless Xvfb)
                                              └──→ Camoufox-in-Webtop (port 9378, Selkies-visible)
                                              └──→ Webtop Chromium (CDP:9223, fallback)
                                                        ↓
                                                  Screenshots + Click/Scroll/Type
```

## Decision Tree

```
Need authenticated browsing?
  ├─ Cloudflare-protected site?
  │    └─ Camoufox + auth-only cookies (NOT cf_clearance). Let Camoufox get its own cf_clearance.
  ├─ Anti-bot site (FB, DataDome)?
  │    ├─ User needs to SEE the browser? → Camoufox-in-Webtop (visible, Selkies)
  │    └─ Agent-only interaction? → Camoufox host (headless Xvfb, programmatic)
  ├─ Normal site, need auth?
  │    └─ Camoufox + auth cookies (fastest path)
  ├─ User says "ouvre le moi" / wants to SEE it?
  │    ├─ Open directly on Mac Brave: `ssh mac "open -a 'Brave Browser' '<url>'"`
  │    └─ If Mac not available → Camoufox-in-Webtop (visible on Selkies HTTPS:3001)
  ├─ Just need API token?
  │    └─ Extract token → vault → curl
  └─ Need real Mac browser fingerprint (DataDome strict)?
       └─ brave-walter CDP 9226 (real macOS fingerprint, SSH tunnel)
```

**Key rule**: When Monsieur says "ouvre le moi" — open it on his Mac Brave via SSH immediately. Don't suggest Webtop URLs or give instructions. Just do it.

**NEVER use Mac Brave CDP directly** — it opens visible tabs/pop-ups on Monsieur's screen.

**NEVER inject cf_clearance across browsers** — Cloudflare binds it to the fingerprint. Always inject auth-only cookies and let the target browser get its own cf_clearance.

## Variant: Visible Camoufox in Webtop (noVNC)

When the user wants to watch the browsing live on the Webtop desktop (noVNC on port 3100), run Camoufox **inside the Webtop container** instead of on the host's headless Xvfb. The container already has Chromium; Camoufox installs alongside it.

### Setup (one-time per container)

```bash
# Install camoufox Python package in container
docker exec webtop bash -c "pip3 install camoufox"

# Fetch browser binaries (Firefox-based, ~200MB)
docker exec webtop bash -c "python3 -m camoufox fetch"
# → "Camoufox binaries up to date! Current version: v135.0.1-beta.24"
```

### Launch visible browser with cookies

```bash
# Copy cookies into container
docker cp /tmp/google-cookies.json webtop:/tmp/google-cookies.json

# Write launch script
cat > /tmp/launch-camoufox-webtop.py << 'PYEOF'
import json, time, sys
from camoufox.sync_api import Camoufox

cookies_path = "/tmp/google-cookies.json"
target_url = "https://labs.google/fx/fr/tools/flow"

with open(cookies_path) as f:
    cookies = json.load(f)

print(f"Loaded {len(cookies)} cookies")

with Camoufox(headless=False, humanize=True) as browser:
    page = browser.new_page()
    page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    context = browser.contexts[0]
    context.add_cookies(cookies)
    print("Cookies injected")
    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    print(f"Page loaded: {page.title()}")
    sys.stdout.flush()
    while True:
        time.sleep(60)  # Keep alive
PYEOF

docker cp /tmp/launch-camoufox-webtop.py webtop:/tmp/launch-camoufox-webtop.py

# Launch with DISPLAY=:1 (Webtop's desktop display)
docker exec -e DISPLAY=:1 -d webtop bash -c \
  "DISPLAY=:1 python3 /tmp/launch-camoufox-webtop.py > /tmp/camoufox.log 2>&1"
```

### Verify

```bash
# Check it's running
docker exec webtop bash -c "cat /tmp/camoufox.log"
# Expected: "Loaded N cookies" → "Cookies injected" → "Page loaded: <title>"

docker exec webtop bash -c "ps aux | grep camoufox-bin | grep -v grep"
```

The browser is now visible on the Webtop desktop at `http://<host>:3100`.

### Key difference from host Camoufox

| Aspect | Host Camoufox (Xvfb) | Webtop CamounoVNC |
|---|---|---|
| Visibility | None (headless virtual) | Full desktop via noVNC |
| Control | HTTP API (localhost:9377) | Direct interaction OR Playwright |
| Use case | Agent programmatic | User watching / co-browsing |
| Cookies | API injection | Playwright `add_cookies()` |
| DISPLAY | :116 (Xvfb) | :1 (Webtop KDE/XFCE) |

## Step 1: Extract Cookies from Mac Brave

**Preferred: Keychain decryption** (works when main Brave has no CDP — which is the normal case).

```python
import hashlib, json, subprocess
from Crypto.Cipher import AES

# 1. Copy cookies DB from Mac
subprocess.run(["ssh", "mac", "cp ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies-main.db"], check=True)

# 2. Export encrypted cookies for target domain
result = subprocess.run(["ssh", "mac", 'sqlite3 /tmp/brave-cookies-main.db "SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies WHERE host_key LIKE \'%target_domain%\'"'], capture_output=True, text=True)

# 3. Get Keychain key from vault
key = subprocess.run(["vault", "get", "macos/brave_keychain_key"], capture_output=True, text=True).stdout.strip().encode()
derived_key = hashlib.pbkdf2_hmac('sha1', key, b'saltysalt', 1003, dklen=16)

def decrypt(hex_str):
    enc = bytes.fromhex(hex_str)
    if enc[:3] == b'v10': enc = enc[3:]
    elif enc[:4] == b'v11': enc = enc[4:]
    iv, data = enc[:16], enc[16:]
    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
    dec = cipher.decrypt(data)
    pad = dec[-1]
    if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]): dec = dec[:-pad]
    clean = dec[16:] if len(dec) > 16 else dec
    return bytes(b for b in clean if 32 <= b <= 126).decode('ascii', errors='replace')

# 4. Decrypt and convert to Playwright format
cookies = []
for line in result.stdout.strip().split('\n'):
    parts = line.split('|')
    if len(parts) < 7: continue
    host, name, enc_hex, path, secure, httponly, expires = parts
    val = decrypt(enc_hex)
    c = {"name": name, "value": val, "domain": host, "path": path, "secure": secure=='1', "httpOnly": httponly=='1'}
    if expires and int(expires) > 0: c["expires"] = (int(expires)/1000000) - 11644473600
    cookies.append(c)

# 5. Save ALL cookies and AUTH-ONLY cookies separately
with open("/tmp/brave-cookies-all.json", "w") as f: json.dump(cookies, f)

# Filter auth cookies (exclude Cloudflare, analytics)
EXCLUDE = {'cf_clearance', '__cf_bm', '_cfuvid', '_ga', '_gcl_au'}
auth_cookies = [c for c in cookies if not any(c['name'].startswith(p) for p in ['_ga', '_gcl', '_cf', '__cf']) and c['name'] not in EXCLUDE]
with open("/tmp/brave-auth-cookies.json", "w") as f: json.dump(auth_cookies, f)
```

**See**: `references/macos-cookie-decryption.md` for full decryption analysis and Keychain access methods.
**See**: `references/northwest-registered-agent.md` for NWRA-specific Keycloak auth flow, SPA behavior, and document download patterns.

**Fallback: CDP extraction** (only when main Brave has `--remote-debugging-port` enabled — rare):

```python
import asyncio, json, subprocess, time, http.client
proc = subprocess.Popen(["ssh", "-o", "StrictHostKeyChecking=no", "-L", "19222:localhost:9222", "-N", "mac"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
async def extract():
    import websockets
    conn = http.client.HTTPConnection("localhost", 19222)
    conn.request("GET", "/json/version")
    ws_url = json.loads(conn.getresponse().read())["webSocketDebuggerUrl"].replace("ws://localhost:9222", "ws://localhost:19222")
    async with websockets.connect(ws_url, max_size=50*1024*1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        return json.loads(await ws.recv())["result"]["cookies"]
cookies = asyncio.run(extract())
proc.terminate()
```

**localStorage tokens** (Tinder, etc.): attach to specific tab via `Target.attachToTarget` → `Runtime.evaluate("localStorage.getItem('key')")`.

## Step 2a: Camoufox Path (Anti-Bot Sites — including Cloudflare)

### Start Camoufox

```bash
cd /root/.hermes/hermes-agent/node_modules/@askjo/camofox-browser
NODE_ENV=development PORT=9377 node server.js &
```

**Critical**: `NODE_ENV=development` is REQUIRED for cookie import from loopback without API key.

### Inject Cookies

```python
import http.client, json

def cf(method, path, body=None):
    conn = http.client.HTTPConnection("localhost", 9377)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, json.dumps(body) if body else None, headers)
    resp = conn.getresponse()
    raw = resp.read()  # read ONCE — second read returns empty bytes
    return resp.status, json.loads(raw.decode()) if raw else {}
```

```python
# Inject per-domain (avoid 413 Payload Too Large — max 512KB)
google_cookies = [c for c in pw_cookies if "google" in c["domain"]]
status, result = cf("POST", "/sessions/walter/cookies", {"cookies": google_cookies})
# → {"ok": true, "userId": "walter", "count": 90}
```

### Navigate + Interact

```python
# Create tab
status, result = cf("POST", "/tabs", {
    "userId": "walter", "sessionKey": "fb-marketplace",
    "url": "https://www.facebook.com/marketplace"
})
tab_id = result["tabId"]

# Screenshot
conn = http.client.HTTPConnection("localhost", 9377)
conn.request("GET", f"/tabs/{tab_id}/screenshot?userId=walter&sessionKey=fb-marketplace")
with open("/tmp/screenshot.png", "wb") as f:
    f.write(conn.getresponse().read())

# Snapshot (accessibility tree with [eN] refs)
status, snap = cf("GET", f"/tabs/{tab_id}/snapshot?userId=walter&sessionKey=fb-marketplace")

# Click by ref
cf("POST", f"/tabs/{tab_id}/click", {"userId": "walter", "sessionKey": "fb-marketplace", "ref": "e38"})

# Type
cf("POST", f"/tabs/{tab_id}/type", {"userId": "walter", "sessionKey": "fb-marketplace", "text": "pixel", "ref": "e10"})

# Press key
cf("POST", f"/tabs/{tab_id}/press", {"userId": "walter", "sessionKey": "fb-marketplace", "key": "Enter"})

# Scroll
cf("POST", f"/tabs/{tab_id}/scroll", {"userId": "walter", "sessionKey": "fb-marketplace", "direction": "down", "amount": 500})

# Navigate to new URL
cf("POST", f"/tabs/{tab_id}/navigate", {"userId": "walter", "sessionKey": "fb-marketplace", "url": "https://..."})
```

### Camoufox API Reference

For the full endpoint table, Python helper code, and interaction patterns, see `hermes-camoufox-setup` skill → `references/camoufox-api-reference.md`.

| Endpoint | Method | Body | Notes |
|---|---|---|---|
| `/health` | GET | — | `{"ok":true, "engine":"camoufox"}` |
| `/sessions/:uid/cookies` | POST | `{"cookies":[...]}` | Max 512KB, 500 cookies. Needs `NODE_ENV=development` |
| `/tabs` | POST | `{"userId","sessionKey","url"}` | Creates tab, optionally navigates |
| `/tabs/:id/navigate` | POST | `{"userId","sessionKey","url"}` | Navigate existing tab |
| `/tabs/:id/screenshot` | GET | query: `userId,sessionKey` | PNG binary |
| `/tabs/:id/snapshot` | GET | query: `userId,sessionKey` | Accessibility tree with `[eN]` refs |
| `/tabs/:id/click` | POST | `{userId, sessionKey, ref}` OR `{userId, sessionKey, selector}` | Click by `[eN]` ref from snapshot, OR by Playwright selector (e.g. `text=Document Name` for non-interactive elements like table rows) |
| `/tabs/:id/type` | POST | `{"userId","sessionKey","text","ref"}` | Type into element |
| `/tabs/:id/press` | POST | `{"userId","sessionKey","key"}` | Press keyboard key |
| `/tabs/:id/scroll` | POST | `{"userId","sessionKey","direction","amount"}` | Scroll page |

## Step 2b: Webtop Chromium Path (Fallback)

For sites without anti-bot (most sites except FB/Google/Cloudflare strict).

```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://172.17.0.3:9223")

# IMPORTANT: use existing context, NOT browser.new_context() — causes TargetClosedError
context = browser.contexts[0]
context.add_cookies([c for c in pw_cookies if ".example.com" in c["domain"]])

page = context.pages[0] if context.pages else context.new_page()
page.set_viewport_size({"width": 1920, "height": 1080})
page.goto("https://example.com", wait_until="domcontentloaded", timeout=15000)
page.screenshot(path="/tmp/screenshot.png")

# Interactions
element = page.query_selector('input[name="q"]')
element.focus()
page.keyboard.type("search term", delay=30)
page.keyboard.press("Enter")
page.evaluate("window.scrollBy(0, 500)")
page.mouse.click(x, y)  # coordinate-based click
```

### Webtop Chromium CDP Notes
- Container IP: `172.17.0.3`, CDP via socat: port `9223` → `9222`
- `page.set_viewport_size()` BEFORE `page.goto()` — causes page close if done after
- `focus()` > `click()` for input fields (more reliable via CDP)
- After navigation, page object may become stale — re-query from context
- **Anti-bot**: Facebook closes page, Google shows CAPTCHA. Use Camoufox instead.

## Step 2c: Camoufox-in-Webtop (Visual Browsing on Selkies)

When Monsieur wants to **see** the browser live on the Selkies desktop (port 3001), run Camoufox inside the Webtop container. Camoufox creates its own Xvfb display (:103) for anti-detection, then x11vnc + noVNC bridges it onto display :1 (Selkies).

### Architecture

```
Webtop container (display :1, Selkies)
  └─ Chromium window: noVNC client → localhost:6080
       └─ websockify → x11vnc:5901 → Camoufox Xvfb :103
            └─ Camoufox Firefox (anti-detect, cookies injected)
```

### Setup (one-time per container restart)

```bash
# 1. Install Node.js (arm64 static binary)
docker exec webtop bash -c "curl -fsSL https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-arm64.tar.gz | tar -xz -C /usr/local --strip-components=1"

# 2. Install camoufox Python package + fetch browser binary
docker exec webtop bash -c "pip3 install camoufox && python3 -m camoufox fetch"

# 3. Copy camoufox-browser server + install deps
docker cp /root/.hermes/hermes-agent/node_modules/@askjo/camofox-browser webtop:/tmp/camofox-browser
docker exec webtop bash -c "cd /tmp/camofox-browser && npm install express camoufox-js playwright-core"

# 4. Install x11vnc + websockify + noVNC
docker exec webtop bash -c "apt-get update -qq && apt-get install -y -qq x11vnc novnc && pip3 install websockify"
```

### Launch Sequence (each session)

```bash
# 1. Start Camoufox in Webtop (creates Xvfb :N automatically)
docker exec -d webtop bash -c "cd /tmp/camofox-browser && DISPLAY=:1 NODE_ENV=development PORT=9378 nohup node server.js > /tmp/camoufox.log 2>&1 &"

# 2. Wait for "camoufox launched" in log
docker exec webtop bash -c "cat /tmp/camoufox.log | tail -5"
# Look for: "xvfb virtual display started", display: ":103"

# 3. Start x11vnc to mirror Camoufox's virtual display
docker exec -d webtop bash -c "x11vnc -display :103 -nopw -forever -shared -rfbport 5901 -ncache 0 -xdamage -o /tmp/x11vnc.log 2>&1 &"

# 4. Start noVNC websocket proxy
docker exec -d webtop bash -c "websockify --web /usr/share/novnc 6080 localhost:5901 > /tmp/websockify.log 2>&1 &"

# 5. Open noVNC in Webtop's Chromium (appears on Selkies desktop)
docker exec -d webtop bash -c "DISPLAY=:1 chromium --no-sandbox --new-window 'http://localhost:6080/vnc.html?autoconnect=true&resize=scale' &"
```

### Cookie Injection + Navigation (via container-internal Python)

```python
# Inject cookies (use docker exec + python3 inside container)
inject_cmd = '''
python3 -c "
import http.client, json
with open('/tmp/google-cookies.json') as f:
    cookies = json.load(f)
conn = http.client.HTTPConnection('localhost', 9378)
body = json.dumps({'cookies': cookies})
conn.request('POST', '/sessions/walter/cookies', body, {'Content-Type': 'application/json'})
resp = conn.getresponse()
print(resp.read().decode())
"
'''
subprocess.run(["docker", "exec", "webtop", "bash", "-c", inject_cmd], ...)

# Navigate
nav_cmd = '''
python3 -c "
import http.client, json
conn = http.client.HTTPConnection('localhost', 9378)
body = json.dumps({'userId': 'walter', 'sessionKey': 'my-session', 'url': 'https://example.com'})
conn.request('POST', '/tabs', body, {'Content-Type': 'application/json'})
resp = conn.getresponse()
print(resp.read().decode())
"
'''
subprocess.run(["docker", "exec", "webtop", "bash", "-c", nav_cmd], ...)

# Screenshot (for remote analysis while user sees it live)
screenshot_cmd = '''
python3 -c "
import http.client
conn = http.client.HTTPConnection('localhost', 9378)
conn.request('GET', '/tabs/TAB_ID/screenshot?userId=walter&sessionKey=my-session')
with open('/tmp/camoufox-screenshot.png', 'wb') as f:
    f.write(conn.getresponse().read())
"
'''
subprocess.run(["docker", "exec", "webtop", "bash", "-c", screenshot_cmd], ...)
```

### Key Notes
- Camoufox **always creates its own Xvfb** (e.g. :103) — cannot force it to use :1 directly
- The virtual display number varies — check the log for the actual `:N`
- `NODE_ENV=development` required for cookie injection (same as host Camoufox)
- Port 9378 (not 9377) to avoid conflict with host Camoufox
- User interacts with the browser directly through Selkies/noVNC while W.Alter controls via API
- Cookie JSON must be inside the container (use `docker cp` or write via `docker exec`)

## Step 3: Screenshot + Analysis Pattern

```python
# At each interaction step, screenshot + vision_analyze
page.screenshot(path="/tmp/step-N.png")
# Use vision_analyze tool on /tmp/step-N.png to understand what's visible
# Use snapshot (accessibility tree) to find clickable refs
```

## Brave in Webtop Container

Brave is installed in the Webtop container alongside Chromium. Use it when the user wants a real browser window visible on the Selkies desktop.

### Launch Brave with cookies

```bash
# Start Brave (must use --no-sandbox since running as root)
docker exec -d webtop bash -c \
  "DISPLAY=:1 brave-browser --no-first-run --no-sandbox --disable-default-apps \
   --remote-debugging-port=9224 --user-data-dir=/config/.config/brave-persistent \
   'https://target-url.com' > /tmp/brave.log 2>&1"

# Wait for CDP to be ready
sleep 5
docker exec webtop bash -c "curl -s http://localhost:9224/json/version"
```

### Inject cookies via Playwright CDP

```python
# Write injection script, copy to container, execute
script = '''
import json, time
from playwright.sync_api import sync_playwright

with open("/tmp/google-cookies.json") as f:
    cookies = json.load(f)

pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9224")
context = browser.contexts[0]
context.add_cookies(cookies)
print(f"Injected {len(cookies)} cookies")

page = context.pages[0] if context.pages else context.new_page()
page.goto("https://target-url.com", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)
print(f"Title: {page.title()}")
pw.stop()
'''
# docker cp + docker exec to run
```

### CDP Ports

| Browser | Container Port | Host Port (socat) | Profile |
|---|---|---|---|
| Chromium | 9222 | 9223 | `/config/.config/chromium` |
| Brave | 9224 | 9225 | `/config/.config/brave-persistent` |

## Browser Persistence (Webtop Chromium)

### Critical: NEVER kill -9 Chromium
- `kill -9` destroys session cookies (HSID/SID/SSID)
- Always `SIGTERM` first, wait 30s, then `SIGKILL` as fallback
- Profile dir: `/config/.config/chromium/` (Docker volume, persists across restarts)

### Startup/Shutdown Scripts
Located at `/config/custom/` inside webtop container:
- `start-persistent-chromium.sh` — clean locks, launch with `--restore-last-session`
- `stop-chromium.sh` — graceful SIGTERM with timeout
- `chromium-watchdog.sh` — auto-restart every 15s check

### CDP Ports

| Browser | Container Port | Host Port (socat) | Profile |
|---|---|---|---|
| Chromium | 9222 | 9223 | `/config/.config/chromium` |
| Brave | 9224 | 9225 | `/config/.config/brave-persistent` |
| Camoufox (host) | N/A | 9377 | N/A (session-based) |
| Camoufox (webtop) | 9378 | N/A (use docker exec) | N/A (session-based) |

## Account-Risk Policy

- Prefer **Camoufox/browser navigation** over internal API calls
- Do NOT create cron polling jobs against unofficial APIs
- Do NOT send messages through internal APIs unless Monsieur accepts risk
- Read-only, one-shot checks only, on user request
- Tinder: `localStorage.getItem('TinderWeb/APIToken')`, API `api.gotinder.com`, no mass scraping

## Anti-Bot Stack

For strict sites, use the behavioral simulation and CAPTCHA solver modules:

```python
import sys
sys.path.insert(0, "/root/.hermes/scripts")
from human_sim import HumanSimulator
from captcha_solver import CaptchaSolver

# For Camoufox (Playwright direct, not HTTP API)
sim = HumanSimulator(page)
solver = CaptchaSolver(page, groq_api_key="gsk_...")

# Human behavior before interaction
sim.random_mouse_noise()
sim.idle_browse(3.0)

# Auto-solve challenges
await solver.auto_solve()

# Human-like interaction
sim.scroll_and_click('selector')
```

**Note**: HumanSimulator needs a Playwright page object. When using Camoufox HTTP API (port 9377), implement timing delays manually (time.sleep with random intervals).

See `anti-bot-navigation` skill for full decision tree.

## Parallelization Pattern

When the workflow requires both cookie extraction and browser setup, run them concurrently:

```python
# Background: cookie extraction from Mac
terminal("ssh mac 'cp ~/.../Cookies /tmp/cookies.db && sqlite3 /tmp/cookies.db ...' > /tmp/raw_cookies.txt && python3 decrypt.py", background=True, notify_on_complete=True)

# Background: Camoufox health check + cf_clearance
terminal("curl -s http://localhost:9377/health && curl -s -X POST http://localhost:9377/tabs -d '{\"url\":\"https://target.com\"}' && sleep 12 && curl -s http://localhost:9377/tabs/:id/snapshot", background=True, notify_on_complete=True)

# When both complete: inject auth cookies + navigate
```

This cuts total time by ~60% vs sequential execution (tested: 85s parallel vs 25min sequential with troubleshooting).

## Download URL Capture

When a site uses S3/CDN downloads triggered by button clicks, intercept the URL via Playwright's `expect_download`:

```python
with page.expect_download(timeout=15000) as dl_info:
    page.click('button:has-text("Download")')
dl = dl_info.value
s3_url = dl.url  # Pre-signed S3 URL, valid for hours/days
# curl directly to VPS instead of saving through remote browser
subprocess.run(["curl", "-sL", "-o", f"/tmp/{dl.suggested_filename}", dl.url])
```

This avoids the 0-byte file issue when Playwright tries to save downloads from a remote CDP browser (download happens on the remote machine, not locally).

## Site-Specific Tricks

### Google Flow (labs.google/fx/tools/flow)
- Auth via Google cookies (filter `pw_cookies` where `"google" in c["domain"]`)
- Credits: click the profile button (has "PRO" text), a dialog shows `<N> Crédits Flow` as a link
- The credits link goes to `one.google.com/ai/activity?utm_source=flow&utm_medium=web&utm_campaign=flow_ai_credits_page`
- "Changer de forfait" and "Gérer l'abonnement" links also in profile dialog
- Projects listed below the hero banner as links with edit/delete buttons
- Navigation is French-localized (bouton "Nouveau projet", "Changer de forfait", etc.)
- Session key: `google-flow`
- Works on both host Camoufox and Camoufox-in-Webtop

### Google Flow (labs.google/fx/tools/flow)
- Auth via Google cookies (filter `pw_cookies` where `"google" in c["domain"]`)
- Credits: click the profile button (has "PRO" text), dialog shows `<N> Crédits Flow` as a link
- Profile dialog also has: "Changer de forfait", "Gérer l'abonnement", "Se déconnecter"
- Projects listed below hero banner as links with edit/delete buttons
- French-localized: "Nouveau projet", "Changer de forfait"
- Session key: `google-flow`

### Facebook People Search

```
https://www.facebook.com/search/people/?q=<query>
https://www.facebook.com/search/groups/?q=<query>
```

Results appear as `article` elements with `link "Profile photo of <Name>" [eN]` refs. Use regex `r'link "Profile photo of (.+?)"'` to extract names from snapshot.

### Instagram Search

Instagram's `/explore/search/?q=<query>` URL shows the Explore page with reels, NOT search results. To search users:

1. Navigate to `https://www.instagram.com/`
2. Click the Search icon (`link "Search"`)
3. Find the `textbox "Search input"` ref in the snapshot
4. Type the query → wait 3s → snapshot shows user results as `link "<username>'s profile picture <username> <display_name>"` refs

### LinkedIn Cookie Expiry

LinkedIn session cookies (`JSESSIONID`, `bscookie`) expire much faster than Facebook/Instagram. If the Camoufox snapshot shows the login page ("S'identifier"), the session is dead — no workaround without fresh credentials.

### Facebook Marketplace — Direct URL with Filters

Skip the UI search form entirely. Marketplace accepts filter params in the URL:

```
https://www.facebook.com/marketplace/bangkok/search/?query=pixel&maxPrice=4000
https://www.facebook.com/marketplace/bangkok/search/?query=pixel&minPrice=1000&maxPrice=5000
```

Available params: `query`, `maxPrice`, `minPrice`, `category_id`, `sortBy` (e.g., `creation_time_descend`, `price_ascend`, `price_descend`).

This is faster and more reliable than trying to interact with the search form (the combobox "Search Marketplace" has no `[eN]` ref in Camoufox snapshots).

## Pitfalls

### Cookie Expires Format (Chrome Epoch)
Chrome/Brave stores cookie expires as **microseconds since 1601-01-01** (Chrome epoch).
Camoufox/Playwright expects **Unix seconds** or `-1` for session cookies.

**Conversion**:
```python
for c in cookies:
    exp = c.get("expires")
    if exp is not None and isinstance(exp, (int, float)):
        if exp > 0:
            c["expires"] = int((exp / 1000000) - 11644473600)
        else:
            del c["expires"]  # session cookie
```

Without conversion: `browserContext.addCookies: Cookie should have a valid expires`.

### Cloudflare Cookie Injection Rule

**NEVER inject `cf_clearance` from one browser into another.**

**Correct approach**: Inject ONLY auth cookies (session tokens, Keycloak, PHPSESSID), then let the target browser navigate to the site and obtain its OWN `cf_clearance` automatically. If the site still blocks, use `solve_cloudflare=True` on the target browser.

## Pitfalls

0. **NEVER connect Scrapling/Playwright to main Mac Brave CDP (port 9226)**: Opening a Scrapling session with `cdp_url=ws://localhost:9226` creates visible tabs and pop-ups on Monsieur's actual screen. This disturbs him and can cause misclicks. Use Camoufox (localhost:9377) or Webtop Chromium (localhost:9223) for all browsing. The Mac Brave CDP is ONLY for cookie extraction (Step 1) via raw `websockets` + `Storage.getCookies`, never for navigation.
1. **Camoufox click API — `selector` for non-interactive elements**: When a page element has no `[eN]` ref (e.g. table cell text, paragraph), use `{"selector": "text=Exact Text"}` in the click POST body instead of `{"ref": "eN"}`. Works for clicking table rows, links, and any text content. Example: `POST /tabs/:id/click` with `{"userId":"...", "sessionKey":"...", "selector":"text=Initial Resolution"}` navigates to that document's detail page.
2. **Camoufox package name**
0c. **cf_clearance is fingerprint-bound but Camoufox gets its OWN**: Never inject `cf_clearance` from Mac Brave into Camoufox — it won't work. But Camoufox navigates to CF-protected sites and obtains its own `cf_clearance` automatically. Inject only auth cookies (Keycloak, PHPSESSID, etc.). Tested 2026-05-24 on NWRA: Camoufox passed Cloudflare with zero challenge.
1. **Camoufox package name**: `@askjo/camofox-browser` (one 'u' in "camoufox"), server is `server.js` not `server-camoufox.js`
2. **Camoufox NODE_ENV**: Must be `development` for cookie import from loopback. Without it → 403
3. **Cookie payload limit**: 512KB max per request, 500 cookies max. Inject per-domain batches
4. **Refs reset after navigation**: Must re-snapshot before clicking in Camoufox
5. **`browser.new_context()` via CDP**: Causes `TargetClosedError` on webtop Chromium. Use `browser.contexts[0]`
6. **http.client double-read**: `resp.read()` consumes the buffer — calling it twice returns empty bytes. Always store result: `raw = resp.read(); return json.loads(raw.decode()) if raw else {}`. The `cf()` helper above already does this correctly.
7. **Docker iptables**: Container can't reach host SOCKS proxy (DROP rule). Run SSH SOCKS inside container instead
8. **Snap Chromium AppArmor**: Can't write under `/root/`. Use `/tmp/` for profiles on host
9. **SingletonLock**: Clean stale locks before launch: `rm -rf /path/profile/Singleton*`
10. **Google OAuth**: Blocks Playwright clicks. Manual login via Selkies (port 3001) required
11. **Locale spoofing**: Camoufox spoofs random geo — Google may show in Thai. Normal anti-detection
12. **Tailscale routing**: Mac exits via its own IP (124.120.206.170, Thai residential ISP). VPS Oracle = 129.150.52.60. Tailscale exit node routes VPS traffic through Mac's residential IP — Google sees a Thai ISP, not a datacenter. However, Google Lens still blocks from non-headless Camoufox (403 Forbidden) due to TLS/JS fingerprint detection.
13. **Tinder single tab**: Only one active tab allowed. Close duplicate, use original tab ID from `/json/list`
14. **Camoufox Xvfb is always virtual**: Camoufox creates its own Xvfb display (:N) — cannot use host display :1. Must bridge via x11vnc + noVNC for visual access on Selkies
15. **Node.js on arm64 Webtop**: `apt-get install nodejs` fails (broken packages). Use static binary: `curl -fsSL https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-arm64.tar.gz | tar -xz -C /usr/local --strip-components=1`
16. **Camoufox npm deps in Webtop**: `npm install` with no `node_modules/` dir times out. Install specific deps: `npm install express camoufox-js playwright-core`. Must also run `python3 -m camoufox fetch` for the browser binary (~700MB)
17. **docker exec + long-running processes**: `docker exec -d` for daemonized processes. Use `nohup ... &` inside the container for persistence. `docker exec` without `-d` blocks until process exits
18. **Webtop port conflicts**: Use port 9378 for Camoufox-in-Webtop (not 9377, which is host Camoufox)
19. **Selkies requires HTTPS**: Port 3100 (HTTP) shows "This application requires a secure connection (HTTPS)". Use `https://<host>:3001` instead. Current W.Alter server Tailscale endpoint: `https://100.91.35.121:3001`; local server endpoint: `https://127.0.0.1:3001`. Test: `curl -sk https://localhost:3001` returns 200. Opening on Mac: `ssh lucasjouvencon@100.127.150.1 "open -a 'Brave Browser' 'https://100.91.35.121:3001'"`
20. **Brave in Webtop needs --no-sandbox**: Running as root in container, must pass `--no-sandbox` or it crashes with "Running as root without --no-sandbox is not supported"
21. **Brave W.Alter instance has NO cookies**: The Brave instance on port 9226 uses `--user-data-dir=/tmp/brave-walter` — it's a separate profile with no Facebook/Instagram/LinkedIn sessions. Only the main Brave (no CDP, PID under `lucasjouvencon`) has real cookies. Use the SQLite fallback to extract them.
22. **macOS Keychain SSH access via osascript — UNRELIABLE (2026-05-24 confirmed)**: The `osascript ... with administrator privileges` approach for `find-generic-password` consistently fails with error 36 (errSecInteractionNotAllowed) when the keychain item has a restrictive ACL. Tested outcomes: `set-key-partition-list` runs successfully but does NOT fix the subsequent `find-generic-password` ACL. Error 44 (item not found) means the search list doesn't include `login.keychain-db`; error 36 means the ACL blocks non-interactive access. **Only reliable path**: user runs `security find-generic-password -s "Brave Safe Storage" -a "Brave" -w` directly in Terminal.app (local GUI session). Store result in vault as `macos/brave_keychain_key`. Do NOT spend 10+ attempts on osascript variants — try once, then ask the user after 2-3 failures. The user may push back ("find a way without asking me") but the Keychain ACL is a macOS security boundary, not a solvable technical limitation.
23. **First-block garble in decrypted cookies**: Skip first 16 bytes of AES-decrypted output. Domain-shared nonce block produces same garbled prefix for all cookies in a domain. Extract clean ASCII: `bytes(b for b in clean if 32 <= b <= 126).decode('ascii')`.
24. **Chrome epoch cookie expires**: The `expires_utc` column in Brave's SQLite Cookies DB uses Chrome epoch (microseconds since 1601-01-01). To convert to Unix seconds for Playwright: `unix_seconds = int((chrome_us / 1000000) - 11644473600)`. Negative or zero values mean session cookies (don't set `expires`). Playwright rejects any `expires` value that isn't -1 or a positive Unix timestamp in seconds — raw Chrome epoch values like `13424156971634321` cause `Cookie should have a valid expires` errors.

## Verification

- [ ] Camoufox health: `curl http://localhost:9377/health`
- [ ] Webtop CDP: `curl http://172.17.0.3:9223/json/version`
- [ ] Mac Brave CDP: `ssh lucasjouvencon@100.127.150.1 "curl -s http://localhost:9222/json/version"`
- [ ] Cookie injection: `POST /sessions/walter/cookies` → `{"ok": true}`
- [ ] Facebook auth: navigate to `/marketplace`, screenshot shows profile picture + logged-in UI

## Cookie Extraction Fallback (SQLite)

When Mac Brave has no `--remote-debugging-port` (main session never started with CDP), the Step 1 websocket approach fails. Fallback: read cookies directly from the SQLite DB on Mac.

```bash
# Copy Cookies DB from Brave profile
ssh lucasjouvencon@100.127.150.1 "cp ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies.db"

# Export encrypted cookie metadata (host, name, path, flags)
ssh lucasjouvencon@100.127.150.1 "sqlite3 /tmp/brave-cookies.db \"SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies\""
```

### Keychain Decryption Blocker

Cookie values are AES-128-CBC encrypted. The key is stored in macOS Keychain under `"Brave Safe Storage"` / account `"Brave"`. **The Keychain blocks non-GUI access via SSH** — `errSecInteractionNotAllowed` (-25308) even with correct password. This is an ACL on the specific item, not the keychain itself.

**Error codes decoded** (2026-05-24 tested):
- **Error 36** (errSecInteractionNotAllowed): ACL blocks non-interactive access. This is the persistent failure mode via SSH, even with `osascript ... with administrator privileges`. The `set-key-partition-list` workaround does NOT resolve this for Brave Safe Storage items.
- **Error 44** (errSecItemNotFound): The search list doesn't include `login.keychain-db`. Fix: `security list-keychains -d user -s ~/Library/Keychains/login.keychain-db /Library/Keychains/System.keychain` — but this only helps if error 36 is also resolved.

**Workaround options (in order of preference)**:
1. Ask Monsieur to run `security find-generic-password -s "Brave Safe Storage" -a "Brave" -w` in a local Terminal and paste the result — **only reliable method, use this first**
2. If vault already has `macos/brave_keychain_key` from a previous session, skip extraction entirely
3. Read unencrypted metadata only (host, name, path, flags) — enough for some OSINT but not for authenticated browsing

**Note**: `security dump-keychain` CAN list the entry without the password (shows service name, account, dates), but `find-generic-password -w` CANNOT read the secret value. The `-g` flag does not help via SSH.

### Getting the Keychain Password (2026-05 tested)

**Most reliable (100% success):** Ask Monsieur to run on his Mac terminal:
```bash
security find-generic-password -s "Brave Safe Storage" -a "Brave" -w
```
He pastes the result (e.g., `«secret:vault»`). Store in vault as `macos/brave_keychain_key`.

**Automated via osascript with credentials (UNRELIABLE — 2026-05-24 tested, consistent failure):**
```bash
MAC_PASS=$(vault get macos/lucas_password 2>/dev/null)
osascript -e "do shell script \"security find-generic-password -s \\\"Brave Safe Storage\\\" -a \\\"Brave\\\" -w\" user name \"lucasjouvencon\" password \"$MAC_PASS\" with administrator privileges"
```
This approach returns error 36 (errSecInteractionNotAllowed) consistently. The `set-key-partition-list` workaround does NOT fix the ACL for this item. Do NOT spend more than 2-3 attempts — go directly to asking the user to run the command locally.

### Decrypt Formula (once you have the key)

```python
import hashlib, json
from Crypto.Cipher import AES

# The keychain value is the PBKDF2 password (NOT the raw AES key)
keychain_value = b'<from keychain>'  # e.g. b'«secret:vault»'
derived_key = hashlib.pbkdf2_hmac('sha1', keychain_value, b'saltysalt', 1003, dklen=16)

def decrypt_cookie(encrypted_hex):
    enc = bytes.fromhex(encrypted_hex)
    # Strip v10 (3 bytes) or v11 (4 bytes) prefix
    if enc[:3] == b'v10': enc = enc[3:]
    elif enc[:4] == b'v11': enc = enc[4:]

    # First 16 bytes = IV (domain-shared nonce), remaining = ciphertext
    iv = enc[:16]
    data = enc[16:]

    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(data)

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16 and all(b == pad_len for b in decrypted[-pad_len:]):
        decrypted = decrypted[:-pad_len]

    # CRITICAL: first 16 bytes are always garbled (wrong IV derivation).
    # All cookies in the same domain share the same first ciphertext block,
    # producing the same garbled prefix. The actual value starts at byte 16.
    if len(decrypted) > 16:
        clean = decrypted[16:]
    else:
        clean = decrypted  # very short cookie, value may be in first block

    # Extract only printable ASCII
    return bytes(b for b in clean if 32 <= b <= 126).decode('ascii')
```

**Why the first 16 bytes are garbled**: Brave/Chrome on macOS stores a per-domain nonce as the first 16 bytes of encrypted data (all cookies in the same domain share this block). The PBKDF2-derived key decrypts blocks 2+ correctly via CBC chaining, but the first block requires the correct IV which is not the standard `b' ' * 16`. Skipping the first 16 bytes of decrypted output reliably extracts the clean cookie value.

See `references/macos-cookie-decryption.md` for the full analysis of the encryption scheme.
