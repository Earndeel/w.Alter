# ExcaliDash Self-Hosted Deployment

ExcaliDash is an open-source wrapper around Excalidraw that adds multi-board management, user authentication, and collaboration. Solves excalidraw.com's lack of persistent multi-board support.

**Repo:** https://github.com/ZimengXiong/ExcaliDash  
**Default port:** 6767 (frontend), 8000 (backend API)

## Docker Compose Deployment

```yaml
# docker-compose.prod.yml
services:
  backend:
    image: zimengxiong/excalidash-backend:latest
    container_name: excalidash-backend
    environment:
      - DATABASE_URL=file:/app/prisma/dev.db
      - PORT=8000
      - NODE_ENV=production
      - AUTH_MODE=local
      - TRUST_PROXY=true  # if behind Cloudflare tunnel
      - JWT_SECRET=${JWT_SECRET}
      - CSRF_SECRET=${CSRF_SECRET}
      - FRONTEND_URL=${FRONTEND_URL}  # MUST match public URL
    volumes:
      - backend-data:/app/prisma
    restart: unless-stopped

  frontend:
    image: zimengxiong/excalidash-frontend:latest
    container_name: excalidash-frontend
    ports:
      - "6767:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  backend-data:
```

Generate secrets: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

## Auth Onboarding Flow (First-Time Setup)

ExcaliDash requires a multi-step onboarding before anyone can log in. All API calls go through the frontend nginx proxy (`/api/auth/...` → backend `/auth/...`).

### Step 1: Enable Auth
```bash
curl -s -X POST https://draw.example.com/api/auth/onboarding-choice \
  -H "Content-Type: application/json" \
  -H "Origin: https://draw.example.com" \
  -d '{"enableAuth": true}'
```
**Pitfall:** Requires `Origin` header matching `FRONTEND_URL` env var, otherwise 403 "CSRF origin mismatch".

### Step 2: Get Bootstrap Setup Code
The setup code is printed in the **backend container logs** (not the API):
```bash
docker logs excalidash-backend 2>&1 | grep "BOOTSTRAP SETUP"
# Output: [BOOTSTRAP SETUP] One-time admin setup code (onboarding_enabled): LD7A-4CFL (expires ...)
```

### Step 3: Register First Admin (with CSRF token)
CSRF tokens are required. Get one first:
```python
import http.client, json, ssl

ctx = ssl.create_default_context()
conn = http.client.HTTPSConnection("draw.example.com", timeout=10, context=ctx)

# Get CSRF token
conn.request("GET", "/api/csrf-token")
resp = conn.getresponse()
data = json.loads(resp.read())
csrf_token = data["token"]
cookie = resp.getheader("Set-Cookie", "").split(";")[0]

# Register admin with setup code
payload = json.dumps({
    "username": "admin",
    "password": "SecurePass123!",
    "name": "Admin",
    "email": "admin@example.com",
    "setupCode": "LD7A-4CFL"  # from container logs
})
headers = {
    "Content-Type": "application/json",
    "Origin": "https://draw.example.com",
    "x-csrf-token": csrf_token,
    "Cookie": cookie,
}
conn2 = http.client.HTTPSConnection("draw.example.com", timeout=10, context=ctx)
conn2.request("POST", "/api/auth/register", body=payload, headers=headers)
# Returns 201 with user object
```

### Step 4: Enable User Registration
```python
# Login first to get auth cookies, then:
conn.request("POST", "/api/auth/registration/toggle",
    body=json.dumps({"enabled": True}),
    headers={"Content-Type": "application/json", "x-csrf-token": csrf, "Cookie": cookies})
# Returns {"registrationEnabled": true}
```

## Creating Drawings via API

POST `/api/drawings` — creates a new board with pre-populated elements. Requires auth (cookie from login) + CSRF token.

**Payload:**
```json
{
  "name": "Board Title",
  "elements": [ ...excalidraw elements... ],
  "appState": { "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```

