---
name: excalidraw-chromium-bridge
description: "Read/write Excalidraw scenes programmatically via Chromium React fiber traversal. Bridges Camoufox (write via UI) and Chromium (read/write via API)."
version: 1.0.0
author: w-alter
tags: [excalidraw, chromium, react-fiber, playwright, canvas, diagram]
metadata:
  hermes:
    tags: [excalidraw, chromium, react-fiber, playwright, canvas, diagram]
    related_skills: [excalidraw, camoufox-max-server, playwright-cdp-browser-control]
prerequisites:
  commands: [python3, playwright]
---

# Excalidraw Chromium Bridge

Read and write Excalidraw collaborative rooms programmatically by traversing React fiber trees in headless Chromium.

**Support files:**
- `templates/element_helpers.py` — Python factory functions for all element types (rect, text, arrow, ellipse, diamond, line) with color presets
- `references/vite-module-scope-issue.md` — Why Camoufox/Firefox fails and Chromium succeeds (Vite ES module scope isolation)
- `references/mcp-server-comparison.md` — All Excalidraw delivery methods compared (static, ExcaliDash API, MCP server, rooms)
- `references/excalidash-navigation.md` — ExcaliDash SPA navigation patterns for Playwright (URL routing, login flow, zoom-to-fit)

## Why Chromium and not Camoufox?

Excalidraw loads as `<script type="module">` (Vite). Vite wraps React code in ES module scope where `typeof __REACT_DEVTOOLS_GLOBAL_HOOK__` resolves differently than in global scope. React never calls `inject()` on the devtools hook. Chromium exposes React fibers as **own properties** on DOM elements (`Object.getOwnPropertyNames(el)` returns `__reactContainer$xxx`), bypassing the hook entirely.

**Camoufox** does NOT strip DOM properties (tested: custom `__reactFiber$test` persists). The issue is purely the ES module scope isolation.

## Architecture

```
Excalidraw Room (collaborative, E2E encrypted)
    │
    ├─ Chromium (Playwright headless) ── React fiber tree ── API access
    │   ├── READ:  api.getSceneElements()
    │   ├── WRITE: api.updateScene({elements: [...]})
    │   └── STATE: api.getAppState()
    │
    └─ Camoufox (port 9378) ── UI interaction
        ├── READ:  screenshots + vision
        └── WRITE: tool selection + click/type
```

## Fiber Tree Structure

Key objects found at specific depths:

| Depth | Type | Object | Keys |
|-------|------|--------|------|
| ~2 | class component | root wrapper | `props, context, refs, updater, state, _reactInternals` |
| ~5 | hook state | **Scene store** | `updateScene, getSceneElements, mutateElement, applyDeltas, history, scrollToContent, getAppState, getFiles, getName, resetScene, updateLibrary, addFiles` |
| ~15 | class component | **Excalidraw API** (stateNode) | `canvas, interactiveCanvas, scene, fonts, renderer, visibleElements, actionManager, editorInterface, library` |
| ~33 | hook state | Scene data | `app, canvas, elementsMap, visibleElements, selectedElements, allElementsMap, scale, appState, renderConfig, editorInterface` |
| ~39 | class component | **Collab component** (stateNode) | `portal, fileManager, excalidrawAPI, collaborators, isCollaborating, socketInitializationTimer, lastBroadcastedOrReceivedSceneVersion` |

### Portal object (collab.stateNode.portal)

| Key | Type | Description |
|-----|------|-------------|
| `socket` | WebSocket | Active connection |
| `roomId` | string | Room identifier |
| `roomKey` | CryptoKey | E2E encryption key |
| `broadcastScene` | function | `broadcastScene(type, elements, appState)` — sends to server |
| `broadcastIdleChange` | function | Broadcast idle state |
| `broadcastMouseLocation` | function | Cursor sync |
| `broadcastSceneVersions` | object | Element version tracking |
| `queueFileUpload` | function | File upload queue |

## Core Pattern: Find the Excalidraw API

