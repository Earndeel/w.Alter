---
name: hermes-camoufox-setup
category: devops
description: Install, configure, and verify Camoufox anti-detection browser as local backend for Hermes gateway, replacing Browserbase.
metadata:
  hermes:
    related_skills: [webtop-authenticated-browsing, playwright-cdp-browser-control]
---

# Hermes Camoufox Setup

Replace Browserbase cloud browser with local Camoufox (Firefox fork with C++-level anti-detection fingerprint spoofing) on aarch64.

## Prerequisites

- Hermes v0.7.0+ (v2026.4.3+) with `@askjo/camoufox-browser` in `package.json`
- Node.js 18+ and npm installed
- aarch64 Linux (Ubuntu 24.04 confirmed working)

## How It Works

`browser_camofox.py` checks `os.getenv("CAMOFOX_URL")`. If non-empty and reachable, it routes ALL browser tool calls to Camoufox instead of Browserbase. No code changes needed -- env-driven activation.

Port: `9377` (default). REST API maps 1:1 to Hermes browser tools.

## Startup Script

Quick start: `bash ~/.hermes/skills/devops/hermes-camoufox-setup/scripts/camoufox-browse.sh [port]`

Or manually via Python subprocess or terminal (not in execute_code).

## Setup Steps

### 1. Verify Camoufox is already installed

After `hermes update`, the postinstall hook (`npx camoufox-js fetch`) runs automatically. Check:

```bash
ls ~/.cache/camoufox/camoufox-bin  # Firefox binary
ls /root/.hermes/hermes-agent/node_modules/@askjo/camofox-browser/server.js  # Server (note: "camofox" not "camoufox" in package name)
```

**IMPORTANT — Package name typo**: The npm package is `@askjo/camofox-browser` (one 'u' — "camofox"), NOT `@askjo/camoufox-browser`. The server file is `server.js`, NOT `server-camoufox.js`. This has been verified on the live system (2026-05-21).

If missing, install manually:
```bash
cd /root/.hermes/hermes-agent/node_modules/@askjo/camofox-browser
npm install
```

**NOTE:** On some installs the `@askjo/camofox-browser` package directory doesn't exist at all (node_modules not populated). In that case, fall back to Playwright CDP via webtop — see skill `playwright-cdp-browser-control`.

### 2. Start the Camoufox server

For the W.Alter deployment, use the MAX systemd service rather than launching a
second standalone Node process. The service owns port 9377, uses the isolated
Node HOME `/root/.camoufox-node-home`, and restarts on failure:

```bash
systemctl daemon-reload
systemctl enable --now camoufox-max.service
```

The legacy `@askjo/camofox-browser/server.js` instructions below apply only to
an isolated installation that does not use the W.Alter MAX service.

DO NOT use `terminal(background=True)` — it fails in execute_code. Use Python subprocess:

```python
import subprocess, os
os.chdir("/root/.hermes/hermes-agent/node_modules/@askjo/camofox-browser")
env = os.environ.copy()
env["PORT"] = "9377"
env["CAMOFOX_PORT"] = "9377"
env["NODE_ENV"] = "development"   # REQUIRED for cookie import from loopback without API key
proc = subprocess.Popen(
    ["node", "server.js"],          # server.js, NOT server-camoufox.js
    stdout=open("/tmp/camoufox.log", "w"),
    stderr=subprocess.STDOUT,
    env=env,
    start_new_session=True
)
```

Or from terminal (not in execute_code):
```bash
cd /root/.hermes/hermes-agent/node_modules/@askjo/camofox-browser
NODE_ENV=development PORT=9377 nohup node server.js > /tmp/camoufox.log 2>&1 &
```

**`NODE_ENV=development` is REQUIRED** — without it, the cookie import endpoint (`POST /sessions/:userId/cookies`) returns 403 for loopback requests. This was verified on 2026-05-21.

### 3. Verify the server

```bash
curl http://localhost:9377/health
# Expected: {"ok":true,"engine":"camoufox","sessions":0,"browserConnected":true}
```

