---
name: camoufox-max-variant
description: Manage the standalone camoufox-max stealth server (variant B at /root/.hermes/camoufox-max/) — recovery from a stripped checkout, persistent service unit, and how to tell it apart from the gateway-bundled @askjo/camofox-browser variant.
metadata:
  hermes:
    related_skills: [hermes-camoufox-setup, hermes-gateway-systemd-debug, anti-bot-navigation]
---

# Camoufox MAX Variant

Sister skill to `hermes-camoufox-setup`. That skill covers the gateway-bundled `@askjo/camofox-browser` server. This skill covers the second, separate **camoufox-max** stealth server. They serve different purposes and have different package layouts — the most common operator mistake is conflating them.

## Two variants at a glance

| Variant | Location | npm module | Purpose | Lifecycle |
|---|---|---|---|---|
| **A** (gateway) | `node_modules/@askjo/camofox-browser/server.js` | `@askjo/camofox-browser` (typo: one 'u') | Default `browser_*` tool backend, replaces Browserbase | Spawned by Hermes gateway when `CAMOFOX_URL` is configured |
| **B** (max) | `/root/.hermes/camoufox-max/server-max.js` | `camoufox-js` directly | Ultra-stealth scraping (humanize 2.0, geoip, persistent context) | Independent, runs as its own service |

The two have **different APIs**. Variant B uses `/health`, `/session/new`, `/tab/new`, `/tab/navigate`, `/tab/click`, `/tab/type`, `/tab/scroll`, `/tab/screenshot`, `/tab/snapshot`, `/tab/close`. Don't try to call variant B endpoints on variant A's port or vice versa.

## When to reach for variant B

- Sites with strict fingerprinting (DataDome, Cloudflare strict, social platforms) where you want native humanize patterns built into the engine, not bolted on via Playwright
- Long-running scraping sessions that should survive Hermes gateway restarts
- Workflows where `geoip: true` matters (residential exit IP must match the spoofed locale)
- Cases where the gateway is masked or in recovery and you still need stealth browsing

If the task is generic browsing for a tool call, prefer variant A — it's already wired to the `browser_*` tools.

## Pitfall — directory loses its dependencies after checkout cleanup

The most common breakage: `~/.hermes/camoufox-max/` ends up containing **only `server-max.js`**, with no `package.json`, no `node_modules/`, and no `lib/macros.js`. Common triggers: rsync from a clean machine, `npm prune`, repo reset, manual housekeeping.

Symptoms when starting the server:

```
Error: Cannot find module 'camoufox-js'
Error: Cannot find module './lib/macros'
```

The `humanize: 2.0`, `geoip: true`, `persistent_context: true` configuration lives directly in `server-max.js` (around the `launchOptions({...})` call). That single file is the only thing that survives cleanups, but it can't run by itself.

## Recovery procedure (verified 2026-06-06)

1. Change into the directory:

   ```
   cd /root/.hermes/camoufox-max
   ```

2. If `package.json` is missing, recreate it. The minimum dependency set is `camoufox-js`, `playwright-core`, `express`, `dotenv`. Pin to the versions documented in `references/recovery-files.md`.

3. Run `npm install --no-audit --no-fund` to populate `node_modules/`.

4. If `lib/macros.js` is missing, recreate it. It's a tiny URL-expansion helper — see `references/recovery-files.md` for the exact passthrough implementation. The function name is `expandMacro` and it's required by the navigate handler.

5. Smoke-test the server before service-ing it:

   ```
   CAMOFOX_MAX_PORT=9377 node server-max.js
   ```

   Expect a single line on stdout starting with `Camoufox MAX server running on port 9377`. Ctrl-C once you've seen it.

6. Hand off to systemd via the unit template in `templates/camoufox-max.service`. Enable, start, then health-check.

## Persistent service

Use `templates/camoufox-max.service` as the unit file. After installing it under `/etc/systemd/system/`:

```
systemctl daemon-reload
systemctl enable --now camoufox-max.service
curl -sS http://localhost:9377/health
```

Healthy response includes `"ok": true`, `"flavor": "max"`, `"humanize": 2`, `"geoip": true`, `"persistent_context": true`. If `humanize` comes back as something else, the patched `server-max.js` was overwritten by an old copy.

## Why a separate service rather than relying on the gateway