```python
from playwright.sync_api import sync_playwright
import json

def get_excalidraw_api(page):
    """Traverse React fiber tree to find Excalidraw API instance."""
    return page.evaluate("""
    (function(){
        var root = document.getElementById('root');
        var key = Object.getOwnPropertyNames(root).find(function(k){ 
            return k.indexOf('__reactContainer') === 0; 
        });
        if(!key) return null;
        
        var fiber = root[key];
        var api = null;
        
        function find(node, depth) {
            if(!node || depth > 50 || api) return;
            if(node.stateNode && node.stateNode !== document && node.stateNode !== root) {
                if(typeof node.stateNode.getSceneElements === 'function') {
                    api = node.stateNode;
                    return;
                }
            }
            find(node.child, depth + 1);
            find(node.sibling, depth + 1);
        }
        find(fiber.child, 0);
        return api;
    })()
    """
)
def read_scene(page):
    """Read all elements from the Excalidraw scene."""
    return page.evaluate("""
    (function(){
        var root = document.getElementById('root');
        var key = Object.getOwnPropertyNames(root).find(function(k){ 
            return k.indexOf('__reactContainer') === 0; 
        });
        var fiber = root[key];
        var api = null;
        
        function find(node, depth) {
            if(!node || depth > 50 || api) return;
            if(node.stateNode && node.stateNode !== document && node.stateNode !== root) {
                if(typeof node.stateNode.getSceneElements === 'function') { api = node.stateNode; return; }
            }
            find(node.child, depth + 1);
            find(node.sibling, depth + 1);
        }
        find(fiber.child, 0);
        if(!api) return {error: 'API not found'};
        
        return {
            elements: api.getSceneElements(),
            appState: api.getAppState ? api.getAppState() : null
        };
    })()
    """)
```

## Full Workflow — Read + Write (with Persistence)

```python
from playwright.sync_api import sync_playwright
import json, random, time

ROOM_URL = "https://excalidraw.com/#room=<roomId>,<key>"

JS_FIND_STORE_AND_PORTAL = """
var root = document.getElementById('root');
var key = Object.getOwnPropertyNames(root).find(function(k){ return k.indexOf('__reactContainer') === 0; });
var fiber = root[key];
var store = null, portal = null;
function findBoth(n, d) {
    if(!n || d > 60) return;
    if(!store) {
        var hs = n.memoizedState;
        var hi = 0;
        while(hs && hi < 30) {
            var ms = hs.memoizedState;
            if(ms && typeof ms === 'object' && ms !== null && typeof ms.updateScene === 'function') {
                store = ms;
            }
            hs = hs.next;
            hi++;
        }
    }
    if(!portal && n.stateNode && n.stateNode !== document && n.stateNode !== root && typeof n.stateNode === 'object') {
        if(n.stateNode.portal && typeof n.stateNode.portal.broadcastScene === 'function') {
            portal = n.stateNode.portal;
        }
    }
    findBoth(n.child, d+1);
    findBoth(n.sibling, d+1);
}
findBoth(fiber.child, 0);
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(ROOM_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(10000)  # Wait for collab sync

    # READ
    existing = page.evaluate("(" + JS_FIND_STORE_AND_PORTAL + "return store.getSceneElements();)")
    if isinstance(existing, str):
        existing = json.loads(existing)

    # ADD elements
    new_elements = existing + [my_new_element]

    # WRITE + PERSIST (critical: updateScene + broadcastScene)
    els_json = json.dumps(json.dumps(new_elements))
    result = page.evaluate("(function(elsJSON){" + JS_FIND_STORE_AND_PORTAL +
        "store.updateScene({elements: JSON.parse(elsJSON)});" +
        "portal.broadcastScene('SCENE_UPDATE', store.getSceneElements(), store.getAppState());" +
        "return 'updated + broadcasted';" +
    "})(" + els_json + ")")

    page.wait_for_timeout(5000)
    browser.close()
```

### Why BOTH calls are needed

| Call | What it does | Persists? |
|------|-------------|-----------|
| `store.updateScene({elements})` | Updates React state + re-renders canvas | ❌ Local only |
| `portal.broadcastScene('SCENE_UPDATE', elements, appState)` | Sends scene to collab server via WebSocket | ✅ Synced |
| `store.updateScene()` + `portal.broadcastScene()` | Update local + sync to server | ✅ Full persistence |

**Without `broadcastScene`**, elements disappear on next page load. The collab room uses E2E-encrypted WebSocket sync; `updateScene` only touches React state, not the Yjs/CRDT document.

### Helper: Find store only (read-only use)