Log output: `/tmp/camoufox.log`
Key indicators: `camoufox-browser listening on port 9377` and `Camoufox browser launched`

### 4. Configure Hermes env

Append to `~/.hermes/.env`:
```
CAMOFOX_URL=http://localhost:9377
```

Use Python to write (never `hermes config set` -- it masks tokens):
```python
with open("/root/.hermes/.env", "a") as f:
    f.write("\nCAMOFOX_URL=http://localhost:9377\n")
```

### 5. Restart the gateway

Kill existing gateway via Python `os.kill(PID, signal.SIGKILL)`, then relaunch:
```python
subprocess.Popen(["hermes", "gateway", "run", "--replace"], start_new_session=True)
```

### 6. Verify

Call `browser_navigate({"url": "https://example.com"})`. Should work WITHOUT `stealth_warning`.

## Health Check

```bash
curl http://localhost:9377/health
# {ok:true, engine:"camoufox", sessions:N, browserConnected:true}
```

Process check:
```bash
pgrep -afa camoufox
# Should show: node server-camoufox.js + camoufox-bin processes
```

## Stopping

```bash
pkill -f "server-camoufox"
# Or via Python: os.kill(PID, signal.SIGKILL)
```

## Detection par site -- ce qui bloque, ce qui passe

**Sites qui Bloquent** (fingerprinting headless, pas IP-based) :
- **Google Search** -- detecte `navigator.webdriver`, canvas fingerprint, WebGL artifacts. Bloque meme avec IP residentielle propre. Retourne "unusual traffic" page.
- **Cloudflare strict** -- certains sites en "Under Attack Mode"

**Sites qui Passent sans probleme** :
- Hacker News, Reddit, Wikipedia, GitHub, StackOverflow, blogs, forums, la majorite des sites
- Sites avec Cloudflare basic (mode non-strict)
- La plupart des pages statiques et API web

**Strategie agent** : Utiliser Camoufox local en priorite (rapide). Si bloqué :
  1. Essayer API directe du site (DuckDuckGo HTML, etc.)
  2. Fallback sur webtop Chromium via CDP (vrai navigateur, non-detectable)
  3. Pour verification visuelle → diriger vers Selkies/noVNC

## Fallback Webtop + Chromium CDP

Quand Camoufox headless est detecte (Google CAPTCHA, Cloudflare strict, etc.), fallback sur un VRAI navigateur dans un webtop Docker.

**Architecture :**
- Container: `lscr.io/linuxserver/webtop:ubuntu-xfce` (Xvfb + XFCE + Chromium)
- Acces visuel: Selkies (streaming fluide) sur `https://100.91.35.121:3101/`
- Acces visuel: noVNC sur `http://100.91.35.121:3100/`
- Contient VRAI Chromium (pas headless, tourne dans un vrai X11 via Xvfb)
- Host ports: 3100 (noVNC), 3101 (Selkies)
- Container IP: typiquement 172.17.0.2

**Display : Xvfb tourne sur `DISPLAY=:1`** (PAS :99). Verifie avec :
```bash
docker exec webtop ps aux | grep Xvfb
```

**Demarrage du navigateur CDP dans le webtop :**
```bash
docker exec webtop bash -c '
  pkill -9 -f chromium 2>/dev/null
  pkill -9 -f socat 2>/dev/null
  sleep 1
  DISPLAY=:1 nohup /usr/bin/chromium-browser \
    --no-sandbox \
    --disable-dev-shm-usage \
    --remote-debugging-port=9222 \
    --remote-debugging-address=127.0.0.1 \
    --window-size=1920,1080 \
    --no-first-run \
    --password-store=basic \
    about:blank &>/dev/null &
  sleep 3
  ss -tlnp | grep 9222
'
```

**IMPORTANT -- Bug Chromium aarch64 :** `--remote-debugging-address=0.0.0.0` ne fonctionne PAS sur ARM/aarch64. Chromium ignore ce flag et bind TOUJOURS sur `127.0.0.1`. Le port mapping Docker `0.0.0.0:9222->9222` ne forwardera rien car Chromium n'ecoute que sur loopback.

