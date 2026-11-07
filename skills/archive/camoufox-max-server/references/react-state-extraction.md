# React State Extraction via Camoufox

Extract internal React state from web apps using Camoufox browser automation. Covers React fiber traversal, devtools hook injection, and Vite module scope pitfalls.

## Approach 1: React Fiber Tree Traversal

React 16+ attaches internal fiber nodes to DOM elements. Traverse them to reach the component's state/props.

```javascript
function getReactState(element) {
  // Find the internal React key (varies by React version)
  var fiberKey = Object.keys(element).find(
    k => k.startsWith('__reactFiber$') || k.startsWith('__reactInternalInstance$')
  );
  if (!fiberKey) return null;

  var fiber = element[fiberKey];

  // Walk up to find the nearest component with state
  var current = fiber;
  for (var i = 0; i < 15; i++) {
    if (!current) break;
    // React 19+ uses memoizedState
    if (current.memoizedState && current.memoizedState.memoizedState) {
      return current.memoizedState;
    }
    if (current.memoizedProps && Object.keys(current.memoizedProps).length > 1) {
      return { props: current.memoizedProps };
    }
    current = current.return;
  }
  return null;
}

// Usage: find any element inside the target component
var el = document.querySelector('.some-class');
var state = getReactState(el);
```

### Finding the Fiber Key

The key name varies: `__reactFiber$XXXXX`, `__reactInternalInstance$XXXXX`, `__reactEvents$XXXXX`. Use `Object.getOwnPropertyNames(element)` to discover all keys.

**Camoufox note**: Unlike standard Firefox, Camoufox preserves custom properties on DOM elements. Fiber keys are accessible via `Object.getOwnPropertyNames()`.

## Approach 2: __REACT_DEVTOOLS_GLOBAL_HOOK__ (Pre-Load Injection)

React checks for this global hook at startup. If found, it calls `hook.inject(renderer)` which gives access to the fiber tree via `hook.renderers`.

### Installation via addInitScript

```bash
# Must be set BEFORE page navigation
curl -s -X POST http://localhost:9378/tab/add-init-script \
  -H "Content-Type: application/json" \
  -d '{"tabId":"...","script":"window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {inject: function(r) { window.__RD_RENDERERS = window.__RD_RENDERERS || []; window.__RD_RENDERERS.push(r); }, onCommitFiberRoot: function() {}, onCommitFiberUnmount: function() {}, isDisabled: false, supportsFiber: true};"}'
```

### Checking if React Registered

```javascript
JSON.stringify({
  renderers: (window.__RD_RENDERERS || []).length,
  fiber: !!window.__RD_RENDERERS?.[0]?.findFiberByHostInstance,
  version: window.__RD_RENDERERS?.[0]?.version
});
```

### ⚠️ CRITICAL PITFALL: Vite `type="module"` Bundles

**Most modern web apps use Vite/webpack with `<script type="module">`.** This creates an ES module scope that shadows the global `__REACT_DEVTOOLS_GLOBAL_HOOK__`.

**Symptoms**:
- `typeof __REACT_DEVTOOLS_GLOBAL_HOOK__` returns `"object"` (correct)
- `window.__REACT_DEVTOOLS_GLOBAL_HOOK__` exists with all properties (correct)
- BUT `renderers: 0` — React never calls `inject()`

**Root cause**: Vite bundles wrap React code in an ES module scope. The `typeof __REACT_DEVTOOLS_GLOBAL_HOOK__` check inside the module resolves to the module's own scope chain, not `window`. Even though the hook exists on `window`, the module-scoped React code may not see it or may resolve it differently.

**Verified on**: Excalidraw (React 19, Vite bundle, `type="module"`), confirmed hook installed but `inject()` never called, 0 renderers.

**Workarounds**:
1. **Route interception** — Use `page.route()` to modify the bundle in-flight, injecting hook code INSIDE the module scope
2. **Screenshot + UI automation** — Fall back to visual reading when state extraction fails
3. **Playwright CDP with Chromium** — Chromium exposes fibers natively via `getEventListeners()` and DevTools protocol (Camoufox is Firefox-based, limited fiber access)

## Approach 3: Excalidraw-Specific Patterns

Excalidraw stores its scene state in React context/state, not on `window` or in the DOM. No global `excalidrawAPI` or `__EXCALIDRAW_STATE__` exists.

### What Works (Read + Write)

- **Read canvas**: Screenshot via `/tab/screenshot` + vision analysis
- **Write to canvas**: UI automation — select tools, click, type text, draw shapes
- **Export via menu**: Click hamburger menu → Export → triggers download
- **Element count**: `document.querySelectorAll('[data-testid]')` — Excalidraw marks UI elements with test IDs

### What Doesn't Work

- `window.excalidrawAPI` — does not exist
- `JSON.stringify(els)` — no `els` global
- React fiber traversal — fibers exist on DOM elements but state is deeply nested in React 19's concurrent features
- Devtools hook injection — blocked by Vite module scope (see above)
- `page.route()` bundle modification — URL pattern matching may not catch the bundle URL

### Excalidraw Collaboration Protocol

Excalidraw uses WebSocket for real-time collaboration (`wss://json.excalidraw.com`). The scene state syncs via CRDT-like protocol. Intercepting the WebSocket messages could theoretically capture the full scene, but the protocol is custom and undocumented.

## General Recommendations

| App Type | Best Approach |
|---|---|
| React 16-17, non-Vite | Devtools hook injection (addInitScript) |
| React 18-19, Vite/webpack module | Route interception + bundle modification |
| React with global state (Redux DevTools) | `window.__REDUX_DEVTOOLS_EXTENSION__` |
| Canvas-based apps (Excalidraw, Figma) | Screenshot + UI automation |
| Apps with export API | Call export API directly via evaluate |
