# Vite ES Module Scope Issue

## Problem
Excalidraw loads React via `<script type="module">` (Vite). Vite wraps React code in ES module scope where `typeof __REACT_DEVTOOLS_GLOBAL_HOOK__` resolves in the module's local scope rather than `window` global. React's `inject()` is never called, so devtools-based fiber access fails.

## What was tried (all failed for fiber access)
1. **`page.addInitScript()`** — Sets `window.__REACT_DEVTOOLS_GLOBAL_HOOK__` before bundle loads. Hook IS present and accessible, but React inside the module scope doesn't call `inject()`. Confirmed: `typeof` returns `"object"` at window level but React code inside the Vite module wrapper sees it differently.

2. **`page.route()` for bundle interception** — Pattern `**/*.js` doesn't match Vite's module URLs. The `fF="...chunk-HASH.js"` filename in the source suggests hashed chunk loading that bypasses simple glob patterns.

3. **React Fiber `Object.getOwnPropertyNames(el)` in Firefox/Camoufox** — Works for custom properties (tested: `__reactFiber$test` persists), but Vite's production build doesn't expose `__reactContainer$xxx` as an own property in Firefox. Only Chromium does.

## What works
- **Chromium + `Object.getOwnPropertyNames(root)`**: Returns `__reactContainer$if9ywdnij5c` (or similar hash). This IS an own property in Chromium's Vite build.
- **Fiber tree traversal**: Once you have the container fiber, standard React fiber tree walking works: `node.child`, `node.sibling`, `node.memoizedState`.

## Key insight
The issue is NOT anti-fingerprinting (Camoufox preserves DOM properties). It's NOT a devtools hook timing issue (hook is set before module load). It IS a Vite ES module scoping issue where the React bundle's `typeof __REACT_DEVTOOLS_GLOBAL_HOOK__` check resolves in module scope rather than global scope, and Chromium's own-property exposure bypasses this entirely.
