# Camoufox API Quick Reference

Base URL: `http://localhost:9377`

## Prerequisites
- Server started with `NODE_ENV=development` (required for cookie import from loopback)
- Package: `@askjo/camofox-browser` (one 'u' in "camofox"), file: `server.js`

## Authentication
All endpoints require `userId` + `sessionKey` (query params for GET, body for POST).
Cookie import requires either `CAMOFOX_API_KEY` env var OR `NODE_ENV=development` from loopback.

## Endpoints

### Health
```
GET /health
→ {"ok":true, "engine":"camoufox", "browserConnected":true, "activeTabs":0}
```

### Cookie Import
```
POST /sessions/:userId/cookies
Body: {"cookies": [{"name":"c_user","value":"123","domain":".facebook.com","path":"/","secure":true,"httpOnly":true}]}
→ {"ok":true, "userId":"walter", "count":8}
```
- Max 500 cookies per request, body max 512KB
- Inject per-domain batches to avoid 413 errors
- Fields: name, value, domain (required). Optional: path, expires, httpOnly, secure, sameSite

### Tab Management
```
POST /tabs
Body: {"userId":"walter", "sessionKey":"fb", "url":"https://facebook.com"}
→ {"tabId":"uuid-here", "url":"https://facebook.com"}
```

### Navigation
```
POST /tabs/:tabId/navigate
Body: {"userId":"walter", "sessionKey":"fb", "url":"https://..."}
→ {"url":"https://...", "status":200}
```

### Screenshot
```
GET /tabs/:tabId/screenshot?userId=walter&sessionKey=fb
→ PNG binary
```

### Snapshot (Accessibility Tree)
```
GET /tabs/:tabId/snapshot?userId=walter&sessionKey=fb
→ {"snapshot":"- heading \"Title\" [level=1]\n- link \"Click me\" [e1]"}
```
Refs are `[eN]` format (e1, e2, e3...). **Refs reset after navigation** — must re-snapshot.

### Click
```
POST /tabs/:tabId/click
Body: {"userId":"walter", "sessionKey":"fb", "ref":"e38"}
→ {"ok":true}
```

### Type
```
POST /tabs/:tabId/type
Body: {"userId":"walter", "sessionKey":"fb", "text":"search term", "ref":"e10"}
→ {"ok":true}
```

### Press Key
```
POST /tabs/:tabId/press
Body: {"userId":"walter", "sessionKey":"fb", "key":"Enter"}
→ {"ok":true}
```

### Scroll
```
POST /tabs/:tabId/scroll
Body: {"userId":"walter", "sessionKey":"fb", "direction":"down", "amount":500}
→ {"ok":true}
```

## Interaction Pattern

```python
import http.client, json, time

def cf(method, path, body=None):
    conn = http.client.HTTPConnection("localhost", 9377, timeout=30)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, json.dumps(body) if body else None, headers)
    resp = conn.getresponse()
    data = resp.read().decode()
    try:
        return resp.status, json.loads(data) if data.strip() else {}
    except:
        return resp.status, {"raw": data[:500]}

# 1. Inject cookies
with open("/tmp/brave-cookies-all.json") as f:
    cookies = json.load(f)
fb = [c for c in cookies if ".facebook.com" in c["domain"]]
cf("POST", "/sessions/walter/cookies", {"cookies": fb})

# 2. Navigate
status, r = cf("POST", "/tabs", {"userId":"walter", "sessionKey":"fb", "url":"https://facebook.com/marketplace"})
tab_id = r["tabId"]
time.sleep(5)

# 3. Screenshot
conn = http.client.HTTPConnection("localhost", 9377)
conn.request("GET", f"/tabs/{tab_id}/screenshot?userId=walter&sessionKey=fb")
with open("/tmp/screenshot.png", "wb") as f:
    f.write(conn.getresponse().read())

# 4. Snapshot for refs
status, snap = cf("GET", f"/tabs/{tab_id}/snapshot?userId=walter&sessionKey=fb")
# Parse snapshot for [eN] refs

# 5. Click by ref
cf("POST", f"/tabs/{tab_id}/click", {"userId":"walter", "sessionKey":"fb", "ref":"e38"})
```

## URL-based Search (Facebook Marketplace)

Skip the search UI — use URL params directly:
```
https://www.facebook.com/marketplace/search/?query=pixel&maxPrice=4000
https://www.facebook.com/marketplace/bangkok/search/?query=pixel&minPrice=1000&maxPrice=5000
```

## Verified Working (2026-05-21)
- Facebook Marketplace: ✅ loads authenticated with Mac cookies
- Google Search: ❌ CAPTCHA (IP-based, not fingerprint)
- Facebook via Chromium CDP: ❌ TargetClosedError (anti-bot kills page)
