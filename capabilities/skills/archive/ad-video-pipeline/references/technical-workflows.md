## Key Technical Details

### foreplay.co Download
- foreplay.co may have anti-bot protections
- If simple download fails, use Webtop CDP to navigate and intercept network requests:
  ```
  docker exec webtop python3 -c "
    import websocket, json
    ws = websocket.create_connection('ws://localhost:9222/devtools/page/{page_id}', timeout=30)
    ws.send(json.dumps({'id': 1, 'method': 'Network.enable'}))
    ws.send(json.dumps({'id': 2, 'method': 'Page.navigate', 'params': {'url': 'https://foreplay.co/...'}}))
    # Listen for video resource responses in Network messages
  "
  ```

### Shot Detection with ffmpeg
- Scene change threshold: `0.3` (tune per content, 0.1-0.5 range)
  ```
  ffmpeg -i input.mp4 -vf "select='gt(scene,0.3)',showinfo" -f null - 2>&1 | grep 'pts_time'
  ```
- For more precision: use `detect_scenes` from `scenedetect` Python library

### Kling V3 Pro Payload Structure
- Endpoints: extracted via OpenAPI at `https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>`
- Key schemas: `KlingVideoV3ProTextToVideoInput`, `KlingVideoV3ProImageToVideoInput`
- `multi_prompt` format: array of `{prompt, duration}` objects
- `@Element` system: reference in prompt with `@Element0`, provide descriptions in `elements` array
- Audio: `generate_audio: True` for automatic soundtrack

### Notion Scraping via Webtop CDP (VALIDATED WORKFLOW)

**Prerequisites:** Webtop container running with Chromium and CDP port 9222 accessible.

**Step 1: Get CDP Page ID**
```bash
docker exec webtop curl -s http://localhost:9222/json/list
```
Note the `webSocketDebuggerUrl` for the Notion page tab.

**Step 2: Navigate to Card URL via WebSocket**
```python
import websocket, json, time

ws = websocket.create_connection('ws://localhost:9222/devtools/page/{page_id}', timeout=15)

def eval_js(expr):
    ws.send(json.dumps({'id': 99, 'method': 'Runtime.evaluate',
        'params': {'expression': expr, 'returnByValue': True}}))
    r = json.loads(ws.recv())
    return r.get('result', {}).get('result', {}).get('value')

# Navigate to card
ws.send(json.dumps({'id': 1, 'method': 'Page.navigate',
    'params': {'url': 'https://www.notion.so/card-url'}}))
ws.recv()
time.sleep(7)  # Notion SPA needs time to render

# Progressive scroll to trigger lazy loading
for i in range(8):
    eval_js('window.scrollBy(0, 500)')
    time.sleep(0.3)
time.sleep(2)

# Extract full page text
text = eval_js('document.body.innerText')
```

**Step 3: Parse Card Properties and Comments from Text**
Notion renders card properties as "Label\nValue" pairs in the page text. The section headers are:
- Properties: `Persona`, `Angle Marketing`, `Statut`, `Brief Owner`, etc.
- Comments: Look for the `Commentaires` header followed by content until `Utilisez Notion` (language popup)

```python
def extract_comments(full_text):
    comments = []
    lines = full_text.split('\n')
    in_comments = False
    for line in lines:
        stripped = line.strip()
        if stripped == 'Commentaires':
            in_comments = True
            continue
        if in_comments:
            if 'Utilisez Notion' in stripped:
                break
            if stripped:
                comments.append(stripped)
    return comments
```

**Step 4: Extract Kanban Structure**
Navigate to the parent page URL, scroll iteratively, then extract:
- Column headers: look for `Filming in Progress`, `Editing Pending`, etc.
- Card names and URLs: appear as links in the board

**Key URLs Discovered (April 2026):**
- Parent board: `https://www.notion.so/Creatif-Brief-c59e8cde179b8347a5ea01a01b545c6a`
- Sub-board: `https://www.notion.so/V-Avril-2026-334e8cde179b80228c7cee520a105724`
- Card URLs: `https://www.notion.so/{card-name}-{card-id}?pvs=25`

**IMPORTANT Caveats:**
- Notion SPA crashes with "Une erreur s'est produite lors du chargement de cette page" on specific cards even with fresh tabs
- If a page crashes 3x in a row (navigate + reload), the card is likely corrupted or requires auth refresh
- WebSocket closes cleanly (code 1000) unexpectedly on heavy pages
- Always create a new tab/page for each card scrape: `curl http://localhost:9222/json/new` then close with `/json/close/{id}`
- `returnByValue: True` may return Python dict instead of JSON string — check `isinstance()` before `json.loads()`
- Language popup ("Utilisez Notion...") appears at bottom of page text — use as end marker
- **Chromium CDP only accessible from within container** (`docker exec webtop`). Host cannot reach port 9222 directly.

### Validated Batch Video Download Workflow

**Problem:** foreplay.co hosts videos on R2 (`r2.foreplay.co/<id>/<hash>.mp4`). The `yt-dlp` tool is absent in `webtop` container.

**Solution A: CDP MP4 extraction + curl download (R2/foreplay.co)**

```python
# Step 1: Open foreplay.co link in new CDP tab, extract MP4 URL
js_extract = """
(() => {
  const video = document.querySelector('video');
  if (video) return video.currentSrc || (video.querySelector('source')?.src || null);
  return null;
})()
"""
# Returns: https://r2.foreplay.co/12345/abcdef.mp4

# Step 2: Download with curl (works in webtop container)
# curl -L -o /root/projects/ad-video-pipeline/output/videos/card_XX.mp4 "https://r2.foreplay.co/..."
```