**Solution : socat pour forwarder**
```bash
# Installer socat dans le container
docker exec webtop apt-get update -qq && apt-get install -y -qq socat

# Forwarder 0.0.0.0:9223 -> 127.0.0.1:9222
docker exec webtop bash -c '
  nohup socat TCP-LISTEN:9223,fork,reuseaddr TCP:127.0.0.1:9222 &>/dev/null &
'
sleep 2

# Verifier
docker exec webtop curl -s http://127.0.0.1:9223/json/version
```

**Connexion CDP :**
Playwright se connecte via `connectOverCDP("http://localhost:9222")` mais comme Chromium bind sur 127.0.0.1 du container, il faut soit :
1. **Executer le script dans le container** : `docker exec webtop python3 script_cdp.py` (le plus fiable)
2. **Socat + port mapping** : Ajouter `-p 9223:9223` au container, puis `connectOverCDP("http://localhost:9223")` depuis l'hote
3. **API Docker + websocket relay** : Forwarder via `docker exec` + socat

Pour une automatisation fiable sans reconfigurer Docker, executer un script Python CDP directement dans le container :
```bash
docker exec webtop python3 webtop_cdp_script.py
```

Le script utilise `websocket-client` (a installer dans le container : `pip3 install websocket-client`) pour communiquer via CDP.

**Script de contrôle :** `/root/.hermes/bin/webtop-control.sh` (start/status/stop)
- Start: demarre Chromium dans le conteneur webtop avec CDP
- Status: verifie si Chromium tourne et si CDP repond
- Stop: kill Chromium dans le conteneur

**Quand l'utiliser :**
- Google Search bloque avec CAPTCHA
- Verification visuelle manuelle necessaire
- Sites avec anti-bot strict qui bypassent Camoufox
- Besoin de cookies persistants entre sessions
- Navigation sur sites qui detectent le headless

**Strategie agent :** Camoufox en priorite (rapide). Si bloque → basculer sur webtop CDP. Si besoin d'intervention visuelle → diriger l'utilisateur vers Selkies/noVNC.

## Pitfalls

