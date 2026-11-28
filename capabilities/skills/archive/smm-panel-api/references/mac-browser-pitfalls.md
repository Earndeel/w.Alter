# Mac Browser Interaction Pitfalls

Lessons learned from interacting with Brave Browser on macOS remotely via SSH + AppleScript + screen server.

## Brave Dual-Instance Crash

**Never** start a second Brave instance with `--remote-debugging-port`. This crashes the main Brave — all tabs go black, pages stop rendering. The second instance conflicts with the first's profile lock.

**If it happens:**
```bash
pkill -f "remote-debugging-port"   # kill the rogue instance
pkill -f "Brave Browser"           # kill everything
sleep 3
open -a "Brave Browser"            # restart clean
```

Brave will restore tabs from session state (usually). Check with:
```bash
osascript -e 'tell application "Brave Browser" to get title of active tab of front window'
```

## AppleScript `do javascript` in Brave

Requires a one-time GUI setting: **View > Developer > Allow JavaScript from Apple Events**.

Without it, all `do javascript` calls fail with error `-2741` ("Expected end of line but found identifier"). Cannot be enabled via SSH — requires clicking the menu item in the GUI.

**Workarounds when `do javascript` is unavailable:**
- Use `curl` with extracted cookies instead of in-browser JS
- Use the screen server (port 18765) for screenshots + click/type
- Use `osascript` to navigate tabs (this works without the setting): `tell application "Brave Browser" to set URL of tab N of front window to "https://..."`

## Screen Server Screenshots

The screen server runs at `http://localhost:18765` on the Mac.

**Prerequisites for good screenshots:**
1. Activate Brave first: `osascript -e 'tell application "Brave Browser" to activate'`
2. Wait 1-2 seconds for the window to come to foreground
3. Then: `curl -s http://localhost:18765/screenshot -o /tmp/screenshot.png`

**Size heuristic:**
- 400KB+ = real page content visible
- 100-160KB = menu bar only or black screen (wrong app in foreground)
- ~97KB = completely black screenshot

**Navigation via AppleScript (no `do javascript` needed):**
```bash
# Set URL of specific tab
osascript -e 'tell application "Brave Browser" to set URL of tab 15 of front window to "https://example.com"'
# Get URL of specific tab
osascript -e 'tell application "Brave Browser" to get URL of tab 15 of front window'
# List all tabs
osascript -e 'tell application "Brave Browser" to repeat with t in tabs of front window to get URL of t'
```

## Session Cookie Lifecycle

When extracting cookies from Brave's SQLite DB for API calls:
1. Cookies are encrypted — decrypt using vault key (see `brave-cookie-extraction.md`)
2. PHPSESSID cookies are ephemeral — they expire when the browser session ends
3. After restarting Brave, old PHPSESSID values are invalid
4. Always test cookies with a GET request before using them for POST
5. Yii2 CSRF tokens are single-use — each POST invalidates the current token
