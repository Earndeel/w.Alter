# Desktop ↔ Server Token Authentication

## The Problem

When `HERMES_DESKTOP_REMOTE_URL` is set on the Mac but `HERMES_DESKTOP_REMOTE_TOKEN` is not, the Electron app (`main.cjs`) fails early — before any network request — and falls back to local gateway bootstrap. This causes the infamous boot loop:

```
[hermes] [boot] Desktop boot failed: HERMES_DESKTOP_REMOTE_URL is set but HERMES_DESKTOP_REMOTE_TOKEN is not.
```

Then:
1. App tries to spawn local Python gateway → fails (missing Python, permissions, etc.)
2. Renderer crashes (SIGTERM)
3. App restarts → same cycle

## Solution: Align token on both sides

### Server side (systemd)

Inject the token into both service unit files:

```
# /root/.config/systemd/user/hermes-dashboard.service
[Service]
Environment=HERMES_DASHBOARD_SESSION_TOKEN=<token>

# /root/.config/systemd/user/hermes-gateway.service  
[Service]
Environment=HERMES_DASHBOARD_SESSION_TOKEN=<token>
```

Then: `systemctl --user daemon-reload && systemctl --user restart hermes-gateway hermes-dashboard`

### Mac side

Set the matching environment variable before launching the app:

```bash
export HERMES_DESKTOP_REMOTE_TOKEN=<same-token>
open -a "Hermes V2"
```

Or via launchd: add to the app's `launchctl setenv` or the `Info.plist` `LSEnvironment` dict.

### Token flow

```
Mac: HERMES_DESKTOP_REMOTE_TOKEN → X-Hermes-Session-Token header → Server: validates against HERMES_DASHBOARD_SESSION_TOKEN
```

The dashboard (`web_server.py`) validates the `X-Hermes-Session-Token` header against the env var. This is DNS rebinding protection — do NOT disable it. Align the tokens instead.