- **execute_code cannot use `terminal(background=True)`** -- get TypeError. Use subprocess.Popen with `start_new_session=True`.
- **Terminal blocks `kill`/`pkill`** -- use execute_code + os.kill() instead.
- **Postinstall runs `npx camoufox-js fetch`** -- downloads ~300MB Firefox fork on first `npm install`. Cache: `~/.cache/camoufox/`.
- **No `--version` flag** -- `camoufox-js --version` fails. Just run `fetch` or check the logs.
- **Camoufox server package may be entirely missing** -- if `node_modules/@askjo/camoufox-browser` directory doesn't exist after `hermes update`, the package wasn't installed. Check with `ls ~/.hermes/hermes-agent/node_modules/@askjo/camoufox-browser/`. If missing, the binary exists (`~/.cache/camoufox/camoufox-bin`) but the Node.js server wrapper is absent. In this case, fall back to Playwright CDP via webtop (skill: `playwright-cdp-browser-control`).
- **Package name is `@askjo/camofox-browser` (no 'u')** -- the npm package has a typo in the name. Server file is `server.js` (not `server-camoufox.js`). Check with `ls node_modules/@askjo/camofox-browser/server.js`.
- **Cookie injection requires `NODE_ENV=development` for localhost** -- The `POST /sessions/:userId/cookies` endpoint is protected by `CAMOFOX_API_KEY`. Without it, cookie import is only allowed from loopback (127.0.0.1) when `NODE_ENV != production`. Always start with: `NODE_ENV=development PORT=9377 node server.js`. Without this, you get 403: "Cookie import is disabled without CAMOFOX_API_KEY".
- **Cookie payload limit: 500 cookies per request, body max 512KB** -- If you have 400+ cookies from Brave, inject per-domain batches, not all at once. Filter by domain first: `POST /sessions/:userId/cookies { cookies: [filtered] }`.
- **Tab creation requires `userId` + `sessionKey`** -- `POST /tabs` needs both fields. Example: `{"userId": "walter", "sessionKey": "fb-session", "url": "https://..."}`. The `sessionKey` groups tabs for cleanup.
- **Refs reset after navigation** -- After `POST /tabs/:id/navigate`, all element refs (e1, e2...) become stale. Must call `GET /tabs/:id/snapshot` again to get fresh refs before clicking.
- **No `/evaluate` endpoint** -- Cannot execute arbitrary JS. Use `/snapshot` (accessibility tree) + `/screenshot` (visual). For JS execution, fall back to Webtop Chromium CDP.
- **Browserbase vars don't need to be removed** -- CAMOFOX_URL takes priority when present.
- **Server auto-reconnects** — if browser crashes while server runs, new sessions re-launch it.
- **Idle shutdown** — Camoufox browser closes when idle, keeping memory ~40MB.
- **`stealth_warning` est cosmetique** — apparait uniquement dans le JSON de reponse du premier `browser_navigate`, pas dans les appels suivants. Ne bloque rien. Peut etre ignore.
- **Locale spoofing aleatoire** — Camoufox spoof une identite geographique aleatoire. Google peut s'afficher en thai, les resultats varient. Normal, c'est l'anti-detection.
- **Webtop Chromium CDP `new_context` fails** — When connecting via Playwright CDP to the webtop Chromium, `browser.new_context()` followed by navigation causes `TargetClosedError`. Always use the existing context: `browser.contexts[0]`. This was verified 2026-05-21.
- **Webtop Chromium gets blocked by anti-bot** — Facebook closes the page entirely, Google shows CAPTCHA. The Chromium in webtop has no anti-detection. Use Camoufox for sites with anti-bot protection.
- **Camoufox API requires `userId` + `sessionKey`** — Every endpoint needs both. Use consistent values (e.g., `userId="walter"`, `sessionKey="fb-session"`). Refs from snapshot are valid only within a session and reset after navigation.
- **Facebook blocks Chromium CDP but passes Camoufox** -- Verified May 2026. Chromium in webtop gets `TargetClosedError` on Facebook even with anti-detection JS patches. Camoufox with injected cookies loads Marketplace successfully.

## Cookie Injection Workflow (Mac Brave → Camoufox)

Full recipe for authenticated browsing with Mac cookies:

```python
import http.client, json, subprocess, time, asyncio

# 1. Extract cookies from Mac Brave via SSH + CDP
proc = subprocess.Popen(
    ["ssh", "-o", "StrictHostKeyChecking=no", "-L", "19222:localhost:9222",
     "-N", "lucasjouvencon@100.127.150.1"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(2)

# Get browser WS URL
conn = http.client.HTTPConnection("localhost", 19222)
conn.request("GET", "/json/version")
resp = json.loads(conn.getresponse().read())
ws_url = resp["webSocketDebuggerUrl"].replace("ws://localhost:9222", "ws://localhost:19222")

import websockets
async def get_cookies():
    async with websockets.connect(ws_url, max_size=50*1024*1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        resp = json.loads(await ws.recv())
        return resp.get("result", {}).get("cookies", [])

cookies = asyncio.run(get_cookies())
proc.terminate()

# 2. Inject per-domain into Camoufox
def cf(method, path, body=None):
    conn = http.client.HTTPConnection("localhost", 9377)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, json.dumps(body) if body else None, headers)
    resp = conn.getresponse()
    return resp.status, json.loads(resp.read().decode())

fb_cookies = [c for c in cookies if ".facebook.com" in c["domain"]]
cf("POST", "/sessions/walter/cookies", {"cookies": fb_cookies})

# 3. Navigate with anti-detect
status, result = cf("POST", "/tabs", {
    "userId": "walter", "sessionKey": "fb-session",
    "url": "https://www.facebook.com/marketplace"
})
tab_id = result["tabId"]
time.sleep(5)

# 4. Screenshot
conn = http.client.HTTPConnection("localhost", 9377)
conn.request("GET", f"/tabs/{tab_id}/screenshot?userId=walter&sessionKey=fb-session")
with open("/tmp/fb.png", "wb") as f:
    f.write(conn.getresponse().read())
```

