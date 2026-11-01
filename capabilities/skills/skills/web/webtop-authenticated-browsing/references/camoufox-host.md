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
