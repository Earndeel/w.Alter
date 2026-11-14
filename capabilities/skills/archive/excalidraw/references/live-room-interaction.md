# Live Excalidraw Room Interaction via Camoufox-Max

## Quick Reference

```bash
# Create tab
TAB=$(curl -s -X POST http://localhost:9378/tab/new \
  -H "Content-Type: application/json" \
  -d '{"session":"excalidraw"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['tabId'])")

# Navigate to room
curl -s -X POST http://localhost:9378/tab/navigate \
  -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"url\":\"https://excalidraw.com/#room=ROOM_ID,ROOM_KEY\"}"

# Wait for sync
sleep 6

# Screenshot
curl -s -X POST http://localhost:9378/tab/screenshot \
  -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\"}" | python3 -c "
import sys,json,base64
d=json.load(sys.stdin)
open('/tmp/excalidraw_room.png','wb').write(base64.b64decode(d['buffer']))
print('Saved')
"
```

## Available UI Actions

### Tool Selection (via aria-label clicks)
```bash
# Select tool by aria-label
curl -s -X POST http://localhost:9378/tab/evaluate -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"expression\":\"document.querySelector('[aria-label=\\\"Text\\\"]').click()\"}"

# Common tool aria-labels: "Selection", "Rectangle", "Diamond", "Ellipse", "Arrow", "Line", "Pencil", "Text", "Image", "Eraser"
```

### Click at Coordinates
```bash
curl -s -X POST http://localhost:9378/tab/click-at -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"x\":400,\"y\":300}"
```

### Keyboard Input
```bash
# Type text
curl -s -X POST http://localhost:9378/tab/keyboard-type -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"text\":\"Hello World\"}"

# Press key
curl -s -X POST http://localhost:9378/tab/keyboard-press -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"key\":\"Escape\"}"
```

### Export Modal
```bash
# Open export (Ctrl+Shift+E)
curl -s -X POST http://localhost:9378/tab/keyboard-press -H "Content-Type: application/json" \
  -d "{\"tabId\":\"$TAB\",\"key\":\"Control+Shift+E\"}"
# Buttons: PNG, SVG, Copy to clipboard
```

## Limitations

- **No programmatic scene reading** — Camoufox strips React fibers. See `camoufox-automation` skill, `references/react-fiber-stripping.md`
- **No undo** — changes committed directly to room
- **Room sync delay** — 5-8 seconds after navigation before screenshots are useful
- **Canvas coordinates** — may be zoomed/panned; use annotated screenshots to find positions