Variant A is spawned at `hermes gateway run` time. When the gateway is masked (`Start request repeated too quickly`, see `hermes-gateway-systemd-debug`) or running via a manual replacement, variant A may not start cleanly. Variant B with its own service unit is **independent of the gateway** — stealth scraping survives gateway restarts and gateway-mask states. This is the preferred wiring on the W.Alter VPS.

## Stack lineage — exit IP

When the host VPS uses Tailscale exit node = Mac, variant B traffic exits via the Mac's residential IP. The `geoip: true` flag bakes this assumption in: the residential IP keeps the geoip-based fingerprint consistent with a real macOS user. Verify with `curl -sS https://ifconfig.me` before running stealth-sensitive sessions; if it returns the VPS IP, the exit node is down.

## Stability Patches (verified 2026-06-10)

### `snapshot()` null crash
`page.accessibility.snapshot()` returns `null` or `undefined` on SPAs in loading state or pages with no accessibility tree. The `walk()` recursive function crashes on `node.children.forEach(...)`. Guard: `if (!node || !node.children) return result;` at the top of `walk()`. Also wrap the snapshot call itself: `const snap = await page.accessibility.snapshot().catch(() => null); if (!snap) return res.json({ snapshot: '', refs: {} });`.

### Playwright Firefox `pageError.location.url` crash
Playwright's internal error handler accesses `pageError.location.url` which can be undefined in Firefox, causing an uncaught exception that crashes the Node process. Fix: `process.on('uncaughtException', (err) => { if (err.message?.includes('Cannot read properties of undefined')) { console.error('[camoufox-max] Suppressed Playwright internal error:', err.message); return; } console.error(err); process.exit(1); });`. Also add `page.on('pageerror', () => {})` to suppress page-level errors from propagating.

### New endpoints added (2026-06-10)

**`POST /tab/evaluate`** — Execute arbitrary JavaScript in page context. Essential for React SPAs where standard click/type APIs fail.

```json
{"userId": "walter", "sessionKey": "aws", "expression": "document.querySelector('input').value = 'test'"}
```

Response: `{"result": <evaluated_value>}`. Uses `page.evaluate(expression)` under the hood. Expression must be a valid JS expression string.

**`POST /session/cookies`** — Inject cookies directly into the active page's browser context (bypasses storage-state.json). Useful for mid-session cookie refresh without restarting the server.

```json
{"cookies": [{"name": "session", "value": "abc123", "domain": ".example.com", "path": "/"}]}
```

Response: `{"ok": true, "count": N}`. Calls `context.addCookies()` on the existing browser context.

## React SPA Input Pattern

AWS Console, Facebook, and other React SPAs don't respond to standard DOM value setting. Use the `nativeInputValueSetter` pattern:

```javascript
const nativeSetter = Object.getOwnPropertyDescriptor(
  window.HTMLInputElement.prototype, 'value'
).set;
const input = document.querySelector('input[type="text"]');
nativeSetter.call(input, 'desired value');
const tracker = input._valueTracker;
if (tracker) tracker.setValue('');
input.dispatchEvent(new Event('input', { bubbles: true }));
```

See `webtop-authenticated-browsing` skill → `references/react-spa-input-patterns.md` for full details (textarea, select, AWS-specific patterns).

## Pitfalls

1. **Path collision with variant A** — both can default to port 9377. If variant A is also configured, pick distinct ports and document them.
2. **Don't `apt remove` Node.js** — both variants share the host Node runtime. Removing it kills both.
3. **`server-max.js` is hand-patched** — `humanize: 2.0` lives in code, not config. After any update, diff the file against your last known-good copy and re-apply if needed.
4. **`lib/macros.js` may need to expand more macros over time** — the recovery stub is a passthrough that only adds `https://` to bare hostnames. If real macro expansion was used in the original (e.g. `@google_search`), the stub will break those URLs silently. Check `git log` of the directory if you have history.
5. **`/data` and `~/.camoufox-max-data`** — `persistent_context: true` writes session state to disk. Don't delete this directory casually; cookies and storage live there.

## Verification checklist

- `curl -sS http://localhost:9377/health` returns the healthy JSON shape above
- `systemctl is-active camoufox-max.service` returns `active`
- `systemctl is-enabled camoufox-max.service` returns `enabled`
- The Mac exit IP is what `https://ifconfig.me` reports from the VPS
- Variant A on its own port (if used) is also responding, separately
