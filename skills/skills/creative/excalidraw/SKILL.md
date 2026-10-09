---
name: excalidraw
description: "Excalidraw JSON diagrams — architecture, flowcharts, mindmaps, sequence. Push to ExcaliDash or excalidraw.com."
version: 1.0.0
author: Hermes Agent
license: MIT
dependencies: []
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Excalidraw, Diagrams, Flowcharts, Architecture, Visualization, JSON]
    related_skills: []

---

# Excalidraw Diagram Skill

Create diagrams by writing standard Excalidraw element JSON and saving as `.excalidraw` files. These files can be drag-and-dropped onto [excalidraw.com](https://excalidraw.com) for viewing and editing. No accounts, no API keys, no rendering libraries -- just JSON.

## When to use

Two modes:
- **Generate** `.excalidraw` files (architecture diagrams, flowcharts, sequence diagrams, concept maps)
- **Interact** with live Excalidraw collaborative rooms (view, draw, edit via camoufox-max)

## Mode 1: Generate .excalidraw Files (Offline)

1. **Write the elements JSON** -- an array of Excalidraw element objects
2. **Save the file** using `write_file` to create a `.excalidraw` file
3. **Optionally upload** for a shareable link using `scripts/upload.py` via `terminal`

### Saving a Diagram

Wrap your elements array in the standard `.excalidraw` envelope and save with `write_file`:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "hermes-agent",
  "elements": [ ...your elements array here... ],
  "appState": {
    "viewBackgroundColor": "#ffffff"
  }
}
```

Save to any path, e.g. `~/diagrams/my_diagram.excalidraw`.

### Uploading for a Shareable Link

Run the upload script (located in this skill's `scripts/` directory) via terminal:

```bash
python skills/diagramming/excalidraw/scripts/upload.py ~/diagrams/my_diagram.excalidraw
```

This uploads to excalidraw.com (no account needed) and prints a shareable URL. Requires the `cryptography` pip package (`pip install cryptography`).

## Mode 2: Live Collaborative Room Interaction (camoufox-max)

Excalidraw rooms (URLs with `#room=ID,KEY`) can be opened, viewed, and interacted with via camoufox-max (port 9378). Requires the camoufox-max server to be running (`curl -s http://localhost:9378/health`).

### Prerequisites
- camoufox-max running on port 9378 (see `devops/camoufox-max-server` skill)
- The `camoufox-max-server` skill for API endpoint reference

### View a Room

```bash
# 1. Create tab
TAB=$(curl -s -X POST http://localhost:9378/tab/new \
  -H "Content-Type: application/json" \
  -d '{"session":"excalidraw"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['tabId'])")

# 2. Navigate to room (include the full #room= fragment)
curl -s -X POST http://localhost:9378/tab/navigate \
  -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"url\":\"https://excalidraw.com/#room=ROOM_ID,ROOM_KEY\"}"

# 3. Wait for room to load and sync (5-8s)
sleep 6

# 4. Screenshot
curl -s -X POST http://localhost:9378/tab/screenshot \
  -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\"}" | python3 -c "
import sys,json,base64
d=json.load(sys.stdin)
open('/tmp/excalidraw_room.png','wb').write(base64.b64decode(d['buffer']))
print('Saved screenshot')
"

# 5. View with vision_analyze
```

### Draw / Edit on the Canvas

Three approaches, from simplest to most powerful:

1. **Tool selection + click-at** — Use Excalidraw's toolbar (select tool, click at coordinates). Good for moving/selection.
2. **keyboard-type / keyboard-press** — Type text into selected elements. Good for labels.
3. **JavaScript evaluate** — Inject elements directly via Excalidraw's internal API. Most powerful but requires understanding the scene state.

### Reading the Scene — API Access Limitation (Critical)

