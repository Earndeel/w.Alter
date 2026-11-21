# Reading React internals in Camoufox — the DevTools-hook bypass (verified 2026-08-11)

## Problem this solves

Camoufox's anti-fingerprinting layer strips non-standard own-properties from DOM
elements — including the `__reactFiber$...` markers React attaches. So
`Object.getOwnPropertyNames(el)` returns `[]` and the classic "walk the fiber via
element property" trick is dead on every React SPA.

## The bypass

React registers its roots/renderers on `window.__REACT_DEVTOOLS_GLOBAL_HOOK__`
(the same hook React DevTools extensions use). That hook lives on `window`, not
on DOM elements, so Camoufox's element stripping never touches it. If we install
a minimal hook with `context.add_init_script(...)` BEFORE React loads, React
calls `hook.inject(renderer)` + `hook.onCommitFiberRoot(rendererID, root)`, and
we capture every fiber root directly from the renderer's internal Map / root set.
We then walk the fiber tree from the roots — no element property needed.

## Files (ready to run)

- `~/.hermes/scripts/react-fiber-hook.js` — the init script (idempotent).
  Exposes `window.__REACT_FIBER__` with:
  - `.rootCount`, `.version`
  - `.getElementState(domEl)` -> {props, state, type, key} for a DOM element
  - `.getTree()` -> serializable list of {name, key, props, state, childCount}
  - `.findComponent(substr)` -> first matching component by type name
- `~/.hermes/scripts/camoufox_react_runner.py` — PyCamoufox runner:
  - injects the hook via `add_init_script` (before any page JavaScript)
  - optional `--cookies /tmp/cookies.json`
  - optional French-exit proxy: `--no-proxy` to disable
  - `--dump-tree` prints component inventory + interesting nodes

Honest limitation: this gives you the RENDER tree (props/state of every fiber) —
it does NOT expose React DevTools' `renderer.getFiberRoots` for mutations, nor
React event/interceptor internals. For reading application state (form values,
store snapshots, loaded data) it is the full path.

## Verified results (2026-08-11)

- Excalidraw (`excalidraw.com`): React 19.0.0, 509 fiber nodes, saw MainMenu,
  WelcomeScreen, OverwriteConfirmDialog, the store object (applyDeltas,
  mutateElement, addFiles) — the exact page the old skill marked "impossible".
- OneForma (`my.oneforma.com/center/login`): React 19.2.7, 1 root — and with the
  Camoufox + tinyproxy-HTTP-fr stack the Cloudflare Turnstile challenge does NOT
  block (`cfChallenge: false`). Both capabilities (anti-detect + React read) in
  one browser.

## How to run

```bash
source /root/.hermes/hermes-agent/venv/bin/activate
# one-shot probe, real French exit, cookies injected
python3 ~/.hermes/scripts/camoufox_react_runner.py https://target.com \
  --cookies /tmp/cookies-opp.json
# full component dump
python3 ~/.hermes/scripts/camoufox_react_runner.py https://target.com \
  --cookies /tmp/cookies-opp.json --dump-tree
# no proxy (e.g. already residential / no geo need)
python3 ~/.hermes/scripts/camoufox_react_runner.py https://target.com --no-proxy
```

Notes:
- The hook must be installed via `add_init_script` on the CONTEXT before
  navigation; re-running `page.evaluate(HOOK)` after load is a no-op safety net
  (idempotent guard `if (window.__REACT_FIBER__) return`).
- Camoufox browser binary: install once via `python -m camoufox fetch`
  (cached under ~/.cache/camoufox).
- geoip=False to keep the proxy as the only exit; humanize=True for natural
  timing on Cloudflare-sensitive pages.