```python
JS_FIND_STORE = """
var root = document.getElementById('root');
var key = Object.getOwnPropertyNames(root).find(function(k){ return k.indexOf('__reactContainer') === 0; });
var fiber = root[key]; var store = null;
function findStore(n, d) {
    if(!n || d > 60 || store) return;
    var hs = n.memoizedState; var hi = 0;
    while(hs && hi < 30) {
        var ms = hs.memoizedState;
        if(ms && typeof ms === 'object' && ms !== null && typeof ms.updateScene === 'function') { store = ms; return; }
        hs = hs.next; hi++;
    }
    findStore(n.child, d+1); findStore(n.sibling, d+1);
}
findStore(fiber.child, 0);
"""
# Usage: page.evaluate("(" + JS_FIND_STORE + "return store.getSceneElements();)")
```

## Element Properties Reference

Every Excalidraw element has these common fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier |
| `type` | string | `rectangle`, `ellipse`, `diamond`, `text`, `arrow`, `line`, `freedraw`, `image` |
| `x`, `y` | float | Position (top-left corner) |
| `width`, `height` | float | Dimensions |
| `strokeColor` | string | Border color (`#1e1e1e`, `#e03131`, etc.) |
| `backgroundColor` | string | Fill color or `transparent` |
| `fillStyle` | string | `hachure`, `cross-hatch`, `solid` |
| `strokeWidth` | int | 1 (thin), 2 (bold), 4 (extraBold) |
| `roughness` | int | 0 (architect), 1 (artist), 2 (cartoonist) |
| `opacity` | int | 0-100 |
| `angle` | float | Rotation in radians |
| `text` | string | Content (text elements only) |
| `fontSize` | int | 20 (small), 28 (medium), 36 (large), 48 (veryLarge) |
| `fontFamily` | int | 1 (hand-drawn), 2 (normal), 3 (code) |
| `isDeleted` | bool | Soft delete flag |
| `groupIds` | array | Group membership |
| `boundElements` | array | Attached arrows/text |
| `seed` | int | Rough.js random seed |

### Arrow-specific

| Field | Type | Description |
|-------|------|-------------|
| `startBinding` | object | `{elementId, focus, gap}` |
| `endBinding` | object | `{elementId, focus, gap}` |
| `points` | array | `[[x1,y1], [x2,y2]]` relative to element position |
| `startArrowhead` | string | `arrow`, `dot`, `triangle`, or null |
| `endArrowhead` | string | `arrow`, `dot`, `triangle`, or null |

## ExcaliDash API Delivery (Preferred for Live Collaboration)

When ExcaliDash is available (draw.walter-ai.cloud), push diagrams via REST API instead of Chromium fiber traversal. Simpler, no browser dependency, supports multi-board.

**Credentials:** `lucas@walter-ai.cloud` / `«secret:vault»`

**Board registry:** `draw.walter-ai.cloud` → drawing `1bd29c80-2439-4cc8-a92e-7731f48ae0dd` (Hermes Agent Payload Architecture). Use `/editor/{id}` for browser access, NOT `/d/{id}` (broken SPA routing).

```python
import http.client, json, ssl

ctx = ssl.create_default_context()

# CSRF + Login
conn = http.client.HTTPSConnection("draw.walter-ai.cloud", timeout=10, context=ctx)
conn.request("GET", "/api/csrf-token")
resp = conn.getresponse()
csrf = json.loads(resp.read())["token"]
cookie = resp.getheader("Set-Cookie", "").split(";")[0]

conn2 = http.client.HTTPSConnection("draw.walter-ai.cloud", timeout=10, context=ctx)
conn2.request("POST", "/api/auth/login",
    body=json.dumps({"username": "lucas", "password": "«secret:vault»"}),
    headers={"Content-Type": "application/json", "x-csrf-token": csrf, "Cookie": cookie})
resp2 = conn2.getresponse(); resp2.read()
for h in resp2.getheaders():
    if h[0].lower() == "set-cookie": cookie += "; " + h[1].split(";")[0]

# Create drawing
conn3 = http.client.HTTPSConnection("draw.walter-ai.cloud", timeout=15, context=ctx)
conn3.request("POST", "/api/drawings",
    body=json.dumps({"title": "My Diagram", "elements": elements_array}),
    headers={"Content-Type": "application/json", "Cookie": cookie, "x-csrf-token": csrf})
result = json.loads(conn3.getresponse().read().decode())
print(f"https://draw.walter-ai.cloud/d/{result['id']}")
```

