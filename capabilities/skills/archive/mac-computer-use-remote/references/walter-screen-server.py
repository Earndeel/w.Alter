#!/usr/bin/env python3
"""W.Alter Screen Server — HTTP endpoint for Mac Computer Use via SSH tunnel.

Deployed as LaunchAgent on Mac. Runs in GUI session (has TCC permissions).
Endpoints:
  GET /screenshot     → PNG of current screen
  GET /click?x=N&y=N  → click at coordinates (requires cliclick + Accessibility)
  GET /type?text=TEXT → type text via cliclick
  GET /key?key=return → press key via cliclick
  GET /health         → status check

Port: 18765 (localhost only, accessed via SSH tunnel)
LaunchAgent: ~/Library/LaunchAgents/com.walter.screen-server.plist
"""
import http.server
import subprocess
import json
import os
from urllib.parse import urlparse, parse_qs

PORT = 18765
SCREENSHOT_PATH = "/tmp/walter_screen_live.png"
CLICLICK = "/usr/local/bin/cliclick"


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
            subprocess.run([CLICLICK, f"c:{x},{y}"], check=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "clicked": [int(x), int(y)]}).encode())

        elif parsed.path == "/type":
            params = parse_qs(parsed.query)
            text = params.get("text", [""])[0]
            subprocess.run([CLICLICK, f"t:{text}"], check=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "typed": text}).encode())

        elif parsed.path == "/key":
            params = parse_qs(parsed.query)
            key = params.get("key", ["return"])[0]
            subprocess.run([CLICLICK, f"kp:{key}"], check=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "key": key}).encode())

        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "version": 2}).encode())

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"W.Alter Screen Server on :{PORT}")
    http.server.HTTPServer(("127.0.0.1", PORT), ScreenHandler).serve_forever()
