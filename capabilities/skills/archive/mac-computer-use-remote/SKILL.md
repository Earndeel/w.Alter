---
name: mac-computer-use-remote
description: Remote Computer Use on Mac from VPS — screencapture via SSH, cliclick, screen server LaunchAgent, macOS TCC permissions, Brave CDP.
version: 1.0.0
author: W.Alter
metadata:
  hermes:
    tags: [mac, computer-use, ssh, vnc, screencapture, cliclick, tcc]
---

# Mac Computer Use — Remote from VPS

Control Lucas's Mac screen from the VPS via SSH tunnel. Screenshot → Vision AI → cliclick/osascript.

## Architecture

```
VPS → SSH tunnel → Mac:18765 (screen server) → screencapture → SCP → Vision AI → cliclick
```

## Prerequisites

1. **cliclick** installed: `brew install cliclick` (Mac)
2. **Screen Recording permission** for `/usr/bin/python3` in System Settings > Privacy & Security
3. **Accessibility permission** for `/usr/local/bin/cliclick` — required for mouse/keyboard simulation
4. **cmux** already has Screen Recording permission (Lucas added it)
4. **Screen server** running via LaunchAgent on Mac

## Screen Server (LaunchAgent)

- Script: `~/.hermes/scripts/walter-screen-server.py` on Mac (source: `references/walter-screen-server.py`)
- Plist: `~/Library/LaunchAgents/com.walter.screen-server.plist` (template: `templates/com.walter.screen-server.plist`)
- Port: `18765` (localhost only)
- Endpoints:
  - `GET /screenshot` → PNG of current screen
  - `GET /click?x=N&y=N` → click at coordinates
  - `GET /type?text=TEXT` → type text
  - `GET /key?key=return` → press key
  - `GET /health` → status check

### Restart server
```bash
ssh lucasjouvencon@100.127.150.1 'launchctl unload ~/Library/LaunchAgents/com.walter.screen-server.plist; launchctl load ~/Library/LaunchAgents/com.walter.screen-server.plist'
```

## macOS TCC (Screen Recording) — CRITICAL

`screencapture` from SSH returns **black screen** (97KB for 2880x1800 = all black). Real screenshot = 2-5MB.

**Root cause**: macOS TCC (Transparency, Consent, Control) requires each process to have Screen Recording permission. SSH sessions and LaunchAgent Python processes are separate from cmux.

**Fix**: Add the **exact Python binary** used by the LaunchAgent to System Settings > Privacy & Security > Screen Recording.
- Check the plist to find which Python is used: `grep -A1 ProgramArguments ~/Library/LaunchAgents/com.walter.screen-server.plist`
- The actual binary may be `/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python` (NOT `/usr/bin/python3`)
- Each Python binary is a separate TCC entry — adding one does NOT cover the other
- Or: `open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"`

**Pitfall**: Adding cmux is NOT enough — Python is a different process. Adding `/usr/bin/python3` is NOT enough if the plist uses CommandLineTools Python.

### Fallback: Launch via Terminal.app

If the LaunchAgent's Python binary doesn't have TCC permission but Terminal.app does:
```bash
ssh lucasjouvencon@100.127.150.1 'open -a Terminal ~/.hermes/scripts/walter-screen-server.py'
```
This launches the script inside Terminal.app's process, which inherits Terminal's Screen Recording permission. The Terminal window will open on the Mac — works as a quick fix until TCC is properly configured.

### cliclick Accessibility Permission

After installing `brew install cliclick`, the first click triggers a macOS dialog: *"Accessibility Access (Events)"*. The user must:
1. Click **"Open System Settings"** on the dialog
2. Enable `cliclick` in **Privacy & Security > Accessibility**

Without this, `cliclick` commands silently fail or return errors.

**Pitfall**: The dialog only appears once. If dismissed with "Deny", go manually to System Settings > Accessibility and add `/usr/local/bin/cliclick`.

## Brave Browser CDP

Brave supports Chrome DevTools Protocol. Steps:

