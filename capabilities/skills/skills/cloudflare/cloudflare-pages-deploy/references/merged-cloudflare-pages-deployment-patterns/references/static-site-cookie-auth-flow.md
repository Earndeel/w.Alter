# Static Site Cookie Auth Flow — Full Pattern

**Context**: Static HTML site hosted on Cloudflare Pages, auth handled by Cloudflare Worker backend, Google OAuth, cookie-based sessions.

## Architecture

```
User clicks "Sign in with Google" on static page
    ↓
<a href="https://api.example.com/api/auth/google"> (full page redirect)
    ↓
Worker: stores CSRF state in D1, redirects to Google OAuth
    ↓
Google: user consents
    ↓
Google redirects to Worker callback
    ↓
Worker: exchanges code for tokens, creates/finds user, sets session cookie
    ↓
Worker redirects to static site: https://site.example/?auth=1
    ↓
Static site boot.js: shows loader, polls /api/auth/get-session
    ↓
Session found → store in sessionStorage → reload → dashboard
Session not found after 10s → show sign-in modal
```

## Worker Callback (TypeScript/Worker)

```typescript
// After successful Google auth
const sessionToken = await createSessionToken(user.id, env.BETTER_AUTH_SECRET);
return new Response(null, {
  status: 302,
  headers: {
    Location: "https://site.example/?auth=1",
    "Set-Cookie": `session=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800; Domain=.example.com`,
  },
});
```

**Critical**: Cookie domain must be `.example.com` (with leading dot) to share between `api.example.com` and `site.example.com`.

## Static HTML Boot Sequence

```html
<script>
const API = 'https://api.example.com';

function showLoadingState() {
  document.body.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:16px;">
      <div style="width:40px;height:40px;border-radius:50%;border:2px solid #333;border-top-color:#a78bfa;animation:spin 1s linear infinite;"></div>
      <p style="color:#a0a0a0;font-size:14px;">Connexion en cours...</p>
    </div>`;
}

async function pollSession(maxAttempts = 20) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const r = await fetch(`${API}/api/auth/get-session`, { credentials: 'include' });
      if (r.ok) {
        const data = await r.json();
        if (data?.user) return data.user;
      }
    } catch(e) {}
    await new Promise(r => setTimeout(r, 500));
  }
  return null;
}

async function boot() {
  // Sign-in button from secondary pages
  if (window.location.search.includes('signin=1')) {
    window.history.replaceState({}, '', '/');
    sessionStorage.setItem('show_signin', '1');
    location.reload();
    return;
  }

  // OAuth callback — poll with loading state
  if (window.location.search.includes('auth=1')) {
    window.history.replaceState({}, '', '/');
    showLoadingState();
    const user = await pollSession(20);
    if (user) {
      sessionStorage.setItem('auth_user', JSON.stringify(user));
      location.reload();
      return;
    }
    sessionStorage.setItem('show_signin', '1');
    location.reload();
    return;
  }

  // Restored session after reload
  const restored = sessionStorage.getItem('auth_user');
  if (restored) {
    sessionStorage.removeItem('auth_user');
    showDashboard(JSON.parse(restored));
    return;
  }

  // Show signin after failed auth
  if (sessionStorage.getItem('show_signin')) {
    sessionStorage.removeItem('show_signin');
    showLanding();
    showSignInModal();
    return;
  }

  // Normal boot
  try {
    const r = await fetch(`${API}/api/auth/get-session`, { credentials: 'include' });
    if (r.ok) {
      const data = await r.json();
      if (data?.user) { showDashboard(data.user); return; }
    }
  } catch(e) {}
  showLanding();
}

boot();
</script>
```

## Secondary Pages (Studio, Pricing, etc.)

Sign-in buttons on non-homepage pages must redirect to homepage with param:

```html
<button onclick="location.href='/?signin=1'">Connexion</button>
```

Do NOT try to open a modal on secondary pages — the modal JS/CSS lives only on the homepage.

## CSS for Auth Modal (don't delete during redesigns)

```css
#sign-in-modal {
  position: fixed; inset: 0; z-index: 200;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.7);
  backdrop-filter: blur(10px);
  padding: 24px; overflow-y: auto;
}
#sign-in-modal.hidden { display: none !important; }
#sign-in-modal .modal {
  background: #111; border: 1px solid rgba(255,255,255,.08);
  border-radius: 24px; padding: 40px; max-width: 420px; width: 100%;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
}
```

## Common Bugs & Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Modal doesn't appear | `#nav-links` referenced but doesn't exist after redesign | Defensive coding: `if (el) el.innerHTML = ...` |
| Loop: auth → Google → modal → auth | Cookie not ready on first fetch, modal shown immediately | Poll session for 5-10s with loading spinner |
| "Nothing changed after deploy" | Cloudflare Pages cache (4h) + browser cache | Verify with `curl`, tell user to Ctrl+Shift+R |
| Dashboard flashes then disappears | `showLanding()` called after `showDashboard()` | Add `return` after successful auth in boot sequence |
| 404 on `/api/auth/google` | Using HEAD instead of GET, or wrong path | Verify with `curl -L` (follows redirects) |

## curl Verification Commands

```bash
# Verify CSS deployed
curl -s https://site.example/assets/style.css | grep -c "particle-canvas"

# Verify JS deployed
curl -s https://site.example/assets/app.js | grep -c "pollSession"

# Verify auth endpoint works
curl -sL https://api.example.com/api/auth/get-session \
  -H "Cookie: session=..." | jq .

# Verify Google OAuth initiates
curl -sLI https://api.example.com/api/auth/google | grep -i location
```

## Session Endpoint Contract

```typescript
// GET /api/auth/get-session
// Request: Cookie: session=<token>
// Response 200: { user: { id, name, email, image } }
// Response 200: null (no valid session)
// Response 401: invalid/expired token
```

Always use `credentials: 'include'` in fetch from static frontend to cross-origin Worker API.
