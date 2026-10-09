---
name: tldraw-automation
description: Extends tldraw-offline with remote Mac automation, API pitfalls, and programmatic canvas generation patterns.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [tldraw, canvas, whiteboard, automation, diagramming]
    related_skills: [tldraw-offline]
---

# tldraw Automation

Extends the bundled `tldraw-offline` skill with patterns discovered in production:
remote Mac automation via SSH tunnel, API scope pitfalls, and programmatic
mindmap/diagram generation.

Load `tldraw-offline` first for the API reference; this skill adds corrections
and the remote-automation pattern.

## When to Use

- tldraw-offline runs on a Mac, Hermes runs on a remote VPS
- You need to generate a mindmap, diagram, or structured layout programmatically
- You hit API errors with shape props or scope access

## Remote Mac via SSH Tunnel

When tldraw-offline runs on a Mac and Hermes runs on a remote VPS connected via
Tailscale + SSH tunnel:

1. **Establish tunnel once:** `ssh -f -N -L 7236:localhost:7236 <user>@<tailscale-ip>`
2. **Cache the token** on the Mac so every call doesn't re-read server.json:
   ```bash
   ssh <user>@<ip> 'python3 -c "import json;print(json.load(open(\"Library/Application Support/tldraw/server.json\"))[\"token\"])" > /tmp/tldraw_token.txt'
   ```
3. **Read token inline** in every Python script:
   ```python
   import subprocess
   result = subprocess.run(["ssh", "user@<ip>", "cat", "/tmp/tldraw_token.txt"], capture_output=True, text=True)
   TOKEN = result.stdout.strip()
   ```
4. All API calls go to `http://localhost:7236` (tunneled to Mac).
5. **Token expires on app restart** — re-run step 2 after restarting tldraw-offline.

## API Pitfalls

### `fontSize` is NOT a valid prop for `geo` shapes

```js
// ✗ BROKEN — "Unexpected property" error
editor.createShape({type:'geo', props:{geo:'rectangle', richText:toRichText('hi'), fontSize:'m'}})

// ✓ CORRECT — omit fontSize
editor.createShape({type:'geo', props:{geo:'rectangle', richText:toRichText('hi')}})
```

Valid geo props: `geo`, `w`, `h`, `color`, `fill`, `richText` (plus dash/size with defaults).

### `api` is NOT available in `/api/doc/:id/exec`

The `/exec` scope only has `editor` + `helpers`. For `api.getScreenshot()`,
`api.getDocs()`, or any `api.*` method, use the `/api/search` endpoint:

```python
# ✗ BROKEN — api is not defined
req(f"api/doc/{doc_id}/exec", {"code": "return api.getScreenshot(docId)"})

# ✓ CORRECT — use /api/search which has full api scope
req("api/search", {"code": f"return await api.getScreenshot(\"{doc_id}\")"})
```

### Screenshot file lives on the remote host

`api.getScreenshot()` returns a `filePath` on the Mac (e.g. `/var/folders/...`).
SCP it to the VPS before using `vision_analyze`:

```bash
ssh user@<ip> 'cp <screenshot-path> /tmp/tldraw_screenshot.jpg'
scp user@<ip>:/tmp/tldraw_screenshot.jpg /tmp/tldraw_screenshot.jpg
```

## Programmatic Mindmap Generation

For horizontal left-to-right mindmaps:

```python
# Layout constants
ROOT_X, ROOT_Y = 80, 400
L1_X, L1_W, L1_H = 420, 220, 50
L2_X, L2_W, L2_H = 800, 190, 36

# Generate JS block then execute via /exec:
req(f"api/doc/{doc_id}/exec", {"code": js_code})

# Verify with /api/search screenshot:
req("api/search", {"code": f"return await api.getScreenshot(\"{doc_id}\")"})
```

### Shape creation pattern

```js
const {createShapeId, toRichText} = await import('tldraw');

// Rectangle with label
editor.createShape({
  id: createShapeId('my-node'),
  type: 'geo',
  x: 100, y: 200,
  props: {
    geo: 'rectangle', w: 200, h: 50,
    color: 'black', fill: 'solid',
    richText: toRichText('My Label')
  }
});

// Arrow between nodes
editor.createShape({
  id: createShapeId('arrow-1'),
  type: 'arrow',
  x: 0, y: 0,
  props: {
    start: {x: 300, y: 225},
    end: {x: 500, y: 300},
    color: 'black'
  }
});
```

## Behavioral Rule

When tldraw-offline has been explicitly installed, configured, and verified
working in the current session for a diagramming task, USE IT. Do not fall back
to excalidraw or another tool by reflex. The user invested time in the setup;
honor that investment.
