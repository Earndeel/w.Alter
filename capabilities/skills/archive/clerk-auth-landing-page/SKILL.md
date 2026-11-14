---
name: clerk-auth-landing-page
category: devops
description: Integrate Clerk authentication into a static landing page with backend provisioning webhook.
---

# Clerk Auth for Static Landing Pages

## When to Use

- Building a static HTML landing page that needs Clerk authentication
- Integrating Clerk `mountSignIn`/`mountSignUp` inline components via CDN
- Provisioning users on a separate backend after Clerk login

When building a landing page with Clerk auth that provisions users on a separate backend.

## Key Learnings

### Clerk CDN Versions (CRITICAL)

**`@4` from jsdelivr — USE THIS for `mountSignIn`/`mountSignUp` inline components:**
```html
<script data-clerk-publishable-key="pk_test_..." 
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@4/dist/clerk.browser.js"
  crossorigin="anonymous"></script>
```
```javascript
// Singleton pattern — NO constructor
await Clerk.load();          // init
Clerk.mountSignIn(el, opts); // inline sign-in widget
Clerk.session.getToken();    // JWT for API calls
```

**`@latest` (v5) — only has `openSignIn`/`openSignUp` (modal overlays), NO `mountSignIn`:**
```javascript
await Clerk.load();
Clerk.openSignIn();  // works
Clerk.mountSignIn(); // DOES NOT EXIST in v5 from CDN
```

### WRONG patterns that DON'T work:
- `new Clerk(key)` — v4 CDN uses singleton, not constructor
- `@latest` CDN + `mountSignIn` — v5 removed inline mounting from CDN build
- Just `script.onload = initClerk` without polling — `Clerk` object exists but `.load` not ready yet
- Loading from Clerk's own domain CDN — not a real CDN

### Performance Optimization
Load Clerk immediately at boot, not on click:
```javascript
async function boot() {
  // Pre-warm backend
  fetch(API + '/api/me').catch(() => {});
  // Poll for Clerk CDN ready
  while (typeof Clerk === 'undefined' || typeof Clerk.load !== 'function') {
    await new Promise(r => setTimeout(r, 100));
  }
  await Clerk.load();
  // Ready — mountSignIn is instant on click
}
boot();

function showSignIn() {
  document.getElementById('modal').classList.remove('hidden');
  Clerk.mountSignIn(el, opts); // should be instant
}
```

Add `<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>` in `<head>`.

### Publishable Key Format
The publishable key encodes the Clerk instance domain. Decode with:
```python
import base64
raw = pub_key.replace("pk_test_", "")
domain = base64.b64decode(raw + '=' * (4 - len(raw) % 4)).decode().strip().rstrip('$')
```

### Dark Theme CSS Overrides for Clerk
```css
.cl-rootBox,.cl-card{background:transparent!important;box-shadow:none!important}
.cl-formButtonPrimary{background:linear-gradient(135deg,#00e676,#7c8cff)!important;color:#000!important}
.cl-formFieldInput{background:rgba(0,0,0,.4)!important;border:1px solid rgba(255,255,255,.1)!important;color:#e8e8f0!important}
.cl-formFieldInput:focus{border-color:#00e676!important}
.cl-formFieldLabel{color:#8888a0!important}
.cl-dividerText{color:#555!important}
.cl-dividerLine{background:rgba(255,255,255,.06)!important}
.cl-footerActionLink{color:#00e676!important}
.cl-headerTitle{color:#e8e8f0!important}
.cl-headerSubtitle{color:#8888a0!important}
```

### Architecture Pattern
- Landing page = static (Cloudflare Pages) — NO Clerk SDK on landing, just links to /login.html
- Login page = separate HTML with Clerk widget — handles auth
- After auth → calls backend API to provision (bot, credits, dashboard)
- Backend webhook finds existing users by email before creating new records

### Backend Signup Endpoint Pattern
```python
@app.route("/api/signup", methods=["POST"])
def api_signup():
    # 1. Find existing client by email OR clerk_id in notes
    # 2. If exists, return existing bot/dashboard info
    # 3. If new, auto-provision (assign bot, create env, start dashboard)
    # 4. Store clerk_id in client notes for future lookups
```

### CORS on Cloudflare Workers (CRITICAL)
Every route handler must explicitly add CORS headers. The fetch handler does NOT auto-add them.
Pattern — wrap the handler response:
```typescript
if (path.startsWith("/api/client/")) {
  const cors = getCorsHeaders(request);
  const resp = await handleClientPortal(request, env, path, method);
  const newHeaders = new Headers(resp.headers);
  for (const [k, v] of Object.entries(cors)) newHeaders.set(k, v);
  return new Response(resp.body, { status: resp.status, headers: newHeaders });
}
```
Missing CORS = frontend gets `ERR_FAILED` with no visible error, page appears broken.

### CORS Gotcha: Unconditional API Calls
If an SPA page calls `loadAll()` or similar on load without checking for a valid token, failed CORS requests can crash JS and prevent login overlays from rendering. Always guard:
```javascript
if (ADMIN_TOKEN) loadAll(); // NOT just loadAll();
```

### Spinner Fallback Pattern
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
    el.innerHTML = '<div style="text-align:center;padding:60px"><div class="spinner"></div></div>';
    const check = setInterval(() => {
      if (clerkReady) {
        clearInterval(check);
        Clerk.mountSignIn(el, opts);
      }
    }, 100);
  }
}
```

### Preloading Optimization
```html
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
```
Add spinner CSS:
```css
.spinner{width:32px;height:32px;border:3px solid #2a2a3a;border-top-color:#7c5cfc;border-radius:50%;animation:spin .6s linear infinite;margin:0 auto}
@keyframes spin{to{transform:rotate(360deg)}}
```

### Cloudflare Worker: Missing Admin Endpoints Pattern
When building admin UIs, common missing endpoints that the frontend expects:
- `POST /api/admin/clients/:id/credits` — add credits with `{amount: N}`
- `PUT /api/admin/clients/:id/status` — toggle status with `{status: 'active'|'suspended'}`
- `GET /api/admin/clients/:id` — single client detail

Each needs CORS wrapping (see pattern above). If admin actions silently fail, check Worker logs for 404s.
