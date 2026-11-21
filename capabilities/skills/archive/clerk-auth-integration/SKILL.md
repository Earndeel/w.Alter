---
name: clerk-auth-integration
category: devops
description: Integrate Clerk authentication into static sites and Flask backends
---

# Clerk Auth Integration

## When to use
Adding user authentication (Google, Email, etc.) to a landing page or web app using Clerk.

## Key concepts
- **Publishable key** (`pk_test_*`): Used in browser. Decodes to the Clerk domain.
- **Secret key** (`sk_test_*`): Used server-side only. Never expose in frontend.
- **Clerk domain**: Decoded from publishable key. Format: `xxxxx.clerk.accounts.dev`.

## Decoding publishable key
```python
import base64
raw = pub_key.replace("pk_test_", "")
padded = raw + '=' * (4 - len(raw) % 4) if len(raw) % 4 else raw
domain = base64.b64decode(padded).decode().strip().rstrip('$')
# → "pleasing-bedbug-9.clerk.accounts.dev"
```

## Loading Clerk JS (critical — 3 methods in order of reliability)

### Method 1: Domain-specific CDN (most reliable)
```javascript
var CLERK_DOMAIN = 'pleasing-bedbug-9.clerk.accounts.dev';
var s = document.createElement('script');
s.async = true;
s.crossOrigin = 'anonymous';
s.src = 'https://' + CLERK_DOMAIN + '/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
s.onload = boot;
document.head.appendChild(s);
```

### Method 2: jsdelivr fallback
```javascript
s.src = 'https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js';
```

### Method 3: data-clerk-publishable-key attribute
```html
<script
  data-clerk-publishable-key="pk_test_xxx"
  src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js"
  crossorigin="anonymous"
  async>
</script>
```

## Initialization (MUST poll for window.Clerk)
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

## CORS for cross-origin API calls
Frontend on `app.example.com` calling API on `api.example.com` needs CORS. Flask:
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

## Matching Clerk Users to Existing Backend Clients

After Clerk auth, the frontend calls your backend with `clerk_id`. But the user might already exist in your DB (from manual creation, previous signup, etc.). Always search by email first:

```python
# In webhook/signup endpoint
existing = db.execute("SELECT * FROM clients WHERE email = ?", (email,)).fetchone()
if not existing and clerk_id:
    existing = db.execute("SELECT * FROM clients WHERE notes LIKE ?", (f"%clerk_id:{clerk_id}%",)).fetchone()
client_id = existing["client_id"] if existing else f"clerk_{clerk_id[:20]}"
```

Store `clerk_id` in client notes on first signup for future lookups: `notes=f"clerk_id:{clerk_id}"`

## Centralized OAuth for Multi-Project Setups

When managing multiple projects (landing pages, apps, SaaS), do NOT configure Google OAuth per project. Instead:

1. **One Clerk account** handles all OAuth providers (Google, GitHub, Apple, etc.)
2. **Same publishable key** used across ALL projects
3. **No redirect URI management** — Clerk handles it automatically per domain
4. **Free tier**: 10,000 MAU — more than enough for multiple projects

Integration pattern for a landing page modal:
```javascript
// Open modal → Clerk mounts sign-in widget
function openAuthModal() {
  document.getElementById('authModal').classList.add('active');
  document.body.style.overflow = 'hidden';
  initClerk(); // Mount Clerk sign-in component
}

async function initClerk() {
  await window.Clerk.load();
  if (window.Clerk.user) {
    window.location.href = '/app.html'; // Redirect logged-in users
  } else {
    window.Clerk.mountSignIn(document.getElementById('clerk-mount'), {
      afterSignInUrl: window.location.href,
      afterSignUpUrl: window.location.href,
      routing: 'hash'
    });
  }
}
```

Dark theme CSS overrides for Clerk (match site palette):
```css
.cl-rootBox,.cl-card{background:transparent!important;box-shadow:none!important}
.cl-formButtonPrimary{background:YOUR_GRADIENT!important;color:YOUR_BG!important;font-weight:700!important}
.cl-socialButtonsIconButton{background:rgba(255,255,255,.06)!important;border:1px solid rgba(255,255,255,.1)!important}
.cl-formFieldInput{background:rgba(0,0,0,.4)!important;border:1px solid rgba(255,255,255,.1)!important;color:#e8e8f0!important}
.cl-formFieldInput:focus{border-color:YOUR_ACCENT!important}
.cl-formFieldLabel{color:#8888a0!important}
.cl-dividerText{color:YOUR_DIM_TEXT!important}
.cl-dividerLine{background:rgba(255,255,255,.06)!important}
.cl-footerActionLink{color:YOUR_ACCENT!important}
.cl-headerTitle{color:YOUR_TEXT!important}
.cl-headerSubtitle{color:YOUR_DIM_TEXT!important}
.cl-socialButtonsBlockButton{background:YOUR_SURFACE!important;border:1px solid rgba(255,255,255,.1)!important}
```

## Pitfalls
- **`window.Clerk is undefined`**: Set `window.__clerk_publishable_key = KEY` AND `data-clerk-publishable-key` attribute BEFORE appending the script element. The key must be available when the SDK initializes.
- **`Cannot read properties of undefined (reading 'load')`**: `window.Clerk` exists but isn't ready. Use `setInterval` polling (100ms, max 100 tries) instead of direct call after `onload`.
- **403 on API calls from server**: Clerk blocks server-side calls from certain IPs. Frontend SDK works fine.
- **Publishable key trailing chars**: Some keys have padding chars that decode to `$`. Strip with `.rstrip('$')`.
- **Version pinning**: Use `@5` not `@latest` for production stability.
- **Separate auth page preferred**: Embedding Clerk widget in a long landing page causes timing issues. Use dedicated `/login.html`.
- **CORS `Failed to fetch`**: Without `Access-Control-Allow-Origin` header, browser blocks cross-origin requests. The API server MUST return this header.
- **Development mode badge**: Shows with `pk_test_` keys. Use `pk_live_`/`sk_live_` for production (upgrade in Clerk dashboard).