**Solution B: Google Drive (authenticated session via CDP cookies)**

Google Drive uses a YouTube embed for video preview (cross-origin iframe). `document.querySelector('video').currentSrc` does NOT work. Standard tools (`yt-dlp`, `gdown`) return HTTP 403 on restricted files.

Working method: Export authenticated browser cookies via CDP → use `curl -b` with the direct download endpoint.

Step 1 — Export ALL cookies from the CDP session:
```python
import urllib.request, json, websocket

# Connect to an active Drive tab
resp = urllib.request.urlopen('http://localhost:9222/json/list')
tabs = json.loads(resp.read())
drive_tab = next((t for t in tabs if 'drive.google.com' in t.get('url', '')), None)
if not drive_tab:
    raise Exception('No Drive tab found')

ws = websocket.create_connection(drive_tab['webSocketDebuggerUrl'], timeout=30)

# Get all cookies via CDP
ws.send(json.dumps({'id': 2, 'method': 'Network.getAllCookies', 'params': {}}))
r = json.loads(ws.recv())
all_cookies = r.get('result', {}).get('cookies', [])

# Write Netscape format cookie file
lines = ['# Netscape HTTP Cookie File']
for c in all_cookies:
    domain = c.get('domain', '')
    include_sub = 'TRUE' if domain.startswith('.') else 'FALSE'
    path = c.get('path', '/')
    secure = 'TRUE' if c.get('secure', False) else 'FALSE'
    expiry = str(int(c.get('expirationDate', 9999999999)))
    lines.append('\t'.join([domain, include_sub, path, secure, expiry, c['name'], c['value']]))

with open('/tmp/google_cookies.txt', 'w') as f:
    f.write('\n'.join(lines))
```

Step 2 — Download via curl with cookies:
```python
import subprocess
file_id = '1bdVcvEXvkd_4vLPmrN21OwccOG53nWyN'  # Extract from Drive URL
output_path = '/root/projects/ad-video-pipeline/output/videos/w14_v1.mp4'

result = subprocess.run([
    'curl', '-L',
    '-b', '/tmp/google_cookies.txt',
    '-o', output_path,
    f'https://drive.google.com/uc?export=download&id={file_id}'
], capture_output=True, text=True, timeout=120)

# Verify: check file size (should be MBs, not bytes — HTML error pages are <1KB)
import os
size = os.path.getsize(output_path)
if size > 1_000_000:  # More than 1MB, likely a real video
    print(f'Download OK: {size/1024/1024:.1f} MB')
else:
    print('Download may have failed — file too small, likely an HTML error')
```

Step 3 — Verify with ffprobe:
```bash
ffprobe -v quiet -print_format json -show_format -show_streams video.mp4
```

**CRITICAL Google Drive caveats:**
- The Drive video player uses a YouTube embed (cross-origin iframe). You CANNOT extract video URLs via `document.querySelector('video')`.
- `yt-dlp --cookies` and `gdown` both fail with HTTP 403 on restricted Drive files.
- The `curl -b cookies` method with `uc?export=download&id=` WORKS but requires a valid authenticated CDP session.
- If cookies expire, you must manually re-authenticate via the Webtop browser (Selkies/noVNC) and re-export.
- The `?usp=drive_link` suffix in the URL should be stripped — the bare file ID is sufficient.

**Solution C: Loom videos** (TODO — implement when first Loom card is encountered)
- Loom embeds may require different extraction. Likely needs CDP navigation + network interception.

**Step 3: Video analysis with ffmpeg**
```bash
# Shot detection (scene threshold 0.4, tune 0.1-0.5)
ffmpeg -i video.mp4 -vf "select='gt(scene,0.4)',showinfo" -vsync vframes 1 keyframes/keyframe_%04d.jpg 2>&1

# Metadata extraction
ffprobe -v quiet -print_format json -show_format -show_streams video.mp4
```

### Critical CDP Access Patterns

**Webtop CDP is internal-only.** Use `docker exec webtop python3 <script>` — NOT host-side websocket.

```python
# Create new tab from inside container
import urllib.request, json
resp = urllib.request.urlopen('http://localhost:9222/json/new')
new_tab = json.loads(resp.read())
ws = websocket.create_connection(new_tab['webSocketDebuggerUrl'], timeout=20)

# Close tab when done
urllib.request.urlopen(f'http://localhost:9222/json/close/{new_tab["id"]}')
```

**Chromium restart command:**
```bash
docker exec webtop bash /config/custom/start-chromium.sh
# Creates /tmp/chromium-start-data, binds to port 9222
# socat forwards 9223 → 9222 (but direct 9222 via docker exec is faster)
```

### Foreplay.co Direct MP4 URL Pattern
`https://r2.foreplay.co/<numeric_id>/<hash>.mp4`
- No anti-bot protection needed — R2 URLs are direct and downloadable with curl
- URLs are session-independent, stable per card
- Extract via: `document.querySelector('video')?.currentSrc`

### Notion Card Content Limitation
- CDP scraping only captures **comments** (visible in page DOM after scroll)
- **Main card body content** may crash on some cards (SPA rendering issues, ~1/15 cards)
- If a card crashes 3x: mark as `content_incomplete`, flag for manual extraction
- Fallback: check `/tmp/comments_export.json` and `/tmp/cards_to_download.json` for previously extracted data