**When to use instead of Chromium:**
- User wants instant visual feedback (open link in browser)
- Multi-board organization needed
- No Playwright/Chromium dependency required
- See `references/mcp-server-comparison.md` for full decision matrix

## Pitfalls

1. **Room encryption**: Excalidraw rooms are E2E encrypted. The room key is in the URL hash (`#room=id,key`). Both Chromium and Camoufox must use the full URL with key.

2. **Collab sync delay**: After navigating, wait 8-10 seconds for the WebSocket to sync scene data. Elements may be empty otherwise.

3. **Fiber traversal depth**: The Excalidraw API is typically found at depth 15 in the fiber tree. Max depth 50 is safe.

4. **updateScene replaces ALL elements**: When calling `store.updateScene({elements: [...]})`, you must pass the COMPLETE elements array (existing + new). Passing only new elements will delete existing ones.

5. **updateScene does NOT persist**: `updateScene()` only updates React local state. In collaborative rooms, you MUST call `portal.broadcastScene('SCENE_UPDATE', elements, appState)` after `updateScene()` to sync to the server. Without this, elements vanish on next page load.

6. **Element IDs must be unique**: Use `Date.now()` or random suffixes. Duplicate IDs cause rendering glitches.

7. **Chromium only**: This approach does NOT work in Camoufox/Firefox due to ES module scope isolation. Vite wraps React in `<script type="module">` where `typeof __REACT_DEVTOOLS_GLOBAL_HOOK__` resolves in module scope (not global). React never calls `inject()` on the devtools hook. Chromium bypasses this by exposing fibers as own DOM properties.

8. **Room must be joined**: The browser must successfully join the collaboration room before the API is available. If the room URL has expired or the key is wrong, `getSceneElements()` returns empty.

9. **Store vs API vs Portal**: Three distinct objects in the fiber tree:
   - **Store** (depth ~5, hook state): `updateScene`, `getSceneElements`, `mutateElement`, `applyDeltas`
   - **API** (depth ~15, class stateNode): `canvas`, `scene`, `renderer`, `visibleElements`
   - **Portal** (depth ~39, collab.stateNode.portal): `broadcastScene`, `socket`, `roomId`
   Use **store** for reading/writing, **portal** for persistence.

10. **No appState via getAPI**: `api.getAppState()` may return null on class component instances. Access appState through the fiber's hook state at depth 33, hookIndex 1: `memoizedState.memoizedState.current.appState`. Alternatively, the **store** object (depth ~5) has its own `store.getAppState()` that works reliably.

11. **Collab room accumulates elements — no reliable cleanup**: `resetScene()` only clears local React state, NOT the server-side CRDT document. `isDeleted: true` on elements does NOT persist through the collab server (elements come back on next join). The room merges elements from every session that ever wrote to it. **Consequence**: you cannot "clear and rebuild" a collaborative room. Options:
    - Create a **new room** by navigating to `https://excalidraw.com` (no room hash), injecting elements, then sharing the new room URL
    - Accept accumulated elements and work around them (filter by position bounds, or live with duplicates)
    - Use a **local Excalidraw instance** (no collab) for clean diagram generation, then export

12. **Headless Chromium font rendering — BROKEN for text**: Excalidraw fonts (`Excalifont` for fontFamily 2, `Comic Shanns` for fontFamily 1) are lazy-loaded. In headless Chromium, `canvas.toDataURL()` produces shapes and arrows but **NO TEXT** — `ctx.fillText()` silently renders nothing when fonts aren't loaded. Even after force-loading fonts via `new FontFace().load()`, the canvas does NOT re-render because Excalidraw only paints once per frame. **This is NOT fixable via canvas extraction.** The reliable workaround is **PIL/Pillow rendering** from the JSON elements directly. See `excalidraw` skill `references/pil-render.md` for the full pattern.

13. **Two canvases in Excalidraw**: The app uses two `<canvas>` elements:
    - `canvases[0]` — static layer (elements, shapes, text) — use this for exports
    - `canvases[1]` — interactive layer (selection handles, cursors) — ignore for screenshots
    Both share the same dimensions (matches viewport). Only the static canvas has the final rendered content.

14. **Layout preference**: The user prefers **left-to-right tree layouts** (not top-down hierarchies) for architecture diagrams. Think: `USER → CHANNELS → GATEWAY → CORE → [SKILLS | TOOLS | SERVICES]` with fan-out/fan-in arrows. Use colored boxes per category, monospace for tool names, and solid fills with contrasting stroke colors.

