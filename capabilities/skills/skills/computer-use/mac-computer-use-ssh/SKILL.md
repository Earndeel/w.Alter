---
name: mac-computer-use-ssh
description: "Computer Use on Mac via SSH — screencapture + cliclick + osascript + vision AI. Full pipeline: screenshot → analyze → click/type/key/scroll/drag/combo."
version: 3.1.0
author: walter
metadata:
  hermes:
    tags: [computer-use, mac, ssh, automation]
    fallback_for_tools: [computer_use]
---

# Mac Computer Use via SSH

Control Lucas's Mac screen remotely from the VPS: see the screen, analyze it with vision AI, click anywhere, type text, press keys, run keyboard combos, scroll, drag.

**Operating principle**: Use terminal/commands/API first for speed. Screenshot + click only when GUI interaction is genuinely needed. This is a user preference — don't default to Computer Use when a CLI approach exists.

## Architecture

```
VPS → SSH tunnel → Mac:18765 (W.Alter Screen Server) → screencapture/cliclick/osascript → Vision AI
Deploy: copy to Mac `~/.hermes/scripts/walter-screen-server.py`, load LaunchAgent, tunnel port 18765. Active template: `walter-screen-server-v7.py`.

**Version history:** v4 — basic screencapture + cliclick. v5 — osascript combos (fixed modifier mapping: cmd→command, ctrl→control, opt→option). v6 — first foreground approval gate. v7 — task-bound approval with heartbeat, explicit release, idle timeout and hard safety maximum.

## Components

| Component | Location | Purpose |
|---|---|---|
| W.Alter Screen Server v7 | Mac LaunchAgent on `:18765` | HTTP API; captures/status are passive, visible input is task-approved |
| `cliclick` | `/usr/local/bin/cliclick` (brew) | Mouse clicks, scroll, drag |
| `osascript` | macOS built-in | Keyboard input and native approval dialog |
| `screencapture` | macOS built-in | Passive screen capture (needs TCC permission) |
| Vision AI | Auxiliary model | Screenshot analysis; never triggers the approval dialog |
| SSH tunnel | VPS `localhost:18765` → Mac | Secure channel |

## Endpoints (v7)

All on `http://localhost:18765` (via SSH tunnel):

| Endpoint | Params | Description |
|---|---|---|
| `/screenshot` | — | Passive PNG screenshot; never prompts |
| `/health` | — | Passive server health/version; never prompts |
| `/control-status` | — | Passive approval state; never prompts |
| `/request-control` | `task_id`, optional `reason` | Shows the native dialog for visible control |
| `/control-heartbeat` | `task_id`, `approval_token` | Keeps the approved task alive; no dialog |
| `/release-control` | `task_id`, `approval_token` | Releases the approved task; no dialog |
| `/click?x=N&y=N` | `task_id`, optional token | Visible left click; approval required unless `background=1` |
| `/doubleclick?x=N&y=N` | `task_id`, optional token | Visible double click; approval required unless `background=1` |
| `/rightclick?x=N&y=N` | `task_id`, optional token | Visible right click; approval required unless `background=1` |
| `/type?text=TEXT` | `task_id`, optional token | Visible text entry; approval required unless `background=1` |
| `/key?key=NAME` | `task_id`, optional token | Visible key press; approval required unless `background=1` |
| `/combo?keys=k1,k2` | `task_id`, optional token | Visible key combo; approval required unless `background=1` |
| `/scroll?dir=up&amount=N` | `task_id`, optional token | Visible scroll; approval required unless `background=1` |
| `/drag?x1=N&y1=N&x2=N&y2=N` | `task_id`, optional token | Visible drag; approval required unless `background=1` |

The approval lease is bound to one task, expires after 60 seconds without
activity, and has a 10-minute hard maximum. Call `/release-control` as soon
as the visible task is complete. `background=1` is reserved for operations
that genuinely cannot disturb the user; do not use it to suppress a visible
interaction.

## Setup

### Prerequisites (already done on Lucas's Mac)
1. `brew install cliclick`
2. Screen server v7 deployed to `~/.hermes/scripts/walter-screen-server.py`
3. LaunchAgent at `~/Library/LaunchAgents/com.walter.screen-server.plist`

### TCC Permissions (macOS System Settings)

Two separate permissions must be granted **manually** by the user:

| Permission | Where | For what | How to add CLI tools |
|---|---|---|---|
| **Screen Recording** | Privacy & Security → Screen Capture | `screencapture` | Add `cmux` (or Terminal) |
| **Accessibility** | Privacy & Security → Accessibility | `cliclick` + `osascript` | Add `cliclick` |

