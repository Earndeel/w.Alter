---
name: clerk-auth
description: "Integrate Clerk authentication into static sites, landing pages, and Flask backends. Covers CDN loading (v4 vs v5), mountSignIn, dark theme, publishable key decoding, CORS, and backend provisioning."
version: 2.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [clerk, auth, static-site, landing-page, flask, cdn, oauth]
---

# Clerk Authentication — Complete Guide

Integrate Clerk auth into any static HTML site, landing page, or Flask backend.

## When to Use

- Adding Google/Email authentication to a plain HTML/CSS/JS site
- Landing pages that need login/signup modals
- SaaS portals with Clerk-managed user accounts
- Flask backends needing Clerk JWT verification

## Key Concepts

- **Publishable key** (`pk_test_*`): Used in browser. Decodes to the Clerk domain.
- **Secret key** (`sk_test_*`): Used server-side only. Never expose in frontend.
- **Clerk domain**: Decoded from publishable key. Format: `xxxxx.clerk.accounts.dev`.

## Decoding Publishable Key

```python
import base64
raw = pub_key.replace("pk_test_", "")
padded = raw + '=' * (4 - len(raw) % 4) if len(raw) % 4 else raw
domain = base64.b64decode(padded).decode().strip().rstrip('$')
# → "pleasing-bedbug-9.clerk.accounts.dev"
```

## Loading Clerk JS SDK (3 Methods, in Order of Reliability)

### Method 1: jsdelivr + Clerk v4 (RECOMMENDED for static HTML)

```html
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<script data-clerk-publishable-key="pk_test_..."
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@4/dist/clerk.browser.js"
  crossorigin="anonymous"></script>
```

- Exposes `Clerk` as **singleton** (NOT a constructor — no `new Clerk()`)
- Has `mountSignIn()`, `mountSignUp()`, etc.
- Init: `await Clerk.load()` then `Clerk.mountSignIn(el, opts)`

### Method 2: Domain-specific CDN (fallback)

```javascript
var CLERK_DOMAIN = 'pleasing-bedbug-9.clerk.accounts.dev';
var s = document.createElement('script');
s.async = true;
s.crossOrigin = 'anonymous';
s.src = 'https://' + CLERK_DOMAIN + '/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
s.onload = boot;
document.head.appendChild(s);
```

### Method 3: jsdelivr v5 (`@latest`)

```html
<script data-clerk-publishable-key="pk_test_..."
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/dist/clerk.browser.js"
  crossorigin="anonymous" async></script>
```

**⚠️ `mountSignIn` DOES NOT EXIST in v5 CDN** — only `openSignIn()` (popup mode). Use v4 for inline mounting.

## Initialization (MUST Poll for window.Clerk)

```javascript
function boot() {
    var tries = 0;
    var iv = setInterval(function() {
        tries++;
        if (window.Clerk && window.Clerk.load) {
            clearInterval(iv);
            init();
        } else if (tries > 80) {
            clearInterval(iv);
            // Error: Clerk not loaded
        }
    }, 100);
}

async function init() {
    await window.Clerk.load();
    if (window.Clerk.user) {
        // Logged in → show portal
    } else {
        window.Clerk.mountSignIn(document.getElementById('mount-point'), {
            afterSignInUrl: window.location.href,
            afterSignUpUrl: window.location.href
        });
    }
}
```

## Spinner Fallback Pattern

If Clerk isn't ready when user clicks "Sign In", show a loading state:

```javascript
let clerkReady = false;
async function boot() {
    while (typeof Clerk === 'undefined' || typeof Clerk.load !== 'function') {
        await new Promise(r => setTimeout(r, 100));
    }
    await Clerk.load();
    clerkReady = true;
}
boot();

function showSignIn() {
    document.getElementById('modal').classList.remove('hidden');
    if (clerkReady) {
        Clerk.mountSignIn(el, opts);
    } else {
        el.innerHTML = '<div class="spinner"></div>';
        const check = setInterval(() => {
            if (clerkReady) { clearInterval(check); Clerk.mountSignIn(el, opts); }
        }, 100);
    }
}
```

## Dark Theme CSS Overrides

```css
.cl-rootBox,.cl-card{background:transparent!important;box-shadow:none!important}
.cl-formButtonPrimary{background:linear-gradient(135deg,#00e676,#7c8cff)!important;color:#000!important;font-weight:700!important}
.cl-socialButtonsIconButton{background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.1)!important}
.cl-formFieldInput{background:rgba(0,0,0,.4)!important;border:1px solid rgba(255,255,255,.1)!important;color:#e8e8f0!important}
.cl-formFieldInput:focus{border-color:#00e676!important}
.cl-formFieldLabel{color:#8888a0!important}
.cl-dividerText{color:#555!important}
.cl-dividerLine{background:rgba(255,255,255,.06)!important}
.cl-footerActionLink{color:#00e676!important}
.cl-headerTitle{color:#e8e8f0!important}
.cl-headerSubtitle{color:#8888a0!important}
```