15. **Use FlowChartCreator for proper elbow arrows**: Do NOT manually draw arrows with `points` arrays — they render as smooth curves, NOT elbows. Instead, access `app.flowChartCreator.createNodes(parentEl, appState, 'right', app.scene)` via the fiber tree to create native elbow arrows with `elbowed: true`, `mode: "orbit"`, and `fixedPoint`. The FlowChartCreator computes proper routing via `updateElbowArrowPoints`. Call `app.insertNewElements(pendingNodes)` then `app.flowChartCreator.clear()`. Process: (1) inject root element, (2) select it, (3) call `createNodes` for each branch, (4) then `createNodes` from each branch for leaves. After creation, reposition elements manually to avoid overlap — the FlowChartCreator distributes leaves around the branch center without accounting for other branches' leaves. Use 20px+ gap between leaves (element height is 50px). Fix arrow `points` arrays after repositioning with 4-point elbow routing: `[0,0], [midX,0], [midX,dy], [dx,dy]`.

16. **Text elements bound to FlowChartCreator nodes**: When `FlowChartCreator.createNodes()` creates a rectangle, it does NOT auto-create a bound text element. You must add text separately: create a `type: "text"` element with `containerId` pointing to the rectangle, and add `{id: textId, type: "text"}` to the rectangle's `boundElements` array. Font family 2 (normal/sans-serif) renders cleanly. Use `fontSize: 20` for titles, `fontSize: 14` for leaves.

17. **Dynamic pill sizing for mindmaps**: Never use fixed-width pills — text overflows or wastes space. Formula: `width = int(len(text) * fontSize * 0.58) + 24` (padding). Minimum widths: 200px for branches, 320px for leaves. Heights: 44-50px for standard nodes, 60px for root/title. Compute widths BEFORE layout, then use the max branch width to position the leaf column (`LEAF_X = BRANCH_X + max_branch_w + 40`).

18. **Group labels for visual categories**: To label sections (e.g., "STATIC 28%", "DYNAMIC 72%"), create standalone `type: "rectangle"` elements (NOT connected by arrows) with `opacity: 60`, `strokeWidth: 1`, spanning the group's bounding box. Add a `type: "text"` element at top-left with `textAlign: 'left'`, `fontSize: 13-14`, `opacity: 80`. Position the group rect with 15px padding around the cluster. Use `strokeColor` for the label color (match the category).

19. **Color coding by category with arrow coloring**: Use `strokeColor` (border) as the primary category identifier, `backgroundColor` (fill) for emphasis, `strokeWidth` for importance (1=minor, 2=normal, 3=major). After repositioning, color arrows to match their branch's `strokeColor` — iterate arrows, check `startBinding.elementId`, set `el.strokeColor = branchStroke`. This creates visual cohesion: blue branches → blue arrows, orange → orange, etc.

20. **Self-contained HTML viewer for browser delivery**: To open a mindmap directly in the user's browser (Brave on Mac), create a self-contained HTML file with Excalidraw loaded from CDN, embed the scene elements as inline JSON, SCP to Mac Desktop, and `open` via SSH. Pattern: `<!DOCTYPE html>` + React/ReactDOM/Excalidraw from unpkg CDN + `Excalidraw.Excalidraw` component with `initialData: {elements}`. File size ~155KB for 200+ elements. This bypasses the need for Cloudflare Pages deployment. Camoufox (port 9378) CANNOT be used because Firefox lacks React fiber property access on DOM elements — only Chromium headless can read/write the store programmatically. Workflow: (1) generate .excalidraw JSON via Chromium, (2) build HTML viewer via Python script (NOT write_file — corrupts HTML), (3) `scp` to `~/Desktop/`, (4) `ssh ... "open ~/Desktop/file.html"`.

21. **Playwright page.evaluate single-arg pattern**: `page.evaluate()` in Playwright Python accepts at most 2 positional args (expression, arg). Never pass multiple positional args — use a single dict: `page.evaluate(js, {'color': '#fff', 'w': 200, 'h': 50})` and destructure in JS: `(args) => { args.color, args.w, args.h }`. This applies to ALL page.evaluate calls, not just Excalidraw.

