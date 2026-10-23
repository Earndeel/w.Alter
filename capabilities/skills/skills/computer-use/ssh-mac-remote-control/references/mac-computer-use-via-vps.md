# Mac Computer Use via VPS (Remote Desktop Control)

Control a Mac's desktop from a remote VPS without installing Hermes on the Mac.
Uses SSH + LaunchAgent HTTP server + `cliclick` for full screen capture + click + type.

## Architecture

```
VPS (Linux, Hermes)
  │
  ├── SSH tunnel ──→ Mac:18765 (W.Alter Screen Server)
  │
  ├── GET /screenshot → screencapture (in GUI session) → PNG
  ├── GET /click?x=N&y=N → cliclick c:N,N
  ├── GET /type?text=TEXT → cliclick t:TEXT
  ├── GET /key?key=RETURN → cliclick kp:RETURN
  └── GET /health → {"status":"ok"}
```

The key insight: a **LaunchAgent** runs in the user's GUI audit session, so `screencapture` works from it (unlike SSH which inherits the `sshd` audit session that TCC blocks).

## Prerequisites

1. `cliclick` on Mac: `brew install cliclick`
2. SSH access from VPS to Mac via Tailscale
3. Mac screen must be **awake and unlocked** (use `caffeinate -d` to prevent sleep)

## Setup (one-time)

### 1. Create the server script on Mac

`~/.hermes/scripts/walter-screen-server.py`:

```python
#!/usr/bin/env python3
"""W.Alter Screen Server — screenshot + click + type endpoint for Computer Use"""
import http.server
import subprocess
import json
from urllib.parse import urlparse, parse_qs

PORT = 18765
SCREENSHOT_PATH = "/tmp/walter_screen_live.png"
CLICKTOOL = "/usr/local/bin/cliclick"

class ScreenHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/screenshot":
            subprocess.run(["screencapture", "-x", SCREENSHOT_PATH], check=True)
            with open(SCREENSHOT_PATH, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/click":
            params = parse_qs(parsed.query)
            x, y = params.get("x", ["0"])[0], params.get("y", ["0"])[0]
            subprocess.run([CLICKTOOL, f"c:{x},{y}"], check=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "clicked": [int(x), int(y)]}).encode())
        elif parsed.path == "/type":
            params = parse_qs(parsed.query)
            text = params.get("text", [""])[0]
            subprocess.run([CLICKTOOL, f"t:{text}"], check=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "typed": text}).encode())
        elif parsed.path == "/key":
            params = parse_qs(parsed.query)
            key = params.get("key", ["return"])[0]
            subprocess.run([CLICKTOOL, f"kp:{key}"], check=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "key": key}).encode())
        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, *a): pass

print(f"W.Alter Screen Server on :{PORT}")
http.server.HTTPServer(("127.0.0.1", PORT), ScreenHandler).serve_forever()
```

### 2. Create LaunchAgent (auto-starts in GUI session)

`~/Library/LaunchAgents/com.walter.screen-server.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.walter.screen-server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/lucasjouvencon/.hermes/scripts/walter-screen-server.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/walter-screen-server.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/walter-screen-server.log</string>
</dict>
</plist>
```

Load: `launchctl load ~/Library/LaunchAgents/com.walter.screen-server.plist`

### 3. SSH tunnel from VPS

```bash
ssh -o ConnectTimeout=5 -f -N -L 18765:localhost:18765 -i ~/.ssh/id_ed25519 lucasjouvencon@<mac-tailscale-ip>
```

### 4. Verify

```bash
curl -s http://localhost:18765/health
# → {"status": "ok"}
```

## Usage from VPS

```bash
# Screenshot → save → analyze
curl -s http://localhost:18765/screenshot -o /tmp/mac_screen.png

# Click at coordinates
curl -s "http://localhost:18765/click?x=500&y=300"

# Type text
curl -s "http://localhost:18765/type?text=Hello%20World"

# Press key
curl -s "http://localhost:18765/key?key=return"
```

## Full Computer Use Loop (Python)

```python
import requests, time
from hermes_tools import vision_analyze  # or use the vision tool directly

BASE = "http://localhost:18765"

def see():
    """Take screenshot and return path for vision analysis."""
    r = requests.get(f"{BASE}/screenshot", timeout=10)
    path = "/tmp/mac_cu_frame.png"
    with open(path, "wb") as f:
        f.write(r.content)
    return path

def click(x, y):
    """Click at screen coordinates."""
    requests.get(f"{BASE}/click", params={"x": x, "y": y}, timeout=5)

def type_text(text):
    """Type text at current cursor position."""
    requests.get(f"{BASE}/type", params={"text": text}, timeout=5)

def press(key):
    """Press a key (return, tab, escape, space, etc.)."""
    requests.get(f"{BASE}/key", params={"key": key}, timeout=5)

# Example loop: screenshot → analyze → click
frame = see()
# Use vision_analyze on frame to identify element coordinates
# Then: click(target_x, target_y)
```

## Latency Budget

| Step | Time |
|------|------|
| SSH tunnel (Tailscale) | ~50ms RTT |
| screencapture (Mac) | ~200ms |
| SCP transfer to VPS | ~100-300ms |
| Vision AI analysis | ~1-2s |
| cliclick (Mac) | ~50ms |
| **Total per action** | **~1.5-2.5s** |

Good for: website navigation, form filling, menu clicking, app automation.
Not good for: drag-and-drop, real-time gaming, video editing.

## Pitfalls

- **Screen must be awake and unlocked.** Use `caffeinate -d -u -t 3600` to prevent sleep. If screen locks, screenshots return black.
- **LaunchAgent must be reloaded if script changes:** `launchctl unload ~/Library/LaunchAgents/com.walter.screen-server.plist && launchctl load ~/Library/LaunchAgents/com.walter.screen-server.plist`
- **brew path not in SSH PATH:** Use full path `/usr/local/bin/brew` or eval the shellenv first: `eval "$(/usr/local/bin/brew shellenv)"`
- **Swift compilation broken on some Macs:** Xcode Command Line Tools can have module conflicts (`SwiftBridging` redefinition). Use Python + subprocess instead of Swift for screen capture.
- **`cliclick` coordinates are in logical points, not retina pixels.** On a 2880x1800 retina display, the logical coordinate space is 1440x900. `screencapture` captures at full retina resolution. When using vision to identify click targets, divide retina coordinates by 2 for `cliclick`.
- **URL-encode special characters in `type` text.** Spaces → `%20`, etc. Or use POST body if you extend the server.
