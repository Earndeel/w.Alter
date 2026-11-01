# Mindmap Layout Patterns

## Horizontal Left-to-Right Mindmap

Best for: system architecture, org charts, feature maps.

### Layout Grid

```
Col 0 (L0): Root node — centered vertically
Col 1 (L1): Level 1 branches — evenly spaced vertically
Col 2 (L2): Level 2 leaves — stacked under their parent L1
```

### Spacing Constants

```
L0 = 100        # Root x position
L1 = 550        # Level 1 x (450px gap from root)
L2 = 1100       # Level 2 x (550px gap from L1)
NODE_H = 44     # Node height (pill style)
L1_GAP = 58     # Vertical gap between L1 nodes
L2_GAP = 44-48  # Vertical gap between L2 nodes
```

### Vertical Centering — Per-Branch Block Layout

**Don't just center L1 nodes.** Each branch is a BLOCK: L1 node + its L2 children. Calculate each block's total height, then stack blocks vertically with a fixed `BRANCH_GAP` between them. This prevents L2 overlap when branches have different child counts.

```python
NODE_H = 50       # L1 node height
SMALL_H = 36      # L2 node height
BRANCH_GAP = 60   # gap between branch blocks

def branch_height(n_children):
    return NODE_H + 20 + n_children * SMALL_H + (n_children - 1) * 10

total_h = sum(branch_height(len(b["children"])) for b in branches) + (len(branches) - 1) * BRANCH_GAP
current_y = root_cy - total_h // 2  # center around root

for branch in branches:
    bh = branch_height(len(branch["children"]))
    l1_y = current_y + bh / 2 - NODE_H / 2  # center L1 in block
    # L2 children stacked from current_y with proportional spacing
    l2_start_y = current_y + (bh - len(children) * SMALL_H - (len(children)-1)*10) / 2
    current_y += bh + BRANCH_GAP
```

**Pitfall:** If you just space L1 nodes evenly and center L2 around L1, branches with many children (e.g. 14 toolsets) will collide with adjacent branches. Always use per-block height calculation.

### Pill Nodes (User Preference)

- `roundness: { "type": 3 }` — maximum rounding
- `strokeColor: "#343a40"` (dark gray, not pure black)
- `backgroundColor: "#ffffff"` (white fill)
- `strokeWidth: 2`
- `roughness: 0` (clean lines)
- Text: `fontFamily: 2` (sans-serif), uppercase, centered

### Curved Elbow Arrows

Standard arrows go straight from A to B. For mindmaps, use curved elbow routing with intermediate points:

```python
def curved_arrow(x1, y1, x2, y2, start_id=None, end_id=None):
    mid_x = x1 + (x2 - x1) * 0.5
    return {
        "type": "arrow",
        "points": [[0, 0], [mid_x - x1, 0], [x2 - x1, y2 - y1]],
        "roundness": {"type": 2},
        "endArrowhead": "arrow",
        "strokeColor": "#343a40",
        "strokeWidth": 2,
        "roughness": 0,
        "startBinding": {"elementId": start_id, "focus": 0, "gap": 8} if start_id else None,
        "endBinding": {"elementId": end_id, "focus": 0, "gap": 8} if end_id else None
    }
```

The 3-point path creates a horizontal exit from the source, then curves down/up to the target.

### PIL Rendering

For previews, render via PIL/Pillow (text renders correctly, unlike headless Chromium canvas).

Key: use `DejaVuSans-Bold.ttf` for sans-serif uppercase text. Draw rectangles with `draw.rounded_rectangle(radius=int(min(w,h)*0.4))` for pill shape.

### Delivery

- **ExcaliDash (preferred when deployed):** Update existing board via `PUT /api/drawings/{id}` — NEVER create a new board unless asked. See `references/excalidash-self-hosted.md`.
- **User on Mac/Brave**: SCP `.excalidraw` file to `~/Desktop/` — user drag-drops onto excalidraw.com
- **User in TUI**: Render PNG preview via PIL, show with `MEDIA:` tag
- **Shareable link**: Upload via `scripts/upload.py`