**Adding CLI binaries**: System Settings → Privacy → click "+" → press **⌘Cmd+⇧Shift+G** (Go to Folder) → type `/usr/local/bin/cliclick` or `/usr/bin/python3`.

**Key pitfall**: Each process needs its own permission. The LaunchAgent's Python process is different from cmux. If screenshots are black (~97KB for 2880x1800 = black), the process running `screencapture` lacks Screen Recording permission. A real screenshot is 300KB-1.5MB.

### SSH Tunnel
```bash
ssh -o ConnectTimeout=5 -f -N -L 18765:localhost:18765 -i ~/.ssh/id_ed25519 lucasjouvencon@100.127.150.1
# Verify:
curl -s http://localhost:18765/health
```

## Usage Pattern

```python
import urllib.request, urllib.parse, json, os

BASE = "http://localhost:18765"

def screenshot(path="/tmp/cu_screen.png"):
    urllib.request.urlretrieve(f"{BASE}/screenshot", path)
    return path, os.path.getsize(path)

def request_control(task_id, reason):
    query = urllib.parse.urlencode({"task_id": task_id, "reason": reason})
    return json.loads(urllib.request.urlopen(f"{BASE}/request-control?{query}", timeout=90).read())

def action(path, task_id, token, **params):
    params.update({"task_id": task_id, "approval_token": token})
    query = urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(f"{BASE}{path}?{query}", timeout=10).read())

def heartbeat(task_id, token):
    query = urllib.parse.urlencode({"task_id": task_id, "approval_token": token})
    return json.loads(urllib.request.urlopen(f"{BASE}/control-heartbeat?{query}", timeout=10).read())

def release_control(task_id, token):
    query = urllib.parse.urlencode({"task_id": task_id, "approval_token": token})
    return json.loads(urllib.request.urlopen(f"{BASE}/release-control?{query}", timeout=10).read())
```

Only `request_control()` opens the native dialog. `screenshot()`, vision
analysis, health, status, heartbeat and release are passive. For a visible
task: request approval once, use `action(...)` for clicks/typing/keys/scroll
or drag, heartbeat during long reasoning, then call `release_control()`.
Use `background=1` only for a genuinely invisible operation.

### Full Computer Use Cycle
```python
# 1. See — no dialog
path, sz = screenshot()
# 2. Analyze (via vision_analyze tool — no dialog)
# 3. Before any visible click/type/key/scroll/drag:
lease = request_control("task-123", "raison précise")
# 4. Act only with the approved task/token
click_result = action("/click", "task-123", lease["approval_token"], x=target_x, y=target_y)
# 5. Verify — screenshot remains passive
path2, sz2 = screenshot()
# 6. Release immediately when the visible task ends
release_control("task-123", lease["approval_token"])
```

## Performance (benchmarked)

| Action | Latency |
|---|---|
| Screenshot | ~400-500ms (avg 467ms, min 407ms, max 724ms) |
| Click | ~300-350ms |
| Type text | ~800-900ms |
| Key press | ~300ms |
| Key combo (osascript) | ~600-1000ms |
| Scroll | ~1000ms |
| **Full cycle (screenshot+click+verify)** | **~1-2s** |

## Server v7 safeguards and fixes

- Foreground approval is enforced only by the visible input routes: click, double-click, right-click, type, key, combo, scroll and drag.
- Passive routes — screenshot, health, control-status, heartbeat and release — never display a dialog.
- Task-bound lease: explicit `task_id`, approval token, heartbeat, `/release-control`, 60-second idle timeout and 10-minute hard maximum.
- `background=1` bypasses the dialog only when the caller explicitly declares that the operation cannot disturb the user.
- Modifier mapping: `cmd→command`, `ctrl→control`, `opt→option` (AppleScript requires full names, not cliclick abbreviations)
- Use `CLICLICK_MODS[p.lower()]` not `p.lower()` when building modifier list
- Special keys use `key code N` (space=49, tab=48, escape=53, return=36, delete=51)
- Combos: `keystroke "g" using {command down, shift down}` or `key code 49 using {command down}`
- osascript for combos, cliclick for mouse only

## Pitfalls