## CAPTCHA Solving

The `.env` has `CAPSOLVER_API_KEY` for automated CAPTCHA solving. Camoufox itself doesn't solve CAPTCHAs — the key is used by external services.

**Setup:** Get API key from capsolver.com ($1 free tier). Save in `.env`:
```
CAPSOLVER_API_KEY=CAP-xxxx
```

**If Camoufox is blocked by CAPTCHA:** fall back to Playwright CDP + capsolver API. See skill `playwright-cdp-browser-control` and its `references/captcha-solving.md` for full integration patterns.

## Cookie Injection (Mac Brave → Camoufox)

To use authenticated sessions (Facebook, Google, etc.), extract cookies from Mac Brave and inject into Camoufox.

### API Endpoints

| Endpoint | Usage |
|---|---|
| `POST /sessions/:userId/cookies` | Import cookies (Playwright format) |
| `POST /tabs` | Create tab (requires `userId` + `sessionKey`) |
| `POST /tabs/:tabId/navigate` | Navigate to URL |
| `GET /tabs/:tabId/screenshot` | PNG screenshot (pass `userId` + `sessionKey` as query params) |
| `GET /tabs/:tabId/snapshot` | Accessibility tree with clickable `[eN]` refs |
| `POST /tabs/:tabId/click` | Click by ref (e.g., `{"ref": "e38"}`) |
| `POST /tabs/:tabId/type` | Type text (requires ref from snapshot) |
| `POST /tabs/:tabId/press` | Press key (e.g., `{"key": "Enter"}`) |
| `POST /tabs/:tabId/scroll` | Scroll (`direction` + `amount`) |

### Cookie Import

```python
import http.client, json

# Filter cookies by domain (avoid 413 Payload Too Large — max 512KB)
fb_cookies = [c for c in all_cookies if ".facebook.com" in c["domain"]]

conn = http.client.HTTPConnection("localhost", 9377)
body = json.dumps({"cookies": fb_cookies})
conn.request("POST", "/sessions/walter/cookies", body, {"Content-Type": "application/json"})
resp = conn.getresponse()
# Expected: {"ok": true, "userId": "walter", "count": 8}
```

**Payload limit**: Max 512KB per request. Inject per-domain batches, not all 425 cookies at once.
**Auth**: Requires `NODE_ENV=development` OR `CAMOFOX_API_KEY` in env.
**Max cookies per request**: 500.

### Full Workflow (Mac Brave → Camoufox → Facebook)

```python
# 1. Extract cookies from Mac Brave via SSH CDP
ssh -L 19222:localhost:9222 -N lucasjouvencon@100.127.150.1 &
# Use websockets to connect to ws://localhost:19222/devtools/browser/...
# Call Storage.getCookies

# 2. Inject into Camoufox (per-domain)
POST /sessions/walter/cookies {"cookies": [<fb_cookies>]}

# 3. Create tab and navigate
POST /tabs {"userId": "walter", "sessionKey": "fb", "url": "https://www.facebook.com/marketplace"}

# 4. Screenshot + snapshot for interaction
GET /tabs/:tabId/screenshot?userId=walter&sessionKey=fb
GET /tabs/:tabId/snapshot?userId=walter&sessionKey=fb
# → snapshot contains [eN] refs for click/type actions
```

**Verified**: Facebook Marketplace loads authenticated, search works, screenshots captured (2026-05-21).

## Features Available via Camoufox

For full API reference (all endpoints, interaction patterns, Python helper code), see `references/camoufox-api-reference.md`.

- C++-level anti-detection (navigator, WebGL, AudioContext, WebRTC spoofing)
- Element refs (stable e1, e2, e3 identifiers)
- Accessibility snapshots (~90% smaller than HTML)
- Session isolation (separate cookies/storage per user)
- Cookie import (Netscape format)
- Proxy + GeoIP support
- YouTube transcript extraction (yt-dlp)
- Search macros (@google_search, @youtube_search, @amazon_search, etc.)
- Screenshot capture (base64)
- Download capture
- Snapshot pagination (offset-based for large pages)
