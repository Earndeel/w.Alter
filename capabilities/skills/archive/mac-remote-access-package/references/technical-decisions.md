# macOS Remote Access — Technical Decisions & Pitfalls

## Why VNC + SSH, not just one

- **SSH alone** gives terminal but no GUI. cliclick from SSH needs Accessibility permissions (manual toggle in System Prefs) and a logged-in GUI session — brittle.
- **VNC alone** gives GUI but no programmatic control or file ops.
- **Together** they cover all use cases: VNC for visual verification + clicking, SSH for everything else.

## Gatekeeper bypass

macOS blocks unsigned `.command` files. The remote user must:
- Right-click → Open (first launch only)
- Or: System Preferences → Privacy & Security → "Open Anyway"

No clean workaround without a paid Apple Developer account ($99/year).

## Tailscale auth

Two options:
1. **Auth key** (ephemeral, single-use): generate at admin.tailscale.com → paste into installer. Best UX.
2. **Interactive**: script opens browser, user logs into Tailscale. Works but requires the remote user to have a Tailscale account (or we create one).

## The manual step that can't be automated

Screen Sharing activation via `kickstart` enables the VNC port, but macOS still requires the user to explicitly check "Screen Sharing" in System Preferences → Sharing. The script opens the pane — user must click the checkbox.

## Persistent tunnel details

The launchd plist at `~/Library/LaunchAgents/com.walter.keepalive.plist`:
- Opens SSH reverse tunnels: remote port 19922 → localhost:22, remote port 15900 → localhost:5900
- `KeepAlive` + `ServerAliveInterval` = survives sleep/wake cycles
- `ExitOnForwardFailure=yes` = fails loudly if the relay host is unreachable
- Logs to `/tmp/walter-tunnel.log` and `/tmp/walter-tunnel.err`

## cliclick (optional addition)

If programmatic clicks are needed beyond what VNC provides:
```bash
brew install cliclick
```
Then from SSH: `cliclick c:500,300` (click at coordinates). Requires Accessibility permission grant in System Preferences → Privacy → Accessibility → Terminal.

## The relay host

The reverse tunnel needs a relay host reachable via Tailscale. Currently: `w-alter` (the VPS). The remote ports are bound on the relay — W.Alter connects to `localhost:19922` (SSH) and `localhost:15900` (VNC) on the relay.
