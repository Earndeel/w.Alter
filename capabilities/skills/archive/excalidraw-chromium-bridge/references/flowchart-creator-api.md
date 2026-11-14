# FlowChartCreator API — Native Elbow Arrows in Excalidraw

## Why use it

Excalidraw's native mindmap system (CMD+Right Arrow) creates elbow-routed arrows with `elbowed: true`, `mode: "orbit"`, and `fixedPoint` bindings. **Manually injecting arrow elements produces smooth curves, NOT elbows** — the routing is computed at creation time by `updateElbowArrowPoints`, not at render time.

## Access via Fiber Tree

```javascript
// Find store + app in fiber tree
const root = document.getElementById('root');
const key = Object.getOwnPropertyNames(root).find(k => k.startsWith('__reactContainer'));
let fiber = root[key];
let store = null, app = null;

function findBoth(node, depth) {
    if (!node || depth > 60) return;
    let hs = node.memoizedState, hi = 0;
    while (hs && hi < 30) {
        let ms = hs.memoizedState;
        if (ms && typeof ms === 'object' && ms !== null && typeof ms.updateScene === 'function') store = ms;
        hs = hs.next; hi++;
    }
    if (node.stateNode && node.stateNode !== document && node.stateNode !== root && node.stateNode.flowChartCreator) app = node.stateNode;
    findBoth(node.child, depth + 1);
    findBoth(node.sibling, depth + 1);
}
findBoth(fiber.child, 0);
```

## Create a child node with elbow arrow

```javascript
// 1. Inject parent element into scene
store.updateScene({elements: [parentElement]});
app.setState({selectedElementIds: {[parentElement.id]: true}});

// 2. Call FlowChartCreator
app.flowChartCreator.createNodes(parentElement, app.state, 'right', app.scene);

// 3. Insert pending nodes (child rect + elbow arrow)
const pending = app.flowChartCreator.pendingNodes;
app.insertNewElements(pending);

// 4. Clear creator state
app.flowChartCreator.clear();
```

## After creation: reposition to avoid overlap

The FlowChartCreator distributes leaves around the branch center WITHOUT accounting for other branches' leaves. You must reposition manually:

```python
# Compute positions with proper gaps
NODE_H = 50  # actual element height
LEAF_GAP = 20  # minimum gap between leaves
BRANCH_GAP = 50  # gap between leaf clusters

# For each branch, compute cluster height
for branch in branches:
    n = len(branch.leaves)
    cluster_h = n * NODE_H + (n - 1) * LEAF_GAP
    # Position branch at center of its cluster
    branch_y = cur_y + cluster_h / 2 - BRANCH_H / 2
    # Position leaves evenly
    for i, leaf in enumerate(leaves):
        leaf_y = cur_y + i * (NODE_H + LEAF_GAP)
    cur_y += cluster_h + BRANCH_GAP
```

## Fix arrow points after repositioning

```python
for arrow in arrows:
    src = rects[arrow.startBinding.elementId]
    tgt = rects[arrow.endBinding.elementId]
    
    sx = src.x + src.width  # right edge of source
    sy = src.y + src.height / 2
    ex = tgt.x              # left edge of target
    ey = tgt.y + tgt.height / 2
    
    dx, dy = ex - sx, ey - sy
    
    # 4-point elbow routing
    if abs(dx) > 30 and abs(dy) > 8:
        mid_x = dx * 0.5
        arrow.points = [[0,0], [mid_x,0], [mid_x,dy], [dx,dy]]
    elif abs(dy) <= 8:
        arrow.points = [[0,0], [dx,0]]
    else:
        arrow.points = [[0,0], [0,dy], [dx,dy]]
    
    arrow.x, arrow.y = sx, sy
    arrow.width, arrow.height = dx, dy
```

## Adding text to FlowChartCreator nodes

`createNodes()` does NOT auto-create bound text elements. Add text separately:

```javascript
const textEl = {
    id: 'txt_' + rect.id,
    type: 'text',
    x: rect.x + rect.width/2 - textWidth/2,
    y: rect.y + rect.height/2 - 10,
    width: textWidth,
    height: 20,
    text: 'LABEL',
    fontSize: 14,
    fontFamily: 2,
    textAlign: 'center',
    verticalAlign: 'middle',
    containerId: rect.id,
    // ... other standard fields
};
rect.boundElements.push({id: textEl.id, type: 'text'});
```

## Arrow element properties (from FlowChartCreator)

```json
{
    "type": "arrow",
    "elbowed": true,
    "startBinding": {
        "elementId": "parent_id",
        "mode": "orbit",
        "fixedPoint": [1.033, 0.498]
    },
    "endBinding": {
        "elementId": "child_id",
        "mode": "orbit",
        "fixedPoint": [-0.033, 0.498]
    },
    "startArrowhead": null,
    "endArrowhead": "arrow"
}
```

## Pitfalls

1. **Never draw arrows manually** — raw `points` arrays render as smooth curves, not elbows
2. **Always reposition after creation** — FlowChartCreator doesn't account for sibling branches
3. **Minimum 20px gap** between leaves (element height is 50px)
4. **Text must be added separately** — `createNodes` only creates the container + arrow
5. **Fix arrow points after repositioning** — the 4-point elbow formula must be recalculated

## Dynamic pill sizing

Never use fixed widths — text overflows or wastes space.

```python
def tw(text, font_size):
    """Estimate text width in pixels."""
    return int(len(text) * font_size * 0.58) + 24  # 24px padding

# Compute widths BEFORE layout
branch_widths = {i: max(tw(label, 14), 200) for i, label in enumerate(branch_labels)}
leaf_widths = {(i,j): max(tw(full_text, 11), 320) for ...}

# Position leaf column based on max branch width
max_branch_w = max(branch_widths.values())
LEAF_X = BRANCH_X + max_branch_w + 40
```

Min widths: 200px branches, 320px leaves. Heights: 44-50px standard, 60px root.

## Group labels (visual categories)

Create standalone rectangles (no arrows) spanning a cluster's bounding box:

```python
groups = [{
    'id': 'grp_static',
    'x': cluster_x - 15, 'y': cluster_y - 30,
    'w': cluster_w + 30, 'h': cluster_h + 50,
    'bg': 'transparent', 'stroke': '#868e96', 'sw': 1,
    'opacity': 60,
    'label': '🔒 STATIC — 28% du payload',
    'labelW': 400, 'labelColor': '#868e96',
}]
```

Add label as separate text element at `(x+10, y+6)`, `textAlign: 'left'`, `fontSize: 13-14`.

## Color coding with arrow coloring

- `strokeColor` = category identifier (border)
- `backgroundColor` = fill emphasis
- `strokeWidth` = importance (1=minor, 2=normal, 3=major)
- Arrow `strokeColor` = match branch's `strokeColor`

After repositioning, iterate arrows and set color:
```python
for arrow in arrows:
    if arrow.startBinding:
        branch_id = arrow.startBinding.elementId
        if branch_id in branch_stroke_map:
            arrow.strokeColor = branch_stroke_map[branch_id]
```
