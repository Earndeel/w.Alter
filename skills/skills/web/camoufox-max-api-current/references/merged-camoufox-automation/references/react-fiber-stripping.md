# Camoufox React Fiber Stripping — Test Results

**Date**: 2026-06-13  
**Target**: excalidraw.com collaboration room (React SPA)  
**Browser**: Camoufox-max (Firefox fork) on port 9378  
**Elements tested**: 820 DOM elements

## What Was Tested

| Method | Result | Notes |
|--------|--------|-------|
| `Object.getOwnPropertyNames(el)` | `[]` on all 820 elements | Should return `__reactFiber$xxx`, `__reactContainer$xxx` |
| `Reflect.ownKeys(el)` | `[]` on all 820 elements | Should include symbols |
| `Object.getOwnPropertySymbols(el)` | `[]` on all elements | Should find React internal symbols |
| `for...in` loop | 316 properties (all inherited) | Only standard HTMLElement prototype props |
| `Object.keys()` | 0 own keys | Confirms no enumerable own properties |
| Global `window.__EXCALIDRAW__` | undefined | No global API exposed |
| Module import (`import('excalidraw')`) | loaded but no scene access | Library loads but doesn't expose running instance |
| Clipboard interception | 0 captures | `navigator.clipboard.writeText` hook not triggered |
| Blob constructor override | not triggered | Bundled code caches original Blob reference |
| Download interceptor | no data captured | `URL.createObjectURL` override bypassed |
| IndexedDB inspection | `excalidraw-library-db` (0 items), `files-db` (0 items) | Scene data not persisted locally |
| WebSocket interception | 0 messages captured | Hook installed after WS already connected |

## Key Insight

Camoufox strips ALL non-standard own properties from DOM elements as an anti-fingerprinting measure. This prevents detection of React/Angular/Vue frameworks (which store fiber/component references on DOM nodes). The stripping is thorough — it affects:
- Enumerable properties
- Non-enumerable properties
- Symbol-keyed properties

## Workarounds

1. **Screenshots + vision** — reliable for reading page state
2. **UI automation** (click-at, keyboard-type, keyboard-press) — reliable for interacting
3. **Chromium CDP** (Playwright) — exposes React fibers normally, use when API access is needed

## When to Use Chromium Instead

Use Chromium (via `playwright-cdp-browser-control` or `webtop-chromium-cdp`) when you need to:
- Read React component state programmatically
- Access internal APIs (Excalidraw, Google Docs, etc.)
- Intercept app-generated data (clipboard, downloads)
- Execute code that depends on DOM element properties