1. **Quit Brave first** (if already running, CDP flag is ignored)
   ```bash
   ssh lucasjouvencon@100.127.150.1 'osascript -e "tell application \"Brave Browser\" to quit"'
   ```
2. **Relaunch with CDP**
   ```bash
   ssh lucasjouvencon@100.127.150.1 'nohup "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" --remote-debugging-port=9222 > /dev/null 2>&1 &'
   ```
3. **Create SSH tunnel**
   ```bash
   ssh -f -N -L 9222:localhost:9222 lucasjouvencon@100.127.150.1
   ```
4. **Connect via Playwright**
   ```python
   from playwright.sync_api import sync_playwright
   pw = sync_playwright().start()
   browser = pw.chromium.connect_over_cdp("http://localhost:9222")
   ```

### CDP Speed (v0.14.0 improvement)

- **180x faster** = persistent WebSocket connection (not new connection per call)
- First call: ~500ms (initialization)
- Subsequent calls: 60-150ms each (same connection)
- **Does NOT affect page load speed** — only CDP call overhead

## SSH Tunnel Summary

| Tunnel | Purpose |
|--------|---------|
| `localhost:9222 → Mac:9222` | Brave CDP (browser automation) |
| `localhost:18765 → Mac:18765` | Screen server (desktop Computer Use) |

## Screenshot Analysis

Vision model: **Gemini 3.1 Flash Lite** (configured as `auxiliary.vision` in config.yaml). Free, ~1-2s per analysis. Sufficient for identifying UI elements, buttons, text fields, and screen state.

For higher-fidelity analysis (small text, complex UIs), override with `vision_analyze` and specify a stronger model.

## Retina Coordinate Handling — CRITICAL

Mac Retina displays use **2x scaling**. The screenshot is in Retina pixels (e.g. 2880×1800) but `cliclick` and `osascript` use **logical points** (e.g. 1440×900).

**Rule**: When the vision model returns coordinates from a screenshot, **divide by 2** before passing to cliclick or the screen server `/click` endpoint.

```
Screenshot: 2880×1800 pixels
Logical:    1440×900 points
cliclick:   uses logical points
```

**Workflow**:
1. Take screenshot via screen server → returns Retina pixels
2. Vision model identifies button at pixel (X, Y)
3. Convert: `logical_x = pixel_x / 2`, `logical_y = pixel_y / 2`
4. Click via `cliclick c:logical_x,logical_y` or `/click?x=logical_x&y=logical_y`

**Pitfall**: Vision models often give inaccurate coordinates for small UI elements (buttons, links). SwiftUI apps are especially hard — buttons don't appear in AppleScript accessibility tree. If a click doesn't land, try:
- Shift by ±20px in each direction
- Use keyboard shortcuts instead (Enter to submit forms, Tab to navigate fields)
- Use menu bar via AppleScript (`click menu item "X" of menu "Y" of menu bar 1`)

## SwiftUI App Automation

SwiftUI apps (like Hermes Desktop) don't expose UI elements via AppleScript accessibility. Standard `click button "Name"` calls fail with "Can't get window" or "Invalid index".

**Workarounds**:
1. **Coordinate-based clicking** — use vision + Retina-corrected coordinates
2. **Keyboard navigation** — Tab between fields, Enter to submit, Escape to dismiss
3. **Menu bar** — `osascript -e 'tell application "System Events" to click menu item "X" of menu "Y" of menu bar 1'`
4. **AppleScript activate** — `osascript -e 'tell application "AppName" to activate'` before clicking

## Screen Server Permission Fix

The screen server LaunchAgent runs Python at `/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python`. If this Python binary doesn't have Screen Recording permission, screenshots return black (97KB for 2880x1800).

**Fix**: Launch via `open -a Terminal ~/.hermes/scripts/walter-screen-server.py` — this uses Terminal's Python context which inherits Screen Recording permission. The LaunchAgent plist must also reference the correct Python binary.

**Verify**: Real screenshots are 700KB-1MB+. Black screenshots are ~97KB.

## Retina Coordinate Handling

Screenshots from the screen server are 2880x1800 (Retina pixels). `cliclick` uses logical points (1440x900). Vision models return pixel coordinates from the screenshot.

