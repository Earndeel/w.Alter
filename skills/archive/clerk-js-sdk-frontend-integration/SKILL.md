---
name: clerk-js-sdk-frontend-integration
description: Integrate Clerk authentication into static/Flask sites with dark theme, Google Sign-in, and proper SDK loading.
version: 1.0
---

# Clerk JS SDK — Frontend Integration

## When to Use
- Adding Clerk authentication to a static HTML site or Flask app
- Debugging Clerk SDK loading issues (`Cannot read properties of undefined`)
- Setting up Google Sign-in with Clerk's dark theme

## Pitfalls
- Clerk's CDN URLs change between versions — always verify the publishable key prefix matches the domain
- `window.Clerk` may not be defined if the script loads async — use `onload` or poll
- CSP headers can block Clerk's CDN — whitelist `*.clerk.accounts.dev` and `*.clerk.com`

## Problem
Clerk's JS SDK has multiple initialization patterns and CDN URLs. Getting `window.Clerk` to be defined after script load is tricky. Common failure: "Cannot read properties of undefined (reading 'load')".

## Solution

### Loading the SDK
Load from the Clerk instance's own CDN first, with jsdelivr as fallback:

```javascript
var CLERK_DOMAIN = 'your-instance.clerk.accounts.dev';  // decode from publishable key
var CLERK_PK = 'pk_test_...';

var s = document.createElement('script');
s.async = false;
s.src = 'https://' + CLERK_DOMAIN + '/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
s.crossOrigin = 'anonymous';
s.onload = function() { waitForClerk(); };
s.onerror = function() {
    var s2 = document.createElement('script');
    s2.async = false;
    s2.src = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
    s2.onload = function() { waitForClerk(); };
    document.head.appendChild(s2);
};
document.head.appendChild(s);
```

### Polling for window.Clerk
```javascript
function waitForClerk() {
    var checks = 0;
    var interval = setInterval(function() {
        checks++;
        if (window.Clerk) { clearInterval(interval); initClerk(); }
        else if (checks > 100) { clearInterval(interval); }
    }, 100);
}

async function initClerk() {
    await window.Clerk.load({publishableKey: CLERK_PK});
    if (window.Clerk.user) { showPortal(window.Clerk.user); }
    else { window.Clerk.mountSignIn(document.getElementById('mount')); }
}
```

### Decode Publishable Key to Domain
```python
import base64
raw = pub.replace("pk_test_", "").rstrip("JA")  # remove trailing padding chars
padded = raw + '=' * (4 - len(raw) % 4)
domain = base64.b64decode(padded).decode().strip().rstrip('$')
```

### Dark Theme CSS
```css
.cl-rootBox, .cl-card { background: transparent !important; }
.cl-formButtonPrimary { background: linear-gradient(135deg, #00e676, #7c8cff) !important; color: #000 !important; }
.cl-formFieldInput { background: rgba(0,0,0,.4) !important; color: #e8e8f0 !important; border-color: rgba(255,255,255,.1) !important; }
.cl-formFieldLabel, .cl-headerSubtitle { color: #8888a0 !important; }
.cl-headerTitle { color: #e8e8f0 !important; }
.cl-footerActionLink { color: #00e676 !important; }
```

## Key Learnings
- Clerk v5: use `s.async = false` for reliable loading
- `window.Clerk` availability is delayed after script `onload` — always poll with setInterval
- Pass `publishableKey` to `Clerk.load()` explicitly
- Verify instance: `https://[DOMAIN]/.well-known/openid-configuration`
- Server-side API calls may get 403 (Cloudflare block) — use frontend SDK only
- "Development mode" badge is normal with `pk_test_` keys
- Instance domain format: `[hash].clerk.accounts.dev`
