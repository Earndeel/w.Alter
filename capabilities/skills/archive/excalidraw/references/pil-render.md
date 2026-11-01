# PIL/Pillow Rendering for Excalidraw Diagrams

## When to use

When headless Chromium can't render text (fonts not loaded), use PIL/Pillow to render `.excalidraw` JSON directly to PNG. This is the **reliable fallback** for any screenshot that needs readable text.

## Pattern

```python
from PIL import Image, ImageDraw, ImageFont
import json, math

with open('diagram.excalidraw', 'r') as f:
    diagram = json.load(f)

els = diagram['elements']

# Calculate bounds (skip deleted elements)
minX = min(e['x'] for e in els if not e.get('isDeleted'))
minY = min(e['y'] for e in els if not e.get('isDeleted'))
maxX = max(e['x'] + e.get('width', 0) for e in els if not e.get('isDeleted'))
maxY = max(e['y'] + e.get('height', 0) for e in els if not e.get('isDeleted'))

# Canvas setup
W, H = 3840, 2160  # 4K resolution
margin = 100
dw, dh = maxX - minX, maxY - minY
scale = min((W - 2*margin) / dw, (H - 2*margin) / dh)
ox = margin - minX * scale + (W - 2*margin - dw * scale) / 2
oy = margin - minY * scale + (H - 2*margin - dh * scale) / 2

img = Image.new('RGB', (W, H), '#ffffff')
draw = ImageDraw.Draw(img)

# Font cache (DejaVu Sans = clean sans-serif, available on most Linux)
font_cache = {}
def get_font(size):
    size = max(size, 10)
    if size not in font_cache:
        try:
            font_cache[size] = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
        except:
            font_cache[size] = ImageFont.load_default()
    return font_cache[size]

# Layer 1: Arrows (behind everything)
for e in els:
    if e.get('isDeleted') or e['type'] != 'arrow': continue
    x = e['x'] * scale + ox
    y = e['y'] * scale + oy
    pts = e.get('points', [[0,0],[0,0]])
    coords = [(x + p[0]*scale, y + p[1]*scale) for p in pts]
    draw.line(coords, fill='#1e1e1e', width=3)
    # Arrowhead
    if len(coords) >= 2:
        ax, ay = coords[-1]
        px, py = coords[-2]
        angle = math.atan2(ay-py, ax-px)
        hl = 14
        draw.line([(ax, ay), (ax - hl*math.cos(angle-0.5), ay - hl*math.sin(angle-0.5))], fill='#1e1e1e', width=3)
        draw.line([(ax, ay), (ax - hl*math.cos(angle+0.5), ay - hl*math.sin(angle+0.5))], fill='#1e1e1e', width=3)

# Layer 2: Rectangles (on top of arrows)
for e in els:
    if e.get('isDeleted') or e['type'] != 'rectangle': continue
    x = e['x'] * scale + ox
    y = e['y'] * scale + oy
    w = e.get('width', 0) * scale
    h = e.get('height', 0) * scale
    fill = e.get('backgroundColor', '#ffffff')
    if fill == 'transparent': fill = '#ffffff'
    r = int(min(w, h) * 0.12)  # Rounded corner radius
    draw.rounded_rectangle([x, y, x+w, y+h], radius=r, fill=fill, outline='#1e1e1e', width=3)

# Layer 3: Text (on top of everything)
for e in els:
    if e.get('isDeleted') or e['type'] != 'text' or not e.get('text'): continue
    x = e['x'] * scale + ox
    y = e['y'] * scale + oy
    w = e.get('width', 0) * scale
    h = e.get('height', 0) * scale
    fs = max(int((e.get('fontSize', 20)) * scale), 12)
    font = get_font(fs)
    lines = e['text'].split('\n')
    lh = fs * 1.3
    total_h = len(lines) * lh
    start_y = y + h/2 - total_h/2 + lh/2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        tx = x + w/2 - tw/2
        ty = start_y + i * lh - lh/2
        draw.text((tx, ty), line, fill='#1e1e1e', font=font)

img.save('/tmp/diagram.png', quality=95)
```

## Key points

- **Draw order matters**: arrows → rectangles → text. Text must be last to appear on top.
- **Font**: DejaVu Sans (`/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`) is a clean sans-serif available on most Linux. Falls back to PIL default if not found.
- **Rounded corners**: `radius=int(min(w, h) * 0.12)` gives a nice rounded feel.
- **Black borders**: Always use `outline='#1e1e1e'` and `fill='#1e1e1e'` for text/arrows.
- **Scale to fit**: Calculate scale from element bounds and canvas size, center with offsets.
- **Resolution**: 3840×2160 (4K) is good for detailed diagrams. Use 1920×1080 for simpler ones.
- **Supports**: rectangles, text, arrows with arrowheads. Does NOT render ellipses, diamonds, or freehand — extend as needed.

## Why not Chromium canvas?

Headless Chromium loads Excalidraw's JS fine, and `canvas.toDataURL()` produces images. But the Excalidraw canvas renderer calls `ctx.fillText()` with custom font families (Excalifont, Virgil). If those fonts aren't loaded in the browser, `fillText()` silently produces nothing — no error, no fallback, just blank space where text should be. Even after using `FontFace.load()` to force-load the fonts, the canvas doesn't re-render because Excalidraw only paints once per frame and doesn't know the fonts became available.

PIL renders text using system fonts directly, bypassing this entire issue.
