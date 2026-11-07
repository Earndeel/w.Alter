---
name: camoufox-max-api-current
description: "Advanced anti-detection browser automation using Camoufox: max variant, persistent session state, SPA/React handling, and session crash troubleshooting."
version: 1.1.0
author: Orchestra Research
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Camoufox, Anti-detect, Scraping, Automation, Playwright, React, SPA]
---

# Camoufox Automation & Stealth Mastery

A unified, comprehensive class-level skill covering advanced web scraping, SPA automation, and persistent browser configurations using Camoufox, specifically addressing the standard and `camoufox-max` variants.

---

## 1. Environment & Setup

Camoufox is a specialized anti-detection browser fork of Firefox. The standard server operates on port 9377 by default, while custom stealth configurations may run on designated container loopbacks.

### Setup and Health Verification
Before interacting, ensure the service is running and verify its health:
```bash
# Verify connection to local Camoufox server
curl http://localhost:9377/health
```

---

## 2. Standard vs. Camoufox-max

| Feature | Standard Camoufox | Camoufox-max Variant |
|---|---|---|
| Port | `9377` | `9377` (overridden) or `9378` |
| Primary Use | Basic anti-detect browsing | Highly interactive SPAs / AWS console |
| State Persistence | Incompatible with standard `--user-data-dir` | Supported via custom `storage-state.json` |
| Custom API | Playwright Standard | Custom `/evaluate` endpoint |

---

## 3. SPA & React Element Handling

Standard element interaction (like `.value = ...` or clicking) often fails to trigger the underlying state manager in React or other SPA frameworks.

### React Property Setters & Event Dispatch
To safely modify input fields and trigger state updates, use native element setters:
```javascript
// Example JavaScript block to run in page context
const input = document.querySelector('input[name="username"]');
const nativeValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
nativeValueSetter.call(input, 'my-username');
input.dispatchEvent(new Event('input', { bubbles: true }));
```

---

## 4. Browser Health Check & Auto-Restart (Critical for Long Sessions)

For long-running browser sessions (AWS console, multi-step flows), the browser can crash silently. Implement a health check mechanism:

### Health Check Function
```javascript
async function isBrowserAlive() {
  try {
    if (!browserContext || !browserContext._browser) return false;
    const pages = browserContext.pages();
    if (!pages || pages.length === 0) return false;
    await pages[0].evaluate('1+1');
    return true;
  } catch (e) {
    return false;
  }
}
```

### Auto-Restart Wrapper
```javascript
async function ensureBrowserHealthy() {
  if (!(await isBrowserAlive())) {
    console.log('Browser unhealthy, restarting...');
    await startBrowser();
    return true; // restarted
  }
  return false; // was healthy
}
```

### Health Endpoint
```javascript
app.get('/health', async (req, res) => {
  const alive = await isBrowserAlive();
  res.json({ ok: alive, browser: alive ? 'running' : 'dead' });
});
```

### Restart Endpoint
```javascript
app.post('/restart', async (req, res) => {
  try {
    await startBrowser();
    res.json({ ok: true, message: 'Browser restarted' });
  } catch (e) {
    res.json({ ok: false, error: e.message });
  }
});
```

### Wrap All Browser Operations
Every endpoint that interacts with the browser should call `ensureBrowserHealthy()` first:
```javascript
app.post('/tab/evaluate', async (req, res) => {
  await ensureBrowserHealthy();
  // ... existing logic
});
```

### Smart Tab Recovery: improvedBrowserSession (Production Pattern)
For maximum resilience, wrap all browser calls in `improvedBrowserSession()` which auto-retries on browser crash:

```javascript
async function improvedBrowserSession(tabId, callback) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      await ensureBrowser();
      const pages = browser.contexts()[0]?.pages() || [];
      let page = pages[0];
      if (!page) throw new Error('No active page');
      return await callback(page);
    } catch (e) {
      if (e.message.includes('Target page, context or browser has been closed') ||
          e.message.includes('Execution context was destroyed') ||
          e.message.includes('No active page')) {
        browser = null;
        if (attempt === 0) { await ensureBrowser(); continue; }
      }
      throw e;
    }
  }
}
```

See `camoufox-max-api-current` skill for the full production server implementation including `activeTabs` tracking, WebSocket frame error handling, and page error logging.

