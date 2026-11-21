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