**Full flow (CSRF → Login → Create):**
```python
import json, http.client, ssl, re

ctx = ssl.create_default_context()
conn = http.client.HTTPSConnection("draw.example.com", timeout=15, context=ctx)

# 1. CSRF token
conn.request("GET", "/api/csrf-token")
resp = conn.getresponse()
csrf = json.loads(resp.read())["token"]
cookie_str = "; ".join(
    f"{v.split('=',1)[0]}={v.split('=',1)[1].split(';')[0]}"
    for k, v in resp.getheaders() if k.lower() == "set-cookie"
)

# 2. Login
h = {"Content-Type": "application/json", "x-csrf-token": csrf, "Cookie": cookie_str}
conn.request("POST", "/api/auth/login",
    body=json.dumps({"email": "user@example.com", "password": "pass"}).encode(), headers=h)
resp = conn.getresponse(); resp.read()
# Merge Set-Cookie into cookie_str
for k, v in resp.getheaders():
    if k.lower() == "set-cookie":
        name, val = v.split(";")[0].split("=", 1)
        cookie_str = re.sub(re.escape(name)+r'=[^;]*', f"{name}={val}", cookie_str) if name+"=" in cookie_str else cookie_str+f"; {name}={val}"

# 3. Create drawing (elements from .excalidraw file)
with open("diagram.excalidraw") as f:
    diagram = json.load(f)
body = json.dumps({
    "name": "My Board", "elements": diagram["elements"],
    "appState": diagram.get("appState", {}), "files": {}
}).encode()
conn.request("POST", "/api/drawings", body=body,
    headers={"Content-Type": "application/json", "x-csrf-token": csrf, "Cookie": cookie_str})
resp = conn.getresponse()
data = json.loads(resp.read())
# data["id"] → https://draw.example.com/d/{id}
```

**Pitfall:** Login returns `success: false` even on 200 if cookies weren't merged — always merge `Set-Cookie` headers from login response into `cookie_str` before creating drawings.

## Updating Existing Drawings (PUT)

**User preference: ALWAYS update the existing board, do NOT create a new one.** When the user asks to modify a diagram, use `PUT /api/drawings/{id}` with the same auth + CSRF flow. The user was explicitly frustrated by repeated new-board creation.

```python
# Same auth flow as above (CSRF → Login → merge cookies), then:
conn.request("PUT", f"/api/drawings/{drawing_id}", body=body,
    headers={"Content-Type": "application/json", "x-csrf-token": csrf, "Cookie": cookie_str})
# Returns 200 on success
```

**Pitfall — 409 Version Conflict:** The server uses optimistic concurrency (ETag/version). If you get 409, fetch the drawing first via `GET /api/drawings/{id}`, extract the version/ETag from the response, and include it as an `If-Match` header in your PUT request.

**Board registry:** Store the drawing ID in memory or reference the known boards:
- `draw.walter-ai.cloud` → drawing `d2b96976-91e7-4eee-be39-92cb2602457a` (Hermes Agent Payload Architecture)

## Deleting Drawings

```python
conn.request("DELETE", f"/api/drawings/{drawing_id}", headers=headers)
# Returns 200 on success
```

## Key Pitfalls

- **FRONTEND_URL must match the public domain** — if set wrong, CORS origin check blocks all POST requests with 403 "CSRF origin mismatch"
- **CSRF is required for all non-GET requests** — token from `GET /api/csrf-token`, cookie must be sent back with `x-csrf-token` header
- **`/auth/` paths skip CSRF token validation** but NOT origin validation — the `Origin` header must still match
- **Bootstrap setup code is in container logs**, not returned via API — `docker logs excalidash-backend | grep BOOTSTRAP`
- **Registration endpoint is `/auth/registration/toggle`** not `/auth/admin/registration/toggle` — no `/admin/` prefix
- **docker-compose v1 is broken** on Docker 29+ — install v2 plugin: `curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/lib/docker/cli-plugins/docker-compose && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose`