**Why this matters**: Without health checks, long sessions (AWS console, multi-step auth flows) fail silently. The server reports success but the browser is dead. Auto-restart + tab recovery recovers transparently — the client gets a valid response instead of a cryptic "Target page closed" error.

## 5. React Fiber Keys Stripped by Anti-Fingerprinting — BUT bypassable

**Symptom**: `Object.getOwnPropertyNames(el)`, `Reflect.ownKeys(el)`, and
`Object.getOwnPropertySymbols(el)` all return `[]` on every DOM element. `for...in`
loops only return inherited prototype properties (~316 standard HTMLElement props,
zero React internals like `__reactFiber$xxx` or `__reactContainer$xxx`).

**Impact**: The classic "read React fiber via element own-property" technique is
impossible in Camoufox. BUT this is **not a dead end** — see
`references/react-fiber-hook.md` for the verified DevTools-hook bypass
(2026-08-11): install a minimal `__REACT_DEVTOOLS_GLOBAL_HOOK__` via
`add_init_script` before React loads; React registers roots on that `window`
hook (not on elements), so the anti-fingerprint element stripping never touches
it. You then walk the fiber tree from the captured roots and get props/state of
every component in full, inside Camoufox — proven on Excalidraw (509 nodes,
store object visible) and OneForma (React 19.2.7). Ready-to-run:
`~/.hermes/scripts/camoufox_react_runner.py` + `react-fiber-hook.js`.

**Fallbacks when you can't use the hook** (e.g. driving the Camoufox-max HTTP
server that can't `add_init_script`):
- Use **screenshots + vision** for reading page state
- Use **UI automation** (click-at, keyboard-type, keyboard-press) for writing/interacting
- For true React API access requiring the DevTools mutation path, use **Chromium**
  (Playwright CDP) instead — it exposes fibers normally (but loses anti-detect).

**Verified**: Tested on excalidraw.com collaboration room (820 DOM elements, all returned 0 own properties). Also confirmed: clipboard hooks, Blob overrides, and module import tricks all fail against bundled SPAs in Camoufox.

---

## 6. Session Crash & Pitfall Troubleshooting

### 1. Persistent Context Silent Exits
Using persistent browser context (`--user-data-dir`) in stock Camoufox can lead to silent exits.
- **Remedy:** Avoid persistent context in stock installations. Use `camoufox-max` and save/restore cookies via cookie injection.

### 2. SingletonLock Cleanups
If the browser crashes, a stale `SingletonLock` symlink can prevent Camoufox from launching.
- **Remedy:** Delete the lock symlink in your profile directory before re-launching:
  ```bash
  rm -f ~/.mozilla/firefox/*.default-release/SingletonLock
  ```

### 3. Playwright Core Patches
To prevent uncaught exceptions on undefined locations, apply a safety patch to Playwright's `coreBundle.js`:
- **Target:** `node_modules/playwright-core/lib/coreBundle.js`
- **Patch:** Add null checks for `pageError.location` to bypass fatal crashes.

### 4. "Target page, context or browser has been closed" Crash
**Symptom**: Browser operations fail with `Target page, context or browser has been closed` error. Server appears running but all interactions fail.

**Root cause**: Browser process crashed or was killed externally. Camoufox server doesn't detect the crash and continues trying to use the dead context.

**Fix**: Implement the health check + auto-restart pattern from §4 above. The `ensureBrowserHealthy()` wrapper detects dead browsers and restarts transparently.

**Manual recovery**: If auto-restart isn't implemented:
```bash
# Check if browser is alive
curl http://localhost:9378/health

# Force restart
curl -X POST http://localhost:9378/restart

# Or restart the entire server
pkill -f "node server-max.js"
cd /root/.hermes/camoufox-max && node server-max.js &
```

---

## Support Directory Map
- `references/max-automation.md`: Detailed configuration for `camoufox-max` automation, including custom server code and standard `/evaluate` endpoints.
- `references/max-variant.md`: Operational architecture of Variant B, standard loopback cookie imports, and headless startup logs.
- `references/session-pitfalls.md`: Thorough debugging recipes for OneTrust overlays, AWS console navigation issues, and browser crash handling.
- `references/aws-mfa-resend-code-pitfall.md`: AWS "Resend code" button — shift+mousedown pattern that actually works (confirmed 2026-06-11), 60-second code expiry timing, fast MFA flow.