For custom palette, replace hardcoded colors with your accent/text/dim values.

## Getting JWT for API Calls

```javascript
async function getToken() {
    if (!Clerk?.session) return '';
    return await Clerk.session.getToken();
}
// Send as: Authorization: Bearer <token>
```

## CORS for Cross-Origin API Calls

Frontend on `app.example.com` calling API on `api.example.com` needs CORS.

### Flask

```python
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        return '', 204
```

### Cloudflare Workers

Every route handler must explicitly add CORS headers. The fetch handler does NOT auto-add them.

```typescript
const ALLOWED_ORIGINS = ["https://app.example.com", "http://localhost:3000"];

function getCorsHeaders(request: Request): Record<string, string> {
    const origin = request.headers.get("Origin") || "";
    const allowed = ALLOWED_ORIGINS.includes(origin) || origin.endsWith(".pages.dev") ? origin : "";
    return {
        "Access-Control-Allow-Origin": allowed,
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
        "Vary": "Origin",
    };
}

// In fetch handler — handle preflight
if (method === "OPTIONS") {
    return new Response(null, { headers: getCorsHeaders(request) });
}

// For each route — wrap response with CORS headers
if (path.startsWith("/api/client/")) {
    const cors = getCorsHeaders(request);
    const resp = await handleClientPortal(request, env, path, method);
    const newHeaders = new Headers(resp.headers);
    for (const [k, v] of Object.entries(cors)) newHeaders.set(k, v);
    return new Response(resp.body, { status: resp.status, headers: newHeaders });
}
```

**Common mistake**: Only returning CORS on OPTIONS preflight. Browsers need CORS on the actual response too.

## Backend Signup Endpoint Pattern

```python
@app.route("/api/signup", methods=["POST"])
def api_signup():
    # 1. Find existing client by email OR clerk_id in notes
    existing = db.execute("SELECT * FROM clients WHERE email = ?", (email,)).fetchone()
    if not existing and clerk_id:
        existing = db.execute("SELECT * FROM clients WHERE notes LIKE ?", (f"%clerk_id:{clerk_id}%",)).fetchone()
    # 2. If exists, return existing bot/dashboard info
    # 3. If new, auto-provision (assign bot, create env, start dashboard)
    # 4. Store clerk_id in client notes for future lookups: notes=f"clerk_id:{clerk_id}"
```

## Centralized OAuth for Multi-Project Setups

When managing multiple projects (landing pages, apps, SaaS):
1. **One Clerk account** handles all OAuth providers (Google, GitHub, Apple, etc.)
2. **Same publishable key** used across ALL projects
3. **No redirect URI management** — Clerk handles it automatically per domain
4. **Free tier**: 10,000 MAU — more than enough for multiple projects

## Pitfalls

- **`window.Clerk is undefined`**: Set `window.__clerk_publishable_key = KEY` AND `data-clerk-publishable-key` attribute BEFORE appending the script element.
- **`Cannot read properties of undefined (reading 'load')`**: `window.Clerk` exists but isn't ready. Use `setInterval` polling (100ms, max 100 tries) instead of direct call after `onload`.
- **jsdelivr `@latest` (v5) has NO `mountSignIn()`** — must use v4 for inline mounting.
- **jsdelivr `@4` uses singleton pattern** — `new Clerk(key)` DOES NOT WORK, use `Clerk.load()`.
- **403 on API calls from server**: Clerk blocks server-side calls from certain IPs. Frontend SDK works fine.
- **Publishable key trailing chars**: Some keys have padding chars that decode to `$`. Strip with `.rstrip('$')`.
- **Version pinning**: Use `@4` or `@5` not `@latest` for production stability.
- **Separate auth page preferred**: Embedding Clerk widget in a long landing page causes timing issues. Use dedicated `/login.html`.
- **CORS `Failed to fetch`**: Without `Access-Control-Allow-Origin` header, browser blocks cross-origin requests.
- **Development mode badge**: Shows with `pk_test_` keys. Use `pk_live_`/`sk_live_` for production.
- **CSP headers can block Clerk's CDN** — whitelist `*.clerk.accounts.dev` and `*.clerk.com`.
- **Worker `loadAll()` guard** — if your admin/UI calls APIs on load, guard with `if (token) loadAll()` to avoid CORS crashes before login.
- **Field mapping** — Worker API returns D1 column names (`credits`, `telegram_bot_username`), UI may expect different names. Normalize in endpoint response.
- **`s.async = false`** for reliable Clerk v5 loading order.
