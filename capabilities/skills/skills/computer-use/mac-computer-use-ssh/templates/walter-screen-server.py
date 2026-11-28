#!/usr/bin/env python3
"""W.Alter Screen Server v5 — osascript for combos, cliclick for clicks.
Combos use AppleScript modifier names (command/control/option/shift), not cliclick abbreviations (cmd/ctrl/opt).
"""
import http.server
import subprocess
import json
import os
from urllib.parse import urlparse, parse_qs, unquote

PORT = 18765
SCREENSHOT_PATH = "/tmp/walter_screen_live.png"
CLICLICK = "/usr/local/bin/cliclick"

# Maps user-facing keys → AppleScript modifier names
MODIFIER_MAP = {"cmd": "command", "ctrl": "control", "opt": "option", "alt": "option", "shift": "shift"}

# Key codes for modifier-only combos (can't use keystroke without a character)
KEY_CODES = {"space": 49, "tab": 48, "escape": 53, "return": 36, "delete": 51, "backspace": 51}


class ScreenHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
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
                x, y = params.get("x", ["0"])[0], params.get("y", ["0"])[0]
                subprocess.run([CLICLICK, "c:" + x + "," + y], check=True)
                self._json({"ok": True, "clicked": [int(x), int(y)]})
            elif parsed.path == "/doubleclick":
                x, y = params.get("x", ["0"])[0], params.get("y", ["0"])[0]
                subprocess.run([CLICLICK, "dc:" + x + "," + y], check=True)
                self._json({"ok": True, "double_clicked": [int(x), int(y)]})
            elif parsed.path == "/rightclick":
                x, y = params.get("x", ["0"])[0], params.get("y", ["0"])[0]
                subprocess.run([CLICLICK, "rc:" + x + "," + y], check=True)
                self._json({"ok": True, "right_clicked": [int(x), int(y)]})
            elif parsed.path == "/type":
                text = unquote(params.get("text", [""])[0])
                escaped = text.replace("\\", "\\\\").replace('"', '\\"')
                script = 'tell application "System Events" to keystroke "' + escaped + '"'
                subprocess.run(["osascript", "-e", script], check=True)
                self._json({"ok": True, "typed": text})
            elif parsed.path == "/key":
                key_name = params.get("key", ["return"])[0]
                code = KEY_CODES.get(key_name.lower())
                if code:
                    script = 'tell application "System Events" to key code ' + str(code)
                else:
                    script = 'tell application "System Events" to keystroke "' + key_name + '"'
                subprocess.run(["osascript", "-e", script], check=True)
                self._json({"ok": True, "key": key_name})
            elif parsed.path == "/combo":
                keys_str = params.get("keys", [""])[0]
                parts = [k.strip() for k in keys_str.split(",")]
                modifiers = []
                chars = []
                for p in parts:
                    if p.lower() in MODIFIER_MAP:
                        # Use AppleScript modifier name, not cliclick abbreviation
                        modifiers.append(MODIFIER_MAP[p.lower()])
                    else:
                        chars.append(p)
                if chars:
                    # Combo with a character: keystroke "g" using {command down, shift down}
                    char = chars[0]
                    mod_str = ", ".join([m + " down" for m in modifiers])
                    script = 'tell application "System Events" to keystroke "' + char + '" using {' + mod_str + '}'
                else:
                    # Modifier-only combo: key code 49 using {command down} (e.g., Cmd+Space)
                    code = KEY_CODES.get(parts[-1].lower(), 49)
                    mod_str = ", ".join([m + " down" for m in modifiers])
                    script = 'tell application "System Events" to key code ' + str(code) + ' using {' + mod_str + '}'
                result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
                self._json({"ok": result.returncode == 0, "combo": keys_str, "err": result.stderr.strip()})
            elif parsed.path == "/scroll":
                direction = params.get("dir", ["up"])[0]
                amount = int(params.get("amount", ["3"])[0])
                if direction == "down":
                    amount = -amount
                subprocess.run([CLICLICK, "sf:0," + str(amount)], check=True)
                self._json({"ok": True, "scroll": direction, "amount": abs(amount)})
            elif parsed.path == "/drag":
                x1, y1 = params.get("x1", ["0"])[0], params.get("y1", ["0"])[0]
                x2, y2 = params.get("x2", ["0"])[0], params.get("y2", ["0"])[0]
                subprocess.run([CLICLICK, "dd:" + x1 + "," + y1, "du:" + x2 + "," + y2], check=True)
                self._json({"ok": True, "dragged": {"from": [int(x1), int(y1)], "to": [int(x2), int(y2)]}})
            elif parsed.path == "/health":
                self._json({"status": "ok", "version": 5})
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            self._json({"ok": False, "error": str(e)})

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps(data).encode()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


print("W.Alter Screen Server v5 on :" + str(PORT))
http.server.HTTPServer(("127.0.0.1", PORT), ScreenHandler).serve_forever()
