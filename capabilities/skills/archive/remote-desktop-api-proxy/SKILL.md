---
name: remote-desktop-api-proxy
description: Drive a desktop app's local HTTP API from a remote VPS via SSH tunnel — token caching, Python urllib instead of fragile curl quoting, stale state cleanup.
version: 1.0.0
metadata:
  hermes:
    tags: [ssh, tunnel, desktop, api, remote, macOS]
    category: devops
---

# Remote Desktop API Proxy

When a desktop app (Electron or otherwise) exposes a local HTTP API
(`localhost:<port>`), and Hermes runs on a remote VPS, bridge them with an
SSH tunnel. This skill covers the patterns that make this reliable:
tunnel setup, token caching across SSH calls, Python `urllib.request` as
a shell-quoting-safe alternative to `curl`, and stale-state recovery.

## When to Use

- A desktop app on the user's Mac/PC has a local REST API
  (tldraw-offline, Excalidraw, ComfyUI, etc.) and Hermes is on a VPS.
- `curl` calls with nested JSON + shell variable interpolation keep
  failing silently (timeout, 401, malformed JSON).
- The app's state file (`.json`, `.pid`) is stale after a crash and
  blocks restart.

See `references/tldraw-offline-recipe.md` for a complete tldraw-specific
walkthrough with verified API calls and recovery steps.

## Pattern

### 1. Tunnel (VPS side, persistent)

```bash
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=10 \
  -i ~/.ssh/id_ed25519 -f -N -L <port>:localhost:<port> \
  <user>@<tailscale-ip>
```

Verify: `curl -s http://localhost:<port>/` returns the API root.

### 2. Token/credential caching

When the app writes credentials to a file on the remote machine, cache
them locally. Nesting SSH + inline Python + JSON + shell quoting is the
#1 source of silent failures.

```bash
# ONCE per session:
ssh <user>@<ip> 'python3 -c "import json;print(json.load(open(\"<config-path>\"))[\"<key>\"])"' \
  > /tmp/<app>_token.txt
```

Read back: `TOKEN=$(cat /tmp/<app>_token.txt)`

### 3. API calls: use Python, not raw curl

Shell quoting with nested JSON, escaped double quotes, and SSH layers
is too fragile. Prefer Python's `urllib.request`:

```python
import json, urllib.request

TOKEN = open('/tmp/<app>_token.txt').read().strip()
data = json.dumps({'code': '...'}).encode()
req = urllib.request.Request(
    'http://localhost:<port>/api/endpoint',
    data=data,
    headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {TOKEN}'
    },
    method='POST'
)
with urllib.request.urlopen(req, timeout=10) as resp:
    print(json.loads(resp.read()))
```

**Why not curl?** A curl command with `-d '{"code":"...escaped quotes..."}'`
inside `$()` inside an SSH command inside another `$()` will fail silently.
The shell resolves the token to empty, or mangles the JSON, and the API
either 401s or times out with zero bytes — no error message, just a hung
connection.

### 4. Stale state cleanup

Desktop apps that write a `server.json` / `.pid` file on launch often
leave it behind on crash. The file persists, the new process sees it and
may skip reinitialization, or the port check fails and you assume the app
is running when it isn't.

Recovery pattern:
```bash
# Kill aggressively (process name in `ps` may differ from the binary name)
pkill -9 -f <broad-match>   # e.g. 'tldraw', not 'tldraw offline'
# Delete the stale state file
rm -f <path-to-server.json>
# Restart
open -a "<App Name>"
```

### 5. macOS App Nap workaround

macOS pauses Electron renderers when the window is not visible. The
HTTP server may accept TCP connections but never send an HTTP response
(timeout with 0 bytes received).

Fix: activate the app before API calls.
```bash
osascript -e 'tell application "<App Name>" to activate'
```

## Common Failure Table

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| TCP connects, POST times out (0 bytes) | App in background (App Nap) | `osascript ... activate` |
| `server.json` present, port doesn't answer | Stale file after crash | Delete it, restart app |
| `pkill -f "<exact name>"` does nothing | Process name differs | `pkill -9 -f <shorter match>` |
| 401 on every request | Token empty (shell ate it) | Cache token to file, use Python |
| `Invalid JSON request body` | Shell mangled quotes | Switch to `urllib.request` |
| `GET /` works, POST endpoints timeout | Agent Skills / API not activated | Check app menu/setup step |

## Pitfalls

- **Never nest shell variable interpolation inside JSON inside SSH inside
  `$()`** — at least one layer will strip the value or corrupt the quoting.
  Cache the credential to a temp file and let Python read it directly.
- **`pkill -f` matches the full command line** — `"tldraw offline"` may not
  match if the process is listed as `/Applications/tldraw offline.app/...`.
  Use a shorter substring.
- **Stale state files are indistinguishable from live ones** — if
  `server.json` says `pid: 12345` but that PID doesn't exist, the file is
  stale. Check with `ps -p <pid>` before assuming the app is running.