**Conversion**: Divide vision-returned coordinates by 2 for cliclick/screen-server click endpoint.

## Hermes Desktop App Setup

Hermes Desktop (Swift/SwiftUI) connects to the VPS via SSH alias. 

### SSH User: must be root

The VPS runs Hermes as root, so `/root/.hermes/` is mode 700. The `ubuntu` user cannot access it even with ACLs or symlinks — the kernel checks group perms first when ubuntu is in the root group.

**Solution**: Enable root SSH login on the VPS:
1. Remove the forced-command rejection from `/root/.ssh/authorized_keys`:
   ```bash
   grep -v "Please login as" /root/.ssh/authorized_keys > /tmp/ak_clean
   mv /tmp/ak_clean /root/.ssh/authorized_keys
   ```
2. Add the Mac's public key without forced command
3. Update Mac SSH config: `User root` instead of `User ubuntu`
4. Update `~/Library/Application Support/HermesDesktop/connections.json`: set `"sshUser": "root"`
5. Remove `/home/ubuntu/.hermes` symlink (not needed)

**Pitfall**: Oracle Cloud VPS forces `PermitRootLogin prohibit-password` + rejects root login via `command=` in authorized_keys. Must remove both restrictions.

### SSH Alias pitfalls

1. **No LocalForward** — if forwarded ports are already in use, SSH exits 255 and the app sees "SSH authentication failed". Remove all `LocalForward` lines.
2. **IdentityFile must be absolute path** — `~` doesn't expand correctly in GUI app context. Use `/Users/lucasjouvencon/Desktop/Keys/ssh-key-2025-12-10.key`.

### App Config

- Preferences: `~/Library/Application Support/HermesDesktop/preferences.json`
- Connections: `~/Library/Application Support/HermesDesktop/connections.json`
- Connection fields: `sshAlias`, `sshHost`, `sshUser`, `label`, `id`

### App Sections

The app sidebar has: Connections, Overview, Sessions, Workflows, Cron Jobs, Kanban, Files, Usage, Skills, Terminal. All read data over SSH from `~/.hermes/` on the VPS.

## Pitfalls

**Support files**: `references/ssh-root-login-oracle-cloud.md` (root SSH fix details), `templates/ssh-config-walter-ts` (correct SSH config template).

- macOS screen locked/asleep → screencapture returns black even with permission
- `caffeinate -d -u -t 300` keeps display awake from SSH
- Swift compilation broken on Mac (Xcode module conflicts) — don't use swift/swiftc
- `screencapture -Cx` vs `screencapture -x` — different MD5s but both black without permission
- Brave must be fully quit before relaunching with `--remote-debugging-port`
- Vision model pixel coordinates ≠ cliclick logical points on Retina — always divide by 2
- `open -a Terminal <script>` gives the script a Python context with Screen Recording permission; direct `python3 script.py` from SSH may not
- **Scrapling CDP sessions are ISOLATED** — `mcp_scrapling_open_session` with `cdp_url=ws://...` creates a NEW browser context that does NOT share cookies/sessions with the existing Brave profile. Navigating to a logged-in site (Tinder, Instagram) will show the login page, not the user's session. To interact with the user's logged-in sessions, you must use the Brave CDP directly via Playwright (`browser.chromium.connect_over_cdp`) or open a new tab via `curl -X PUT http://localhost:9222/json/new?URL` — but even then, Scrapling's `fetch()` creates new contexts. **Workaround**: Use `execute_code` with Playwright directly for sites requiring existing sessions, or ask user to log in via the Scrapling session first.
- **Never use bind mount** for permission workarounds — `mount --bind /root/.hermes /home/ubuntu/.hermes -o ro` makes the SOURCE read-only too, breaking the running Hermes agent.
- **ACL masks reset** — `setfacl` masks get recalculated and can block access. Use standard `chmod` instead of ACLs.
- **ubuntu in root group** — if ubuntu is in gid 0, `chmod 705` fails because kernel checks group (`---`) before other (`r-x`). Use `chmod 755` instead.
