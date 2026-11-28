---
name: clerk-js-sdk-integration
description: Integrate Clerk authentication (Google, Email) into static HTML pages using Clerk JS SDK v5. Covers common pitfalls discovered during integration.
---

# Clerk JS SDK Integration (Frontend Auth)

## Context
Clerk's JS SDK can be tricky to integrate into static HTML pages. The following approach was discovered through extensive trial and error.

## Working Pattern

### 1. Load SDK
```html
<script>
var CLERK_PK = 'pk_test_XXXXX';  // Your publishable key
var CLERK_DOMAIN = 'xxx.clerk.accounts.dev'; // Decode from PK

// Try Clerk's own CDN first, fallback to jsdelivr
var s = document.createElement('script');
s.async = false;
s.setAttribute('data-clerk-publishable-key', CLERK_PK);
s.src = 'https://' + CLERK_DOMAIN + '/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
s.onerror = function() {
    // Fallback
    var s2 = document.createElement('script');
    s2.async = false;
    s2.src = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
    s2.onload = boot;
    document.head.appendChild(s2);
};
document.head.appendChild(s);

s.onload = function() {
    // MUST poll - window.Clerk not immediately available
    var tries = 0;
    var iv = setInterval(function() {
        tries++;
        if (window.Clerk) {
            clearInterval(iv);
            initClerk();
        } else if (tries > 100) {
            clearInterval(iv);
            console.error('Clerk not found after 10s');
        }
    }, 100);
};
</script>
```

### 2. Initialize Clerk
```javascript
async function initClerk() {
    await window.Clerk.load({publishableKey: CLERK_PK});
    
    if (window.Clerk.user) {
        // Already signed in
        showPortal(window.Clerk.user);
    } else {
        // Show sign-in widget
        window.Clerk.mountSignIn(document.getElementById('clerk-mount'), {
            afterSignInUrl: window.location.href,
            afterSignUpUrl: window.location.href
        });
    }
}
```

### 3. Dark Theme CSS Overrides
```css
.cl-rootBox, .cl-card { background: transparent !important; box-shadow: none !important; }
.cl-formButtonPrimary { background: linear-gradient(135deg, #00e676, #7c8cff) !important; color: #000 !important; }
.cl-formFieldInput { background: rgba(0,0,0,.4) !important; border: 1px solid rgba(255,255,255,.1) !important; color: #e8e8f0 !important; }
.cl-formFieldInput:focus { border-color: #00e676 !important; }
.cl-formFieldLabel { color: #8888a0 !important; }
.cl-headerTitle { color: #e8e8f0 !important; }
.cl-headerSubtitle { color: #8888a0 !important; }
.cl-footerActionLink { color: #00e676 !important; }
.cl-dividerText { color: #555 !important; }
.cl-dividerLine { background: rgba(255,255,255,.06) !important; }
```

## v4 vs v5 CDN — Critical Difference

Clerk v4 and v5 from jsdelivr behave differently:

| | v4 (`@clerk/clerk-js@4`) | v5 (`@clerk/clerk-js@latest`) |
|---|---|---|
| Global | `Clerk` singleton | `Clerk` singleton |
| Init | `await Clerk.load()` | `await Clerk.load()` |
| Mount | `Clerk.mountSignIn(el)` ✅ | ❌ Removed — use `Clerk.openSignIn()` only |
| Token | `Clerk.session.getToken()` | `Clerk.session.getToken()` |

**If you need inline `mountSignIn` (widget in a div), use `@4`.** v5 only has modal `openSignIn`/`openSignUp`.

### v4 Working Pattern
```html
<script data-clerk-publishable-key="pk_test_XXX"
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@4/dist/clerk.browser.js"
  crossorigin="anonymous"></script>
<script>
async function initClerk() {
  await Clerk.load();
  if (Clerk.user) { showDashboard(Clerk.user); return; }
  Clerk.mountSignIn(document.getElementById('clerk-mount'), {
    afterSignInUrl: window.location.href,
    appearance: { variables: { colorPrimary: '#7c5cfc', colorBackground: '#14141f', colorText: '#e4e4ef' } }
  });
}
// Boot: poll for Clerk availability
(function boot() {
  if (typeof Clerk === 'undefined' || typeof Clerk.load !== 'function')
    return setTimeout(boot, 100);
  initClerk();
})();
</script>
```

### v5 Pattern (modal only)
```html
<script data-clerk-publishable-key="pk_test_XXX"
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/dist/clerk.browser.js"
  crossorigin="anonymous"></script>
<script>
async function initClerk() {
  await Clerk.load();
  if (Clerk.user) { showDashboard(Clerk.user); return; }
  Clerk.openSignIn(); // modal, not inline widget
}
</script>
```

## Pitfalls Discovered
1. **v5 removed `mountSignIn`** — Use `@4` for inline sign-in widget, `@latest` only has modal `openSignIn`.
2. **`data-clerk-publishable-key` attribute required on script tag** — The CDN uses this to initialize the singleton. Without it, `Clerk.load()` throws "Missing publishableKey".
3. **`window.Clerk` not available on `onload`** — Must poll with `setInterval` or a while loop.
4. **jsdelivr CDN with `@4` exposes `Clerk` as singleton**, not a constructor — Don't use `new Clerk(key)`, use `await Clerk.load()`.
5. **Clerk widgets render in light theme by default** — Need CSS overrides for dark theme integration.
6. **Server-side API calls to `api.clerk.com` may be blocked** (error 1010) from some IPs — use frontend SDK only, don't call Clerk API from server.
7. **Clerk domain decode:** PK format is `pk_test_<base64(domain)>`. Decode to get `{instance}.clerk.accounts.dev`.
8. **Preconnect for performance** — Add `<link rel="preconnect" href="https://cdn.jsdelivr.net">` to reduce first-click latency.
9. **Load Clerk eagerly** — Call `Clerk.load()` at page boot, not at sign-in click. This makes the modal appear instantly on click.

## Publishable Key Format
- Test: `pk_test_...`
- Live: `pk_live_...`
- Decodes to `{instance}.clerk.accounts.dev`

## Backend Integration
After Clerk auth, call your API to provision the user:
```javascript
var res = await fetch(API_URL + '/api/signup', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: user.firstName, email: user.emailAddresses[0].emailAddress, clerk_id: user.id})
});
```

## Environment Variables
```
CLERK_PUBLISHABLE_KEY=pk_test_XXXXX
CLERK_SECRET_KEY=sk_test_XXXXX
```
