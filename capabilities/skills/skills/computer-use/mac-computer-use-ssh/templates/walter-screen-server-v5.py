#!/usr/bin/env python3
"""W.Alter Screen Server v5 — screencapture + cliclick + osascript combos
Deploy to Mac ~/.hermes/scripts/walter-screen-server.py
LaunchAgent: ~/Library/LaunchAgents/com.walter.screen-server.plist
"""
import http.server
import subprocess
import json
import os
from urllib.parse import urlparse, parse_qs, unquote

PORT = 18765

MODIFIER_MAP = {"cmd": "command", "ctrl": "control", "opt": "option", "shift": "shift"}
CLICLICK_MODS = {"cmd": "command", "ctrl": "control", "opt": "option", "shift": "shift"}

class ScreenHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        try:
            if path == "/health":
                self._json({"status": "ok", "version": 5})
            elif path == "/screenshot":
                self._screenshot()
            elif path == "/click":
                self._click(params)
            elif path == "/doubleclick":
                self._doubleclick(params)
            elif path == "/rightclick":
                self._rightclick(params)
            elif path == "/type":
                self._type(params)
            elif path == "/key":
                self._key(params)
            elif path == "/combo":
                self._combo(params)
            elif path == "/scroll":
                self._scroll(params)
            elif path == "/drag":
                self._drag(params)
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _screenshot(self):
        path = "/tmp/walter_screen_live.png"
        subprocess.run(["screencapture", "-x", path], check=True)
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _click(self, params):
        x, y = int(params["x"][0]), int(params["y"][0])
        subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
        self._json({"ok": True, "clicked": [x, y]})

    def _doubleclick(self, params):
        x, y = int(params["x"][0]), int(params["y"][0])
        subprocess.run(["cliclick", f"dc:{x},{y}"], check=True)
        self._json({"ok": True, "doubleclicked": [x, y]})

    def _rightclick(self, params):
        x, y = int(params["x"][0]), int(params["y"][0])
        subprocess.run(["cliclick", f"rc:{x},{y}"], check=True)
        self._json({"ok": True, "rightclicked": [x, y]})

    def _type(self, params):
        text = unquote(params["text"][0])
        text = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{text}"'
        subprocess.run(["osascript", "-e", script], check=True)
        self._json({"ok": True, "typed": len(text)})

    def _key(self, params):
        k = unquote(params["key"][0])
        key_map = {"space": 49, "tab": 48, "escape": 53, "return": 36, "delete": 51,
                   "up": 126, "down": 125, "left": 123, "right": 124"}
        if k in key_map:
            script = f'tell application "System Events" to key code {key_map[k]}'
        else:
            script = f'tell application "System Events" to keystroke "{k}"'
        subprocess.run(["osascript", "-e", script], check=True)
        self._json({"ok": True, "key": k})

    def _combo(self, params):
        keys = unquote(params["keys"][0]).split(",")
        modifiers = []
        char = None
        for k in keys:
            k = k.strip().lower()
            if k in MODIFIER_MAP:
                modifiers.append(MODIFIER_MAP[k])
            else:
                char = k

        key_map = {"space": 49, "tab": 48, "escape": 53, "return": 36, "delete": 51}
        mod_str = ", ".join(f"{m} down" for m in modifiers)

        if char and char in key_map:
            script = f'tell application "System Events" to key code {key_map[char]} using {{{mod_str}}}'
        elif char:
            script = f'tell application "System Events" to keystroke "{char}" using {{{mod_str}}}'
        else:
            # Modifier-only combo (like Cmd+Space)
            if keys[0].strip().lower() in key_map:
                script = f'tell application "System Events" to key code {key_map[keys[0].strip().lower()]} using {{{mod_str}}}'
            else:
                script = f'tell application "System Events" to keystroke "" using {{{mod_str}}}'

        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if result.returncode != 0:
            self._json({"error": result.stderr.strip()}, 400)
        else:
            self._json({"ok": True, "combo": keys})

    def _scroll(self, params):
        direction = params.get("dir", ["down"])[0]
        amount = int(params.get("amount", [3])[0])
        if direction == "down":
            subprocess.run(["cliclick", f"sf:0,-{amount * 10}"], check=True)
        else:
            subprocess.run(["cliclick", f"sf:0,{amount * 10}"], check=True)
        self._json({"ok": True, "scroll": direction, "amount": amount})

    def _drag(self, params):
        x1, y1 = int(params["x1"][0]), int(params["y1"][0])
        x2, y2 = int(params["x2"][0]), int(params["y2"][0])
        subprocess.run(["cliclick", f"dd:{x1},{y1}", f"du:{x2},{y2}"], check=True)
        self._json({"ok": True, "dragged": [[x1, y1], [x2, y2]]})

    def log_message(self, format, *args):
        pass  # Suppress logs

if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), ScreenHandler)
    print(f"W.Alter Screen Server v5 on :{PORT}")
    server.serve_forever()