### macOS TCC (Transparency, Consent, Control)
- **Black screenshots (~97KB)**: The process lacks Screen Recording permission. Each process type (cmux, Terminal, python3) needs separate permission in System Settings.
- **Clicks ignored**: `cliclick` lacks Accessibility permission. Add it in Privacy & Security → Accessibility.
- **Permissions need app restart**: After granting TCC permission, the app/process may need to be restarted to pick it up.
- **`screencapture` via SSH**: Runs as child of the SSH session. Permission is inherited from the parent (cmux/Terminal).
- **TCC permissions are session-specific**: If cmux restarts or the Mac reboots, Screen Recording permission may need to be re-granted. Black screenshots after a period of working = check TCC first. Even re-adding cmux to Screen Recording may not take effect until the SSH session is restarted.
- **Screen must be unlocked**: `screencapture` returns a black image (~97-100KB) if the Mac screen is locked or asleep. Ask user to wake/unlock before screenshotting. A real screenshot is 300KB-1.5MB for Retina.

### osascript Key Combos
- **WRONG**: `keystroke "g" using {command}` → error "Can't make {command} into type constant"
- **RIGHT**: `keystroke "g" using {command down}` — must use `X down` form for each modifier
- **Modifier-only combos** (like Cmd+Space): Use `key code N using {command down}` — can't use `keystroke` without a character. Key codes: space=49, tab=48, escape=53, return=36, delete=51.
- **Multiple modifiers**: `keystroke "g" using {command down, shift down}`

### Cookie Management
- **NEVER clear ALL cookies** — `context.clear_cookies()` in Playwright wipes EVERY domain (X, Google, xAI, etc.). The user gets logged out of everything. Always target specific domains: `context.clear_cookies(domain='.x.ai')` or delete specific cookies by name.
- **OAuth flows via CDP** — when an OAuth flow requires browser login (e.g., xAI → X), the user's existing sessions in Brave are critical. Clearing them breaks the flow and forces manual re-login.

### Browser & Mac Usage Policy
- **Lucas uses Brave, never Safari**: always use Brave (`/Applications/Brave Browser.app`) for browser automation on Mac.
- **NEVER use Mac Brave for scraping/research**: Every navigation, click, or scroll via CDP hijacks Lucas's active browser session. He can't use his Mac while we control it. Use **VPS headless Chromium** or **Scrapling** for all scraping tasks. Reserve Mac CDP exclusively for Computer Use (seeing/clicking/typing on his actual desktop when no CLI alternative exists).
- **x_search for X research**: Use `x_search` tool (xAI Grok) for all X/Twitter research. Returns URLs + Grok synthesis. Don't scrape X via Mac Brave.

### Coordinates
- **Retina screenshot pixels are not cliclick coordinates.** Read the actual screenshot dimensions and logical desktop bounds (for example `tell application "Finder" to get bounds of window of desktop`); convert screenshot coordinates proportionally before sending native clicks. For a 2880×1800 screenshot of a 1440×900 desktop, divide both axes by two. Never assume a fixed scale; multiple displays require their own bounds.
- **Cropped vision results** are relative to the crop origin: add the crop offset before converting to logical desktop coordinates.
- **Foreground target guard**: immediately before a global click, verify both the frontmost application and the exact target tab URL. Refuse the click if focus changed; do not click whatever application is now in front or silently steal focus.
- **Coordinate system**: Origin (0,0) is top-left. x increases right, y increases down.

### Server Lifecycle
- **LaunchAgent auto-starts** on Mac login — no manual start needed.
- **If server dies**: `launchctl unload/load ~/Library/LaunchAgents/com.walter.screen-server.plist`
- **Check health**: `curl http://localhost:18765/health`
- **Server logs**: `/tmp/walter-screen-server.log`

### SSH Tunnel
- Tunnel must be active from VPS side. Check with health endpoint.
- If tunnel drops: re-run the `ssh -f -N -L` command.
- Multiple tunnels possible (e.g., 9222 for Brave CDP, 18765 for screen server).

### Cookie Management (Critical)
- **NEVER clear ALL cookies** — `context.clear_cookies()` in Playwright wipes EVERY domain (X, Google, xAI, etc.). The user gets logged out of everything. Always target specific domains: `context.clear_cookies(domain='.x.ai')` or delete specific cookies by name.
- **OAuth flows via CDP** — when an OAuth flow requires browser login (e.g., xAI → X), the user's existing sessions in Brave are critical. Clearing them breaks the flow and forces manual re-login.

### Fallback: Brave CDP when TCC fails
If Screen Recording permission drops and user can't re-grant immediately, use **Brave CDP** (`playwright-cdp-browser-control` skill) as fallback for web-based tasks. CDP connects to the browser directly (no TCC needed) — can navigate, click, type, screenshot web pages. Cannot see the full desktop or non-browser apps.