**Camoufox anti-fingerprinting strips ALL React fiber keys from DOM elements.** This means `excalidrawAPI.getSceneElements()`, `updateScene()`, and any React internal state access is **impossible** via camoufox-max. Verified: `Object.getOwnPropertyNames(el)`, `Reflect.ownKeys(el)`, and `Object.getOwnPropertySymbols(el)` all return `[]` on every DOM element (tested on 820+ elements). The `for...in` loop only returns inherited prototype properties (316 standard HTMLElement props, zero React internals).

**What this blocks:**
- Reading scene elements as JSON via `excalidrawAPI.getSceneElements()`
- Injecting elements via `updateScene()` / `setState()`
- Accessing the Zustand store or React component tree
- Reading clipboard data after Ctrl+C (Excalidraw uses async Clipboard API, hooks don't capture)
- Downloading exported files (Blob constructor override is bypassed by bundled code)

**What works:**
- **Screenshots + vision** — zoom-to-fit (`Ctrl+Shift+1` opens export modal; use zoom controls instead), then screenshot + `vision_analyze` to read content
- **UI automation** — tool selection via `aria-label` buttons (e.g. `[aria-label="Text"]`), `click-at` for positioning, `keyboard-type` for text input, `keyboard-press` for shortcuts
- **Menu navigation** — export modal accessible via `Ctrl+Shift+E`, menu via `.main-menu-trigger` click

**For true API access** (reading elements as JSON), use Chromium instead of Camoufox. Chromium exposes React fibers. Run Playwright Chromium as a separate browser and navigate to the room URL. See skill `excalidraw-chromium-bridge` for the full fiber traversal pattern. **Pitfall:** Headless Chromium canvas DOES NOT render text — fonts don't load. Use PIL/Pillow for screenshots.

### Injecting into Collaborative Rooms (Chromium + broadcastScene)

`updateScene()` alone does NOT persist in collaborative rooms. You MUST also call `portal.broadcastScene()`:

```python
page.evaluate("""(function(elsJSON){
    var root = document.getElementById('root');
    var key = Object.getOwnPropertyNames(root).find(function(k){ return k.indexOf('__reactContainer') === 0; });
    var fiber = root[key]; var store = null, portal = null;
    function findBoth(n, d) {
        if(!n || d > 60) return;
        if(!store) { var hs = n.memoizedState; var hi = 0; while(hs && hi < 30) { var ms = hs.memoizedState; if(ms && typeof ms === 'object' && ms !== null && typeof ms.updateScene === 'function') { store = ms; } hs = hs.next; hi++; } }
        if(!portal && n.stateNode && n.stateNode !== document && n.stateNode !== root && typeof n.stateNode === 'object') { if(n.stateNode.portal && typeof n.stateNode.portal.broadcastScene === 'function') { portal = n.stateNode.portal; } }
        findBoth(n.child, d+1); findBoth(n.sibling, d+1);
    }
    findBoth(fiber.child, 0);
    store.updateScene({elements: JSON.parse(elsJSON)});
    if(portal) portal.broadcastScene('SCENE_UPDATE', store.getSceneElements(), store.getAppState());
})"""+ json.dumps(json.dumps(elements)) +")")
```

**Pitfall:** Collaborative rooms MERGE elements — they never fully replace. `resetScene()` and `isDeleted: true` do NOT persist. Old elements come back. For a clean diagram, either:
1. Create a NEW room (fresh excalidraw.com page, no #room= fragment)
2. Or use the upload script to generate a shareable JSON link

### Shareable Link (No Room Needed)

Use the upload script to get a clean shareable URL:
```bash
python3 skills/creative/excalidraw/scripts/upload.py diagram.excalidraw
# Returns: https://excalidraw.com/#json=XXX,YYY
```

This creates a clean link with no room merging issues. The `.excalidraw` file can also be drag-and-dropped onto excalidraw.com.

### Pitfalls

- **ALWAYS follow this skill's conventions** — do NOT improvise element structure. The user will reject diagrams that don't follow the style rules below (roughness:0, fontFamily:2, container binding, pill nodes). When building any Excalidraw diagram, load this skill first.
- **Room sync takes 5-8 seconds** after navigation. Screenshotting too early shows empty canvas.
- **Excalidraw is a React SPA** — complex DOM queries may timeout. Prefer screenshots + vision for layout understanding.
- **Canvas coordinates ≠ viewport coordinates** — elements may be zoomed/panned. Use annotated screenshots to find exact positions.
- **No undo from outside** — changes made via camoufox-max are committed to the room. There's no easy undo.
- **Room key is sensitive** — anyone with the full URL can edit. Don't log room keys in shared outputs.
- **No programmatic scene reading via Camoufox** — React fibers are stripped. See "Reading the Scene" section above. Don't waste time trying `Object.getOwnPropertyNames`, `Reflect.ownKeys`, or `Object.getOwnPropertySymbols` — they all return empty arrays.
- **Export modal ≠ zoom-to-fit** — `Ctrl+Shift+E` opens the export dialog, not zoom-to-fit. Use zoom controls or scroll-to-content button instead.
- **Hermes native browser (port 9377) may be off** — use camoufox-max (port 9378) directly. The `browser_navigate` tool connects to 9377 and will fail if the native browser isn't running.
- **Headless Chromium canvas DOES NOT render text** — Excalidraw's canvas renderer needs custom fonts (Excalifont, Virgil, Cascadia) loaded. In headless Chromium, fonts don't load, so `canvas.toDataURL()` produces shapes and arrows but NO TEXT. Even after loading fonts via `FontFace.load()`, the canvas doesn't re-render text. **Workaround:** Render using PIL/Pillow directly from the JSON elements (see `references/pil-render.md`). This is the reliable path for screenshots.
- **JSON links trigger "Replace my content" modal** — Navigating to `https://excalidraw.com/#json=XXX,YYY` shows a modal asking to replace existing content. Click `document.querySelectorAll('button')` and find "Replace my content" to proceed. Room links (`#room=`) don't have this issue.
- **TUI URLs are not clickable** — Links sent in the Hermes TUI appear as underlined text but are NOT clickable. To share diagrams with the user: (1) open in Camoufox so they see it directly, (2) send via Telegram, or (3) render as PNG and show via `vision_analyze`/`MEDIA:` tag.
- **Collaborative rooms CANNOT be cleaned** — `resetScene()`, `isDeleted: true`, and `mutateElement` deletions do NOT persist. The Yjs CRDT server merges back old elements. For a clean diagram: create a fresh page (no `#room=` fragment), or use the upload script for a JSON link.
- **`roughness: 0` for clean/straight lines** — Default `1` gives hand-drawn wobbly look. Set `0` for professional diagrams.
- **Mindmap layout: PIL rendering works well** — For mindmaps with a central hub and branches, generate the `.excalidraw` JSON then render via PIL/Pillow for a clean PNG with text. See `references/pil-render.md`.
- **Mindmap layout: prevent L2 overlap** — When a branch has many children (e.g. 14 toolsets), L2 nodes from adjacent branches can collide. Calculate each branch's total height (`NODE_H + gap + n_children * SMALL_H + (n_children-1) * child_gap`), add a fixed `BRANCH_GAP` between branches, and position L1/L2 relative to the branch block, not just the L1 node. Always render a PIL preview to verify no overlap before pushing.

## Mode 3: Push to Self-Hosted ExcaliDash

When ExcaliDash is deployed (see `references/excalidash-self-hosted.md`), diagrams can be pushed directly as new boards via the API. This gives a collaborative, editable URL without excalidraw.com.

**Workflow:** Build `.excalidraw` JSON → Login via API → POST `/api/drawings` → Share `https://domain/d/{id}`.

Full code pattern and cookie management in `references/excalidash-self-hosted.md` under "Creating Drawings via API".

**When to use:** User has ExcaliDash running and wants collaborative editing. Prefer this over upload.py for self-hosted setups.

---

## Element Format Reference

### Required Fields (all elements)
`type`, `id` (unique string), `x`, `y`, `width`, `height`

### Defaults (skip these -- they're applied automatically)
- `strokeColor`: `"#1e1e1e"` (black borders — user preference)
- `backgroundColor`: `"transparent"`
- `fillStyle`: `"solid"`
- `strokeWidth`: `2`
- `roughness`: `0` (clean/straight lines — user prefers NO hand-drawn wobble)
- `opacity`: `100`
- `roundness`: `{ "type": 3 }` for rounded corners on all rectangles — user preference
- `fontFamily`: `2` (Normal/classic sans-serif — user preference, NOT Virgil hand-drawn)

Canvas background is white.

### Element Types

**Rectangle**:
```json
{ "type": "rectangle", "id": "r1", "x": 100, "y": 100, "width": 200, "height": 100 }
```
- `roundness: { "type": 3 }` for rounded corners
- `backgroundColor: "#a5d8ff"`, `fillStyle: "solid"` for filled

**Ellipse**:
```json
{ "type": "ellipse", "id": "e1", "x": 100, "y": 100, "width": 150, "height": 150 }
```

**Diamond**:
```json
{ "type": "diamond", "id": "d1", "x": 100, "y": 100, "width": 150, "height": 150 }
```

**Labeled shape (container binding)** -- create a text element bound to the shape:

> **WARNING:** Do NOT use `"label": { "text": "..." }` on shapes. This is NOT a valid
> Excalidraw property and will be silently ignored, producing blank shapes. You MUST
> use the container binding approach below.

The shape needs `boundElements` listing the text, and the text needs `containerId` pointing back:
```json
{ "type": "rectangle", "id": "r1", "x": 100, "y": 100, "width": 200, "height": 80,
  "roundness": { "type": 3 }, "backgroundColor": "#a5d8ff", "fillStyle": "solid",
  "boundElements": [{ "id": "t_r1", "type": "text" }] },
{ "type": "text", "id": "t_r1", "x": 105, "y": 110, "width": 190, "height": 25,
  "text": "Hello", "fontSize": 20, "fontFamily": 1, "strokeColor": "#1e1e1e",
  "textAlign": "center", "verticalAlign": "middle",
  "containerId": "r1", "originalText": "Hello", "autoResize": true }
```
- Works on rectangle, ellipse, diamond
- Text is auto-centered by Excalidraw when `containerId` is set
- The text `x`/`y`/`width`/`height` are approximate -- Excalidraw recalculates them on load
- `originalText` should match `text`
- `fontFamily`: `1` = Virgil (hand-drawn, default), `2` = Normal (classic/clean sans-serif), `3` = Cascadia (monospace). User preference: **use `2` for clean professional diagrams.**

**Labeled arrow** -- same container binding approach:
```json
{ "type": "arrow", "id": "a1", "x": 300, "y": 150, "width": 200, "height": 0,
  "points": [[0,0],[200,0]], "endArrowhead": "arrow",
  "boundElements": [{ "id": "t_a1", "type": "text" }] },
{ "type": "text", "id": "t_a1", "x": 370, "y": 130, "width": 60, "height": 20,
  "text": "connects", "fontSize": 16, "fontFamily": 1, "strokeColor": "#1e1e1e",
  "textAlign": "center", "verticalAlign": "middle",
  "containerId": "a1", "originalText": "connects", "autoResize": true }
```

**Standalone text** (titles and annotations only -- no container):
```json
{ "type": "text", "id": "t1", "x": 150, "y": 138, "text": "Hello", "fontSize": 20,
  "fontFamily": 1, "strokeColor": "#1e1e1e", "originalText": "Hello", "autoResize": true }
```
- `x` is the LEFT edge. To center at position `cx`: `x = cx - (text.length * fontSize * 0.5) / 2`
- Do NOT rely on `textAlign` or `width` for positioning

**Arrow**:
```json
{ "type": "arrow", "id": "a1", "x": 300, "y": 150, "width": 200, "height": 0,
  "points": [[0,0],[200,0]], "endArrowhead": "arrow" }
```
- `points`: `[dx, dy]` offsets from element `x`, `y`
- `endArrowhead`: `null` | `"arrow"` | `"bar"` | `"dot"` | `"triangle"`
- `strokeStyle`: `"solid"` (default) | `"dashed"` | `"dotted"`

### Arrow Bindings (connect arrows to shapes)

```json
{
  "type": "arrow", "id": "a1", "x": 300, "y": 150, "width": 150, "height": 0,
  "points": [[0,0],[150,0]], "endArrowhead": "arrow",
  "startBinding": { "elementId": "r1", "fixedPoint": [1, 0.5] },
  "endBinding": { "elementId": "r2", "fixedPoint": [0, 0.5] }
}
```

`fixedPoint` coordinates: `top=[0.5,0]`, `bottom=[0.5,1]`, `left=[0,0.5]`, `right=[1,0.5]`

> **CRITICAL — bidirectional binding:** It's NOT enough to set `startBinding`/`endBinding` on the arrow. You MUST ALSO add the arrow's ID to `boundElements` on BOTH the source and target shapes. Without this, the arrow renders but is NOT attached — moving the shape won't move the arrow. Excalidraw requires both sides of the binding.
>
> ```json
> // Shape with both text AND arrow in boundElements:
> { "type": "rectangle", "id": "r1", ...,
>   "boundElements": [
>     { "id": "t_r1", "type": "text" },
>     { "id": "a1", "type": "arrow" }     // ← MUST list the arrow too
>   ] }
> // Arrow with bindings:
> { "type": "arrow", "id": "a1", ...,
>   "startBinding": { "elementId": "r1", "focus": 0, "gap": 8 },
>   "endBinding": { "elementId": "r2", "focus": 0, "gap": 8 } }
> ```
>
> **Pattern:** After generating all arrows, iterate over them and append each arrow's ID to `boundElements` of its `startBinding.elementId` and `endBinding.elementId`.

### Drawing Order (z-order)
- Array order = z-order (first = back, last = front)
- Emit progressively: background zones → shape → its bound text → its arrows → next shape
- BAD: all rectangles, then all texts, then all arrows
- GOOD: bg_zone → shape1 → text_for_shape1 → arrow1 → arrow_label_text → shape2 → text_for_shape2 → ...
- Always place the bound text element immediately after its container shape

### Sizing Guidelines

**Font sizes:**
- Minimum `fontSize`: **16** for body text, labels, descriptions
- Minimum `fontSize`: **20** for titles and headings
- Minimum `fontSize`: **14** for secondary annotations only (sparingly)
- NEVER use `fontSize` below 14

**Element sizes:**
- Minimum shape size: 120x60 for labeled rectangles/ellipses
- Leave 20-30px gaps between elements minimum
- Prefer fewer, larger elements over many tiny ones

### Color Palette

See `references/colors.md` for full color tables. Quick reference:

| Use | Fill Color | Hex |
|-----|-----------|-----|
| Primary / Input | Light Blue | `#a5d8ff` |
| Success / Output | Light Green | `#b2f2bb` |
| Warning / External | Light Orange | `#ffd8a8` |
| Processing / Special | Light Purple | `#d0bfff` |
| Error / Critical | Light Red | `#ffc9c9` |
| Notes / Decisions | Light Yellow | `#fff3bf` |
| Storage / Data | Light Teal | `#c3fae8` |

### Tips
- Use the color palette consistently across the diagram
- **Text contrast is CRITICAL** -- never use light gray on white backgrounds. Minimum text color on white: `#757575`
- Do NOT use emoji in text -- they don't render in Excalidraw's font
- For dark mode diagrams, see `references/dark-mode.md`
- For larger examples, see `references/examples.md`
- For self-hosted ExcaliDash (multi-board + auth + collaboration), see `references/excalidash-self-hosted.md`
- For horizontal mindmap layouts with pill nodes and curved elbow arrows, see `references/mindmap-layout.md`


