---
name: tldraw-diagramming
description: Generate structured diagrams (mindmaps, flowcharts, architecture) in tldraw offline — elbow arrows, layouts, multi-segment connectors.
version: 1.0.0
author: W.Alter (Hermes Agent)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tldraw, diagramming, mindmaps, connectors, arrows]
    category: creative
    related_skills: [tldraw-offline]
---

# tldraw Diagramming

Generate structured diagrams programmatically in the tldraw offline canvas.
Builds on `tldraw-offline` for the HTTP API primitives (token, endpoints,
`/exec`). This skill adds layout patterns, connector techniques, and
diagram-specific pitfalls.

## When to Use

- User asks for a mindmap, flowchart, architecture diagram, or org chart in tldraw
- User wants structured node-and-connector layouts (not freehand drawing)
- User wants right-angle ("elbow") arrows between nodes

**Tool selection rule:** When tldraw offline is already set up and functional
(Agent Skills installed, API reachable, document open), use it for ALL
diagramming tasks. Do NOT fall back to Excalidraw or other tools — the user
invested time in tldraw setup, and switching tools discards that work. The
only time Excalidraw is appropriate is when tldraw is NOT available (app not
installed, API unreachable, tunnel down).

## Elbow Arrows (Right-Angle Connectors)

tldraw does NOT have native `elbowed: true` arrows like Excalidraw. The
`bend` property on `arrow` shapes creates a Bézier curve — not a right angle.
`handles` cannot be passed through `createShape` / `updateShape` (schema
rejects the property).

### Workaround: 3-Segment Straight Arrows

Create three separate `arrow` shapes with `bend: 0` that share endpoints,
forming a right-angle path: **horizontal → vertical → horizontal**.

```
L1 node ──(horizontal)── corner ──(vertical)── corner ──(horizontal)── L2 node
```

```js
const cx = L1_X + L1_W + ELBOW_OFFSET;  // corner X

// Segment 1: horizontal exit from L1
editor.createShape({id: createShapeId('a1'), type:'arrow', x:0, y:0,
  props: {start: {x: L1_right, y: l1_mid_y},
          end:   {x: cx, y: l1_mid_y}, bend:0, color:'black'}});

// Segment 2: vertical drop/rise to L2 level
editor.createShape({id: createShapeId('a2'), type:'arrow', x:0, y:0,
  props: {start: {x: cx, y: l1_mid_y},
          end:   {x: cx, y: l2_mid_y}, bend:0, color:'black'}});

// Segment 3: horizontal entry into L2
editor.createShape({id: createShapeId('a3'), type:'arrow', x:0, y:0,
  props: {start: {x: cx, y: l2_mid_y},
          end:   {x: L2_left, y: l2_mid_y}, bend:0, color:'black'}});
```

All coordinates are absolute (arrows created at `x:0, y:0` with `start`/`end`
in canvas space). Segments share exact endpoints → they touch and form 90°
turns. This is the ONLY reliable way to get right-angle connectors in tldraw
via the API.

The same pattern works for Root → L1 connections in a mindmap.

### Layout Constants for Horizontal Mindmaps

```
ROOT_X=80, ROOT_W=180, ROOT_H=60      # root node (blue)
L1_X=420, L1_W=220, L1_H=50           # level-1 branches
L2_X=800, L2_W=190, L2_H=36           # level-2 leaves
L1_GAP=80, L2_GAP=8                   # vertical spacing
ELBOW_OFFSET=120                       # horizontal gap before first turn
```

Centering: calculate the total height of all branches (L1 + L2 children +
gaps), then position the first branch so the whole tree is centered on the
root node.

### Shape Creation Reference

```js
const {createShapeId, toRichText} = await import('tldraw');

// Pill node (label inside rounded rectangle)
editor.createShape({
  id: createShapeId('node-1'), type: 'geo',
  x: 100, y: 100,
  props: {
    geo: 'rectangle', w: 200, h: 50,
    color: 'black', fill: 'solid',
    richText: toRichText('LABEL')
  }
});
```

- `color` enum: `black grey light-violet violet blue light-blue yellow orange green light-green light-red red white`
- `fill`: `'solid'` | `'none'` | `'semi'`
- Root node: `color:'blue'` to distinguish it
- L1 nodes: `color:'black'`
- L2 nodes: `color:'grey'`

## Pitfalls

- **`bend` is a curve, not an elbow.** Setting `bend` on arrows creates Bézier
  arcs — NOT right angles. Use the 3-segment technique above for true 90° turns.
- **`handles` are rejected by `createShape`.** The arrow `handles` object
  (start/bend/end) is internal to tldraw; passing it in `props` or on the shape
  record causes schema errors. Don't try to inject handles directly.
- **`line` type does not support `endArrowhead`.** It's for freehand drawing,
  not connectors. Use `arrow` type for all connectors.
- **`fontSize` is rejected on `geo` shapes.** Text size is controlled by the
  `size` enum (`'s'`, `'m'`, `'l'`, `'xl'`) on geo props, or by the `fontSizeAdjustment`
  property on `note` shapes. Passing `fontSize` causes "Unexpected property" errors.
- **Don't fall back to Excalidraw.** See tool selection rule above. This is the
  #1 mistake: spending time on tldraw setup then switching tools out of habit.

## Verification

- Screenshot via `api.getScreenshot(docId)` → returns `{ filePath, ... }`
- Copy to VPS with `scp` and inspect with `vision_analyze`
- On headless Mac access: use SSH tunnel `ssh -L 7236:localhost:7236 user@mac-tailscale-ip`
  then query `http://localhost:7236` from VPS
- Store token on Mac: `cat server.json | python3 -c "import json,sys;print(json.load(sys.stdin)['token'])" > /tmp/tldraw_token.txt`
- Read token from VPS: `ssh user@mac 'cat /tmp/tldraw_token.txt'`

## Reference

- `references/elbow-mindmap.py` — complete Python script for a horizontal
  mindmap with 3-segment elbow arrows (7×L1 + 35×L2 + 42 connectors)
