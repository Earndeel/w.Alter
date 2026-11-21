---
name: camoufox-max-server
description: "camoufox-max server (port 9378) — advanced browser automation with JS execution, crash recovery, and React form filling. Used for AWS console, React SPAs, and complex multi-step flows."
tags: [browser, automation, react, aws, camoufox]
related_skills: [hermes-camoufox-setup, anti-bot-navigation, aws-bedrock-browser-setup]
---

# Camoufox-Max Server & React Automation

**Authenticated-session rule:** when an authenticated session comes from Mac Brave, use the Mac profile only as a passive source for SQLite/LevelDB extraction. Never connect navigation automation to the user's Brave CDP and never launch a second browser window with a copied profile; all navigation and interaction belong in the remote Camoufox context. Keep extracted cookies/tokens in memory, do not print them, and close the isolated Camoufox session after a read-only task.

The basic `@askjo/camofox-browser` server (port 9377) has no `/tab/evaluate` endpoint. For complex automation requiring JS execution (AWS console, React SPAs, form filling), use the **camoufox-max** server.

Location: `~/.hermes/camoufox-max/server-max.js`. Do not assume the historical port from this skill: call `/health` first and use the port that actually reports `flavor: max` (the active W.Alter deployment may expose Max on 9377 rather than 9378).

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/tab/new` | POST | Create tab (`{"session":"name"}`) → returns `{tabId}` |
| `/tab/navigate` | POST | Navigate (`{"tabId":"...","url":"..."}`) |
| `/tab/evaluate` | POST | Execute JS (`{"tabId":"...","expression":"..."}`) |
| `/tab/screenshot` | POST | PNG screenshot (base64 in `buffer` field) |
| `/tab/snapshot` | POST | Accessibility tree with `[eN]` refs |
| `/tab/click-at` | POST | Click at pixel coordinates (`{"tabId":"...","x":N,"y":N}`) |
| `/tab/keyboard-type` | POST | Type text with delay (`{"tabId":"...","text":"...","delay":50}`) |
| `/tab/keyboard-press` | POST | Press a key (`{"tabId":"...","key":"Tab"}`) |
| `/health` | GET | Server health + browser status |
| `/restart` | POST | Force browser restart |
| `/tab/add-init-script` | POST | Inject JS **before** page scripts load (`{"tabId":"...","script":"..."}`) — uses Playwright `addInitScript` |
| `/tab/route` | POST | Intercept network requests via `page.route()` (`{"tabId":"...","urlPattern":"**/*.js","body":"...","contentType":"..."}`) |

### Workflow

```bash
# 1. Create tab
TAB=$(curl -s -X POST http://localhost:9378/tab/new \
  -H "Content-Type: application/json" \
  -d '{"session":"aws"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['tabId'])")

# 2. Navigate
curl -s -X POST http://localhost:9378/tab/navigate \
  -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"url\":\"https://example.com\"}"

# 3. Execute JS
curl -s -X POST http://localhost:9378/tab/evaluate \
  -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"expression\":\"document.title\"}"

# 4. Screenshot
curl -s -X POST http://localhost:9378/tab/screenshot \
  -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\"}" | python3 -c "
import sys,json,base64
d=json.load(sys.stdin)
open('/tmp/screen.png','wb').write(base64.b64decode(d['buffer']))
"
```

## Browser Crash Recovery (Critical for AWS/React)

The Camoufox browser process **dies** on complex React/AWS pages. Error: `"Target page, context or browser has been closed"`.

### Full server-max.js Pattern (Production-Tested)

The production `server-max.js` (v2) includes these crash-resilience components:

#### 1. Health + Restart Endpoints

```javascript
const activeTabs = new Map(); // tabId → { sessionId, createdAt }

// GET /health — lightweight server + browser status
app.get('/health', async (req, res) => {
  let browserOk = false;
  try {
    if (browser) { const pages = browser.contexts()[0]?.pages() || []; browserOk = true; }
  } catch {}
  res.json({ ok: true, browser: browserOk ? 'running' : 'dead', tabs: activeTabs.size });
});

// POST /restart — force kill + reinit
app.post('/restart', async (req, res) => {
  try { if (browser) await browser.close().catch(() => {}); } catch {}
  browser = null; activeTabs.clear();
  await ensureBrowser();
  res.json({ ok: true });
});
```

#### 2. Auto-Restart via setInterval

```javascript
// Every 30s: if browser is dead, restart it
setInterval(async () => {
  try { await ensureBrowser(); }
  catch (e) { console.error('[health-check]', e.message); }
}, 30000);
```

#### 3. improvedBrowserSession (Smart Tab Recovery)

When a request fails on a dead/closed tab, don't just return a 500 — **try to recreate the tab and retry the operation**:

```javascript
async function improvedBrowserSession(tabId, callback) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      await ensureBrowser();
      const pages = browser.contexts()[0]?.pages() || [];
      let page = pages.find(p => p.url && activeTabs.get(tabId)?.url === p.url());
      if (!page && pages.length > 0) page = pages[0];
      if (!page) throw new Error('No active page');
      return await callback(page);
    } catch (e) {
      if (e.message.includes('Target page, context or browser has been closed') ||
          e.message.includes('Execution context was destroyed') ||
          e.message.includes('No active page')) {
        console.log(`[recoverable] ${e.message} — attempt ${attempt + 1}`);
        browser = null;
        if (attempt === 0) { await ensureBrowser(); continue; }
      }
      throw e;
    }
  }
}
```

**Why 2 attempts**: First attempt may fail because browser is dead. ensureBrowser() restarts it. Second attempt succeeds on the fresh browser. If it still fails, it's a real error.

#### 4. Page Error Listener (Console Capture)

Attach to every new tab to capture React/AWS JS errors into server logs:

```javascript
page.on('pageerror', error => {
  const url = page.url?.() || 'unknown';
  console.error(`[pageerror] ${url}:`, error.message);
});
```

**Why this matters**: AWS console pages throw JS errors silently. Without this, you'd never know why a form didn't submit or a button didn't work.

#### 5. WebSocket Frame Errors (Common on AWS)

AWS console WebSocket connections throw `WebSocket frame 81106 bytes too long` errors. These are cosmetic (streaming responses) and don't affect functionality. The server catches and logs them without crashing:

```javascript
try { /* ws handler */ }
catch (frameError) {
  if (frameError.message.includes('WebSocket frame') && frameError.message.includes('too long')) {
    console.warn(`[ws-warning] Frame too large for tab ${tabId}: ${frameError.message}`);
    // Don't send error to client — the content was still received
  }
}
```

#### 6. Wrapped Endpoint Pattern

Every browser-touching endpoint uses this try/catch:

```javascript
app.post('/tab/evaluate', async (req, res) => {
  try {
    const result = await improvedBrowserSession(req.body.tabId, async (page) => {
      return await page.evaluate(req.body.expression);
    });
    res.json({ result });
  } catch (e) {
    if (e.message.includes('Target page, context or browser has been closed')) {
      res.writeHead(503, {'Content-Type':'application/json'});
      res.end(JSON.stringify({ error: 'Browser crashed — restarting', retry: true }));
      return;
    }
    res.writeHead(500, {'Content-Type':'application/json'});
    res.end(JSON.stringify({ error: e.message }));
  }
});
```

**Client behavior**: If you get a 503 with `retry: true`, wait 3 seconds, then retry the same request.

## Keyboard/Mouse Endpoints (for Cross-Origin Iframes)

Standard `/tab/evaluate` can't interact with cross-origin iframes (Stripe Elements, payment forms, embedded widgets). Use these Playwright-native endpoints instead:

### Adding to server-max.js

```javascript
// Click at pixel coordinates — bypasses iframe restrictions
app.post('/tab/click-at', async (req, res) => {
  try {
    const { userId, tabId, x, y } = req.body;
    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    await found.tabState.page.mouse.click(x, y);
    res.json({ ok: true, clicked: { x, y } });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// Type text character by character — works in focused cross-origin iframes
app.post('/tab/keyboard-type', async (req, res) => {
  try {
    const { userId, tabId, text, delay = 50 } = req.body;
    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    await found.tabState.page.keyboard.type(text, { delay });
    res.json({ ok: true, typed: text.length + ' chars' });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// Press a single key (Tab, Enter, Escape, etc.)
app.post('/tab/keyboard-press', async (req, res) => {
  try {
    const { userId, tabId, key } = req.body;
    await ensureBrowserHealthy();
    const session = await getSession(userId || 'default');
    const found = findTab(session, tabId);
    if (!found) return res.status(404).json({ error: 'Tab not found' });
    await found.tabState.page.keyboard.press(key);
    res.json({ ok: true, key });
  } catch (e) { res.status(500).json({ error: e.message }); }
});
```

### Workflow: Cross-Origin Iframe Interaction

```bash
# 1. Find iframe coordinates via evaluate
curl -s -X POST http://localhost:9378/tab/evaluate \
  -d '{"tabId":"...","expression":"(function(){ var iframe = document.querySelector(\"iframe[name=__privateStripeFrame123]\"); var r = iframe.getBoundingClientRect(); return JSON.stringify({x:r.left+r.width/2, y:r.top+r.height/2}); })()"}'

# 2. Click at iframe coordinates
curl -s -X POST http://localhost:9378/tab/click-at \
  -d '{"tabId":"...","x":960,"y":537}'

# 3. Type into focused field
curl -s -X POST http://localhost:9378/tab/keyboard-type \
  -d '{"tabId":"...","text":"{{bw:Carte – Vast.ai:number}}","delay":30}'

# 4. Tab to next field
curl -s -X POST http://localhost:9378/tab/keyboard-press \
  -d '{"tabId":"...","key":"Tab"}'
```

**Why this works**: Playwright's `page.mouse.click(x,y)` and `page.keyboard.type()` operate at the browser input level, not the DOM level. They send OS-level events that cross-origin iframes receive just like a human typing.

## Pre-Loading Script Injection (addInitScript)

Use `/tab/add-init-script` to inject JS **before** any page scripts execute. Critical for hooking into React's internal state.

```bash
# Inject before page loads
curl -s -X POST http://localhost:9378/tab/add-init-script \
  -H "Content-Type: application/json" \
  -d '{"tabId":"...","script":"window.__MY_HOOK = {data: []};"}'

# Then navigate — the hook exists when scripts run
curl -s -X POST http://localhost:9378/tab/navigate \
  -d '{"tabId":"...","url":"https://example.com"}'
```

**Common use**: Install `__REACT_DEVTOOLS_GLOBAL_HOOK__` to intercept React fiber tree. See `references/react-state-extraction.md` for full patterns and pitfalls.

## Network Route Interception

Use `/tab/route` to intercept and modify network requests in-flight (e.g., inject code into JS bundles):

```bash
curl -s -X POST http://localhost:9378/tab/route \
  -H "Content-Type: application/json" \
  -d '{"tabId":"...","urlPattern":"**/bundle.js","body":"// modified code","contentType":"text/javascript"}'
```

⚠️ Pattern matching may fail for some URL patterns. Use `**/*.js` as a broad fallback. Route must be set BEFORE navigation.

## Container and Runtime Compatibility

The former `camoufox-container-incompatibility` skill is absorbed here as the compatibility branch. Use this subsection when Camoufox fails before page automation begins, especially in Docker/containerized Hermes environments.

Observed class-level failure modes:
- ESM/CommonJS and native binding mismatches around Playwright/Camoufox dependencies can masquerade as browser launch failures.
- `better-sqlite3`/native module resolution errors usually require rebuilding or pinning dependencies inside the exact runtime image, not retrying the same Node command.
- A container that can run ordinary Playwright may still fail Camoufox-specific stealth/bootstrap code; prove compatibility with a minimal launch + navigate + screenshot probe before building task-specific automation on top.
- Keep failed patch attempts and exact stack traces as references, but do not create one skill per container error string.

## Réactivité des Endpoints (Critique pour SPA lourdes)

Le serveur Max tourne par défaut sur le **port 9377** (le health check indique `flavor: max`), pas 9378. Tous les endpoints ci-dessous fonctionnent sur 9377.

### Fiabilité par endpoint

| Endpoint | Fiabilité | Notes |
|---|---|---|
| `/tab/evaluate` | ✅ Excellent | Temps de réponse <1s, jamais timeout |
| `/tab/screenshot` | ✅ Excellent | ~2s |
| `/tab/snapshot` | ✅ Bon | ~1-3s |
| `/tab/navigate` | ⚠️ Variable | Timeout 15s+ sur SPA lourdes ; relancer si échec |
| `/tab/click` | ❌ Fragile | Timeout fréquent sur React/SPA → utiliser `evaluate` + `.click()` |
| `/tab/type` | ❌ Fragile | Timeout sur champs React → utiliser `evaluate` + `execCommand` |

**Règle** : sur les SPA lourdes (Google Flow, AWS Console), utilisez **exclusivement** `/tab/evaluate` pour les interactions. Le clic JS (`element.click()`) et l'insertion de texte (`execCommand`) sont fiables là où les endpoints Playwright natifs timeoutent.

## React `contenteditable` Inputs (Google Flow, Notion, etc.)

Certains inputs React ne sont PAS des `<input>` ou `<textarea>` mais des `<div contenteditable="true" role="textbox">`. Le setter `HTMLInputElement.prototype.value` ne fonctionne PAS sur ces éléments.

### ❌ Ne fonctionne pas sur contenteditable

```javascript
// Le setter HTMLInputElement ne s'applique pas aux div
var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
setter.call(el, "texte");  // Erreur ou ignoré
```

### ✅ Approche pour contenteditable React

```javascript
var el = document.querySelector('[contenteditable="true"][role="textbox"]');
el.focus();

// Sélectionner puis remplacer
var range = document.createRange();
range.selectNodeContents(el);
var sel = window.getSelection();
sel.removeAllRanges();
sel.addRange(range);

// execCommand('insertText') déclenche l'event 'input' natif que React détecte
document.execCommand('insertText', false, 'votre texte ici');

// Double dispatch pour garantir la détection React
el.dispatchEvent(new Event('input', {bubbles: true, cancelable: true}));
el.dispatchEvent(new Event('change', {bubbles: true, cancelable: true}));
```

### ⚠️ Limite : React state interne

Même avec `execCommand` et les events, certains frameworks React gèrent le state de manière opaque et ne détectent PAS les modifications DOM programmatiques. **Solution de secours** : intercepter les appels API réseau (fetch/XHR) pour découvrir les endpoints internes et les appeler directement avec les cookies de session. Voir `references/google-flow-api.md`.

## Cache Partagé Python/Node — Cause Racine des Instabilités (2026-08-11)

`camoufox` (pip) et `camoufox-js` (node, server-max.js) écrivent TOUS DEUX dans
`~/.cache/camoufox` avec des formats incompatibles — chaque `fetch` de l'un casse
l'autre (`Invalid Extended Type`, `CamoufoxNotInstalled`, browser mort malgré
`browserConnected:true`). Fix unique : le serveur node tourne avec
`HOME=/root/.camoufox-node-home` (son cache isolé), le Python garde
`~/.cache/camoufox`. Démarrer avec la commande unique idempotente
`/root/.hermes/scripts/start-camoufox-max.sh` (fetch node dans SON cache au
premier lancement, systemd comme superviseur unique, test réel d'onglet avant
validation).
Piège port : la variable est `CAMOFOX_MAX_PORT` (défaut fichier 9378, déploiement
W.Alter = 9377), PAS `PORT`. Ne jamais lancer un fetch "pour vérifier" — il écrase
le binaire de l'autre runtime ; kill d'abord, puis fetch dans le HOME dédié.
Full recipe: `references/cache-isolation-and-startup.md`.
For production systemd ownership, eager browser boot, and the real liveness smoke test, see `references/systemd-supervision-and-health.md`.

## Production service contract — systemd owns the lifecycle

The W.Alter deployment must have one owner for port 9377: `camoufox-max.service`.
Do not run a second `server-max.js` manually beside it. The unit starts Node with
`HOME=/root/.camoufox-node-home`, keeping the Node `camoufox-js` cache separate
from Python's `~/.cache/camoufox`; it uses `Restart=always`, a bounded restart
rate, and an `ExecStartPre` check for the isolated browser binary.

`server-max.js` must launch Camoufox eagerly at boot and serialize concurrent
launches with a shared start promise. A listening Node process without a live
browser is not healthy. `/health` must exercise the browser connection (via
`isBrowserAlive()` or equivalent), and the operational smoke test must also
create one tab and obtain a snapshot. `browser !== null` alone is not a health
proof.

After changing either the unit or server, run `systemctl daemon-reload`, restart
the service, then verify `systemctl is-active`, `systemctl is-enabled`,
`/health` with `ok=true` and `browserConnected=true`, plus a real `/tabs` →
`tabId` → snapshot lifecycle. Keep the legacy standalone Camofox instructions
clearly marked as non-production/isolated; they must not compete for port 9377.

## Browser-use × Camoufox (boucle agentique LLM)

La lib `browser-use` 0.4.5 (ère Playwright-native) accepte un navigateur externe
— on lui passe une instance Camoufox : interaction scriptée par LLM + stealth +
sortie proxy FR. **La CLI 3.0 (0.13.x, le mode Browser Use du tweet Nous
Research) est CDP-only et ne peut PAS piloter Camoufox.** Fix obligatoire :
créer `context` + `page` AVANT `Agent(...)` sinon Firefox refuse `clipboard-read`
(3 échecs consécutifs, steps=0). Extraction via `history.final_result()`.
Benchmark : walter_browse bat browser-use×Camoufox sur JSON/API (0,52 s, 0 token
vs 17,8 s) ; browser-use×Camoufox gagne sur HTML statique (3 records exacts en
23,7 s là où walter_browse échoue — son scorer est JSON/XHR-only). Position :
backend d'escalade #3 après camoufox-max, avant webtop-cdp. Full recipe:
`references/browser-use-camoufox-integration.md`.

## Pitfalls

1. **After patching server-max.js**: Old process holds the port. Kill BOTH the Node server AND the Camoufox browser: `kill -9 $(pgrep -f "server-max.js") $(pgrep -f "camoufox-bin")`. Then restart the server.
2. **New endpoints not registered**: If `Cannot POST /tab/click-at`, the server loaded old code. Kill and restart.
3. **Tab must exist**: All keyboard/mouse endpoints require a valid `tabId`. Create tab first with `/tab/new`.
4. **Cookies lost on browser restart** : Même avec `persistent_context: true`, les cookies Google/Flow sont perdus quand le navigateur Camoufox est tué et relancé. **Toujours sauvegarder les cookies** dans `/tmp/flow_cookies.json` après extraction, et les réinjecter après un restart via `/tab/cookie`. L'extraction des cookies depuis le Mac nécessite un accès SSH fonctionnel — si le SSH est down, demander à l'utilisateur.
5. **Vite `type="module"` blocks devtools hook**: Vite bundles load as `<script type="module">`. ES modules have their own scope — `__REACT_DEVTOOLS_GLOBAL_HOOK__` on `window` is visible (`typeof` returns `"object"`) but React 19 module-scoped code may NOT call `inject()`. Verified on Excalidraw (React 19, Vite): hook installed, `typeof` passes, but 0 renderers registered. Workaround: route interception to modify bundle in-flight, or fallback to screenshot + UI automation.
5. **`page.route()` must be set BEFORE navigation**: Routes registered after `navigate()` won't intercept already-loaded resources.
6. **Pre-loading injection reference**: See `references/react-state-extraction.md` for full patterns on React fiber traversal, devtools hook, and Vite module scope pitfalls.

## React Input Value Setter (Critical for AWS/Modern SPAs)

React forms **ignore** simple `.value =` assignment. Form appears filled but submits empty.

### ❌ Does NOT work on React forms

```javascript
inp.value = "my@email.com";
inp.dispatchEvent(new Event("input", {bubbles: true}));
```

### ✅ The correct approach

```javascript
var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
  window.HTMLInputElement.prototype, "value"
).set;
nativeInputValueSetter.call(inp, "my@email.com");
inp.dispatchEvent(new Event("input", {bubbles: true}));
```

### Full AWS Login Pattern

```javascript
// Set email
(function(){
  var inp = document.querySelector("input[type=email], input[type=text]");
  if (!inp) return "no input";
  var setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, "value"
  ).set;
  setter.call(inp, "user@example.com");
  inp.dispatchEvent(new Event("input", {bubbles: true}));
  return "email set";
})()

// Click Next/Sign in
(function(){
  var btns = Array.from(document.querySelectorAll("button"));
  var btn = btns.find(b => (b.textContent||"").includes("Sign in"));
  if (btn) { btn.click(); return "clicked"; }
  return "not found";
})()

// Set password — same setter pattern
// Set verification code — same setter pattern
```

### Why

React 16+ uses a synthetic event system. Setting `.value` directly doesn't update React's internal state. The native HTMLInputElement setter triggers React's value tracking through the DOM property descriptor.

### Sites Confirmed

- AWS Console (signin.aws.amazon.com) — email, password, verification code
- Likely all React-based enterprise SPAs

## AWS Console Pitfalls

1. **Verification codes expire ~10 min** — Enter immediately. If browser crashes, request new code.
2. **AWS SPA pages crash Camoufox** — Always have crash recovery in place before navigating.
3. **Multiple challenges** — AWS may ask: email → password → verification code → MFA. Each step may need React setter.
4. **Server cleanup** — `pkill -f "server-max.js"` to fully stop.
5. **Amazon Q textarea → Enter triggers feedback modal** — The Q chatbot in Support Center consumes Enter for submission but ALSO triggers a feedback/confidence dialog. Do NOT use `keyboard-press` Enter on the Q textarea. Q auto-submits after typing. If feedback modal appears, click X to dismiss.
6. **AWSUI Select dropdowns are extremely slow (10-15s each)** — AWS Support forms use AWSUI Select components with complex React rendering. DOM queries timeout at 25s. Use `click-at` with annotated screenshots. Expect 5-10 min for a full form fill.
7. **Case type dropdown in Support form** — Must select "Service limit increase" or "Billing" via AWSUI Select. The dropdown options appear in a floating overlay (not in DOM tree near the trigger). Use `snapshot` to find the overlay elements after clicking the dropdown trigger, then `click-at` on the correct option.
8. **Annotated screenshots for AWS** — Use `annotate: true` on `/tab/screenshot` to get element IDs mapped to coordinates. IDs are ephemeral (change between page loads). Save the screenshot + IDs immediately before interacting.
9. **DOM queries on AWS console timeout at 25s** — AWS pages are extremely heavy (multiple iframes, React trees, telemetry scripts). Keep evaluate expressions simple. Complex DOM traversals may timeout. Use screenshot + vision instead of DOM inspection for layout understanding.
10. **Basic Support plan has no direct "Create case"** — Must go through Amazon Q chatbot first. Q investigates (20-30s), then shows "Create a case" button. See billing-support-case-template.md in aws-bedrock-setup skill for full flow.
11. **Automated AWS login with Bitwarden MFA** — Use `~/.hermes/bin/aws-auto-login` for full automated login (email → password → MFA → console). Returns the `tabId`. Uses `~/.hermes/bin/aws-mfa` internally which calls `bw-unlock --sync` + `bw get totp`. No manual MFA entry needed. Fallback: ask user for code if Bitwarden TOTP fails.

## SPA Sites with LocalStorage Auth

Sites like One-API, New-API, Sub2API (e.g. aiprimetech.io) store auth in **LocalStorage**, not in cookies. Cookie extraction returns only tracking cookies. Use the LevelDB extraction pipeline: `references/localstorage-auth-extraction.md`.

For Discord sessions sourced passively from Mac Brave and browsed remotely, use `references/discord-auth-via-camoufox.md`: it covers the `token` Local Storage format, Max endpoint differences, channel-ref navigation, timeout verification, and session cleanup.

## Google Flow & SPA API Interception

When Camoufox's `/tab/click` and `/tab/type` fail on complex SPAs (Google Flow), fall back to API-level automation: intercept the SPA's internal `fetch` calls to discover the real REST endpoints, then call them directly with the injected cookies. Full strategy and monkey-patch script: `references/google-flow-api.md`.
