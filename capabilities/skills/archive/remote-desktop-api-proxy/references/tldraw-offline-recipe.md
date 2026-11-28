# tldraw-offline remote setup (verified 2026-07-24)

Full reproduction of setting up tldraw-offline on a Mac and controlling it
from a remote VPS.

## App details

- Name: tldraw offline
- Binary: `/Applications/tldraw offline.app`
- Config: `~/Library/Application Support/tldraw/server.json`
- Port: 7236
- Token key: `token` (64-char hex)
- API root: `GET /` (no auth), `GET /readme` (no auth)
- Auth endpoints: everything else needs `Authorization: Bearer <token>`

## Install (Mac, via SSH)

```bash
# Download
curl -sLO "https://github.com/tldraw/tldraw-offline/releases/download/v1.11.0/tldraw-offline-mac-universal.dmg"
# Mount
hdiutil attach -nobrowse /tmp/tldraw-offline-mac-universal.dmg
# Copy (volume name has spaces)
cp -R "/Volumes/tldraw offline-1.11.0"/*.app /Applications/
# Detach
hdiutil detach "/Volumes/tldraw offline-1.11.0" -force
```

## Launch & activate

```bash
open -a "tldraw offline"
sleep 8  # wait for server.json

# Activate Agent Skills (mandatory for API to work)
osascript -e '
tell application "System Events"
  tell process "tldraw offline"
    click menu item "Install Agent Skills" of menu 1 of menu bar item "Develop" of menu bar 1
  end tell
end tell'
```

## Tunnel (VPS → Mac)

```bash
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=10 \
  -i ~/.ssh/id_ed25519 -f -N -L 7236:localhost:7236 \
  lucasjouvencon@100.127.150.1
```

## Token cache

```bash
ssh lucasjouvencon@100.127.150.1 \
  'python3 -c "import json;print(json.load(open(\"Library/Application Support/tldraw/server.json\"))[\"token\"])"' \
  > /tmp/tldraw_token.txt
```

## Verified API calls

### List documents
```python
import json, urllib.request
TOKEN = open('/tmp/tldraw_token.txt').read().strip()
data = json.dumps({'code': 'return await api.getDocs()'}).encode()
req = urllib.request.Request('http://localhost:7236/api/search',
  data=data, headers={'Content-Type': 'application/json',
  'Authorization': f'Bearer {TOKEN}'}, method='POST')
with urllib.request.urlopen(req, timeout=10) as resp:
    print(json.loads(resp.read()))
# → {"success":true,"result":[{"id":"tldr:untitled:...","documentId":"zqlpZxWlz7c1eQtxnvrJ2",...}]}
```

### Create shape
```python
code = '''const {createShapeId, toRichText} = await import('tldraw');
editor.createShape({id:createShapeId(), type:'geo', x:100, y:100,
  props:{geo:'rectangle', w:200, h:100, color:'blue', fill:'solid',
  richText:toRichText('Hello')}});
return editor.getCurrentPageShapes().length;'''
data = json.dumps({'code': code}).encode()
req = urllib.request.Request(f'http://localhost:7236/api/doc/{DOC_ID}/exec',
  data=data, headers={'Content-Type': 'application/json',
  'Authorization': f'Bearer {TOKEN}'}, method='POST')
with urllib.request.urlopen(req, timeout=10) as resp:
    print(json.loads(resp.read()))
# → {"success":true,"result":1}
```

## Recovery (stale server.json)

```bash
pkill -9 -f tldraw
rm -f ~/Library/Application\ Support/tldraw/server.json
open -a "tldraw offline"
# then re-run Agent Skills activation + re-cache token
```

## Key pitfalls this session hit

1. `curl` with `$TOKEN` inside `-d '{"code":"..."}'` sent empty token → 401.
   Root cause: shell variable expansion inside single quotes doesn't work;
   switching to double quotes broke the JSON escaping. Fix: Python urllib.
2. `pkill -f "tldraw offline"` had no effect — the process name in `ps`
   is `/Applications/tldraw offline.app/Contents/MacOS/tldraw offline`.
   Fix: `pkill -9 -f tldraw`.
3. `server.json` survived `pkill` → new launch saw stale file, API didn't
   reinitialize. Fix: delete the file before restart.
4. API timed out (TCP connected, 0 bytes) until `osascript activate` brought
   the app to foreground. macOS App Nap was pausing the Electron renderer.