22. **MCP server `create_from_mermaid` needs full frontend**: The canvas-only Docker image (`ghcr.io/yctimlin/mcp_excalidraw-canvas:latest`) supports REST API but NOT Mermaid conversion. Mermaid → Excalidraw requires the full Vite frontend build. For mindmaps, JSON direct with pill nodes and elbow arrows produces better results than Mermaid auto-layout anyway. See `references/mcp-server-comparison.md`.

23. **ExcaliDash API is simpler than Chromium fiber traversal for delivery**: When the goal is "push diagram to user's browser", use ExcaliDash REST API (`POST /api/drawings`) instead of Chromium fiber injection. No Playwright dependency, no font rendering issues, supports multi-board. Credentials: `lucas@walter-ai.cloud` / `«secret:vault»`. See "ExcaliDash API Delivery" section above.

24. **Official Excalidraw Docker (`excalidraw/excalidraw`) is UNUSABLE for headless programmatic scene population**: The official Docker image is a pure client-side React SPA with zero server-side API. Tested 15 distinct approaches — ALL failed to produce reliable headless rendering:

    | Approach | Result | Failure Mode |
    |----------|--------|-------------|
    | React fiber `updateScene()` | 44 elements in store, canvas stays blank | Headless has no collaborative server → React state updates but canvas never re-paints |
    | `scrollToContent()` via fiber API | API not accessible | `excalidrawAPI` prop not reachable via fiber tree walk (depth 0-50) |
    | Clipboard paste via `ClipboardEvent` dispatch | 4/44 elements only | Excalidraw's paste handler clips large payloads |
    | Clipboard paste via `navigator.clipboard.writeText()` + `Ctrl+V` | Canvas stays empty | CDP clipboard write fails silently in headless Chromium |
    | `localStorage` injection | "Loading scene..." forever | Excalidraw reads IndexedDB, not localStorage, for scene data |
    | IndexedDB pre-population | Stuck loading | Format mismatch — Excalidraw's internal IndexedDB schema is undocumented |
    | `updateScene()` + keyboard zoom (`Ctrl+Shift+1`) | Elements in top-left corner | Zoom-to-focus requires React state re-render which doesn't happen headless |
    | Menu "Zoom to fit" | Menu button not findable | `[aria-label="Menu"]` selector doesn't match Excalidraw's hamburger |
    | Font loading + `canvas.toDataURL()` | Shapes render, NO TEXT | Same as pitfall #12 — fonts don't load headless |
    | `reload()` after localStorage set | Same empty state | Excalidraw doesn't re-read localStorage on reload |
    | Multiple page loads | Inconsistent partial renders | Server-side persistence is E2E encrypted WebSocket — Docker has no collab server |

    **Root cause:** The official Docker image runs Excalidraw in "standalone" mode without a collaboration server (Yjs/CRDT). In this mode, `updateScene()` modifies React state but the canvas renderer has no persistence path to trigger a full re-paint. The app expects a human to interact via the real UI. There is NO `loadScene()`, NO server-side API, NO programmatic entry point.

    **Alternatives that DO work:**
    - **ExcaliDash** — REST API, instant board creation (preferred for collaboration)
    - **Excalidraw.com rooms** — Chromium fiber traversal + `broadcastScene()` (pitfall #5)
    - **Static `.excalidraw` files** — JSON → drag-drop on excalidraw.com
    - **HTML viewer** — Self-contained HTML with Excalidraw from CDN (pitfall #20)
    - **PIL/Pillow rendering** — Direct JSON → PNG without browser (pitfall #12)

25. **ExcaliDash SPA routing is broken for deep links — use `/editor/{id}` not `/d/{id}`**: ExcaliDash returns drawing URLs as `/d/{id}` via its API, but the client-side SPA routing redirects `/d/{id}` back to `/` (dashboard). The working URL format is `/editor/{id}`. For Playwright automation: login first, then `page.goto("https://domain/editor/{drawing_id}")`. The login session cookie persists across `page.goto()` calls. Clicking text links on dashboard cards also redirects to `/` — only double-clicking card thumbnails opens drawings (unreliable, may create new empty drawings). See `references/excalidash-navigation.md` for the full Playwright pattern. **Board registry:** `draw.walter-ai.cloud` → drawing `1bd29c80-2439-4cc8-a92e-7731f48ae0dd` (Hermes Agent Payload Architecture).
