---
name: clerk-auth-static-site
description: Integrate Clerk authentication into a static HTML site (no framework). Load SDK, initialize with publishable key, mount sign-in widget, handle auth events.
tags: [clerk, auth, static-site, html]
---

# Clerk Auth for Static Sites

## When use
- Adding auth to a plain HTML/CSS/JS site (no React/Next.js)
- Landing pages that need login/signup
- SaaS portals with Clerk-managed user accounts

## CDN Options (tested April 2026)

### Option A: jsdelivr + Clerk v4 (RECOMMENDED for static HTML)
```html
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<script data-clerk-publishable-key="pk_test_..."
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@4/dist/clerk.browser.js"
  crossorigin="anonymous"></script>
```
- Exposes `Clerk` as **singleton** (NOT a constructor — no `new Clerk()`)
- Has `mountSignIn()`, `mountSignUp()`, etc.
- Init: `await Clerk.load()` then `Clerk.mountSignIn(el, opts)`

### Option B: jsdelivr + Clerk v5 (`@latest`)
```html
<script data-clerk-publishable-key="pk_test_..."
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/dist/clerk.browser.js"
  crossorigin="anonymous"></script>
```
- `mountSignIn` DOES NOT EXIST in v5 — only `openSignIn()` (popup mode)
- No inline mounting to a div
- Only use if popup auth is acceptable

### Option C: Clerk domain CDN
```html
<script src="https://your-app.clerk.accounts.dev/npm/@clerk/clerk-js@5/dist/clerk.browser.js"
  data-clerk-publishable-key="pk_test_..."></script>
```
- `window.Clerk` NOT available on script `onload` — must poll
- `Clerk.load()` needs publishableKey passed explicitly even with data attr

## Recommended pattern (Option A)

```html
<head>
  <link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
  <script data-clerk-publishable-key="pk_test_..."
    src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@4/dist/clerk.browser.js"
    crossorigin="anonymous"
    onerror="console.error('Clerk CDN failed')"></script>
</head>
<body>
  <!-- Modal with loading state -->
  <div id="auth-modal" class="hidden">
    <div class="spinner" id="auth-spinner"></div>
    <div id="clerk-mount"></div>
  </div>

  <script>
  let clerkReady = false;
  let currentUser = null;

  // Boot: load Clerk immediately at page load, not on button click
  async function boot() {
    while (typeof Clerk === 'undefined' || typeof Clerk.load !== 'function') {
      await new Promise(r => setTimeout(r, 100));
    }
    await Clerk.load();
    clerkReady = true;

    if (Clerk.user) {
      currentUser = Clerk.user;
      onAuthenticated(Clerk.user);
    }
  }
  boot();

  function showSignIn() {
    document.getElementById('auth-modal').classList.remove('hidden');
    if (clerkReady) {
      mountSignIn();
    } else {
      document.getElementById('auth-spinner').style.display = 'block';
      const check = setInterval(() => {
        if (clerkReady) {
          clearInterval(check);
          document.getElementById('auth-spinner').style.display = 'none';
          mountSignIn();
        }
      }, 100);
    }
  }

  function mountSignIn() {
    Clerk.mountSignIn(document.getElementById('clerk-mount'), {
      afterSignInUrl: window.location.href,
      appearance: { variables: {
        colorPrimary: '#7c5cfc',
        colorBackground: '#14141f',
        colorText: '#e4e4ef'
      }}
    });
  }

  async function getToken() {
    if (!Clerk?.session) return '';
    return await Clerk.session.getToken();
  }

  async function signOut() {
    await Clerk.signOut();
    currentUser = null;
  }
  </script>
</body>
```

## UX optimizations
- `<link rel="preconnect">` to CDN domain — DNS/TLS handshake starts at page load
- `Clerk.load()` at boot (not on click) — SDK ready before user clicks
- Loading spinner in modal — covers the case where click happens before load
- CSS transitions on modal — `opacity` + `transform:translateY` for smooth appearance
- Pre-warm backend API — `fetch('/health')` wakes up serverless workers

## Cloudflare Workers CORS (when calling API from Clerk portal)

If your static portal calls a Cloudflare Worker API, CORS must be added to **every response**, not just OPTIONS preflight:

```typescript
// In fetch handler, wrap handlers that serve cross-origin:
if (path.startsWith("/api/client/")) {
  const cors = getCorsHeaders(request);
  const resp = await handleClientPortal(request, env, path, method);
  const newHeaders = new Headers(resp.headers);
  for (const [k, v] of Object.entries(cors)) newHeaders.set(k, v);
  return new Response(resp.body, { status: resp.status, headers: newHeaders });
}

function getCorsHeaders(request: Request): Record<string, string> {
  const origin = request.headers.get("Origin") || "";
  const allowed = ALLOWED_ORIGINS.includes(origin)
    || origin.endsWith(".pages.dev")  // Allow Pages preview URLs
    ? origin : "";
  return {
    "Access-Control-Allow-Origin": allowed,
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
    "Vary": "Origin",
  };
}
```

**Common mistake**: Only returning CORS on OPTIONS preflight. Browsers need CORS on the actual response too, otherwise `fetch()` throws a network error.

## Pitfalls
- **jsdelivr `@latest` (v5) has NO `mountSignIn()`** — must use v4 for inline mounting
- **jsdelivr `@4` uses singleton pattern** — `new Clerk(key)` DOES NOT WORK, use `Clerk.load()`
- **`data-clerk-publishable-key` attribute required** on script tag for v4 CDN
- **Clerk user listener** — `Clerk.addListener(({user}) => ...)` for auth state changes
- **JWT in Authorization header** — `Clerk.session.getToken()` returns JWT, send as `Bearer <token>`
- **Dark theme** — Clerk defaults to light; override with `appearance.variables` or CSS overrides
- **Publishable key format** — `pk_test_<base64>` or `pk_live_<base64>`, use as-is from dashboard
- **Worker CORS on every response** — preflight alone is NOT enough, actual responses need CORS headers
- **Worker `loadAll()` guard** — if your admin/UI calls APIs on load, guard with `if (token) loadAll()` to avoid CORS crashes before login
- **Field mapping** — Worker API returns D1 column names (`credits`, `telegram_bot_username`), UI may expect different names (`balance`, `telegram_username`). Normalize in endpoint response.
