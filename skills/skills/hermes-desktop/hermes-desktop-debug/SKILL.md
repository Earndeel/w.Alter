---
name: hermes-desktop-debug
description: "Use when diagnosing or fixing Hermes V2 macOS Electron desktop failures such as white screens, boot loops, connectivity or auth errors, or investigating connection-file precedence, TLS rejection, supervised proxies, dashboard reloads, and recurring WebSocket disconnects."
---

# Hermes Desktop Debug

Diagnose and fix Hermes V2 Electron desktop app failures on macOS: white screen, boot loop, ECONNREFUSED, auth failures.

## Architecture (critical context)

The Electron app has TWO independent paths:

1. **Renderer**: loads a **local** `dist/index.html` from the packaged `.app` bundle — NOT the remote URL. If this file is missing, the window renders a silent white/blank screen with no visible error.
2. **Backend connection**: `startHermes()` reads `HERMES_DESKTOP_REMOTE_URL` and `HERMES_DESKTOP_REMOTE_TOKEN` env vars, calls `resolveRemoteBackend()`, then `ensureBackend()`. This connects to the remote server for API calls after the renderer is already loaded.

These two paths fail independently. A working backend connection does NOT fix a missing renderer bundle.

## Diagnostic Checklist (in order)

Run `scripts/diagnose.sh` on the Mac for automated triage, or follow the manual steps below.

### Step 1: Check env vars on macOS

GUI apps on macOS do NOT inherit shell env vars. They read from `launchctl`:

```
launchctl getenv HERMES_DESKTOP_REMOTE_URL
launchctl getenv HERMES_DESKTOP_REMOTE_TOKEN
```

If either is empty, the app cannot connect:
- URL set + token missing → `Error: HERMES_DESKTOP_REMOTE_URL is set but HERMES_DESKTOP_REMOTE_TOKEN is not` (line 4934 of main.cjs) → boot loop or white screen
- Token set + URL missing → falls through to local bootstrap (line 4941+), which tries to spawn a local gateway → ECONNREFUSED or hang

Set them with:

```
launchctl setenv HERMES_DESKTOP_REMOTE_URL "https://w-alter.tail32cf1c.ts.net"
launchctl setenv HERMES_DESKTOP_REMOTE_TOKEN "<token>"
```

Then **quit the app completely (Cmd+Q)** and relaunch. `launchctl setenv` only takes effect on new process launches.

### Step 2: Check renderer bundle exists

The file loaded by the Electron window is:

```
/Applications/Hermes V2.app/Contents/Resources/app.asar.unpacked/dist/index.html
```

Verify:

```
ls -la "/Applications/Hermes V2.app/Contents/Resources/app.asar.unpacked/dist/index.html"
```

If missing → white screen regardless of backend health. Rebuild with:

```
cd /path/to/hermes-agent/apps/desktop && hermes desktop --force-build
```

Then re-package the .app and reinstall on the Mac.

### Step 3: Verify server-side from Mac

Once env vars are set, verify the backend is reachable:

```
curl -sk https://w-alter.tail32cf1c.ts.net/api/status \
  -H "X-Hermes-Session-Token: $(launchctl getenv HERMES_DESKTOP_REMOTE_TOKEN)"
```

Should return 200 with JSON status. If 401 → token mismatch. If connection refused → Tailscale/serve issue.

### Step 4: Check Tailscale serve on server

The dashboard must be exposed via Tailscale:

```
tailscale serve status
```

Should show port 8787 served at the MagicDNS URL. If not running:

```
tailscale serve --bg 8787
```

### Step 5: Check server-side services

```
systemctl --user status hermes-dashboard hermes-gateway
```

Both must be active. The dashboard service needs `HERMES_DASHBOARD_SESSION_TOKEN` in its environment (matching the Mac token). The `web_server.py` host header check must accept the Tailscale MagicDNS hostname.

## Key source locations (in main.cjs)

| Concern | Function / Area | Approx. line |
|---------|----------------|-------------|
| Env var resolution | `resolveRemoteBackend()` | 4895-4945 |
| Renderer file loading | `resolveRendererIndex()` | 2736-2760 |
| Window creation | `createWindow()` | 5900+ |
| Bootstrap orchestration | `startHermes()` | 5453+ |
| Renderer crash handler | `render-process-gone` listener | 5974 |

## Runtime ownership and restart boundaries

Before claiming that a Desktop-visible change is live, identify which long-lived process owns the stale state and verify its start time. Electron, the remote dashboard, TUI sessions, and per-session gateway workers are separate lifecycles; restarting the Mac app does **not** reload Python modules already imported by a remote `hermes-dashboard.service`.

1. Map each relevant PID to its parent tree, command, start time, listening ports, and systemd unit.
2. Classify it before acting: Desktop renderer, shared dashboard, independent TUI session, or session worker. Similar `ui-tui/dist/entry.js` / `tui_gateway` commands are not proof that a process is orphaned.
3. Compare the process start time with the source/config modification time. A successful source-level test proves the next process will behave correctly; it does not prove the current process reloaded it.
4. Determine restart blast radius. A shared dashboard restart can terminate active sessions, LSPs, MCP servers, proxies, and user jobs in its cgroup. Never restart it merely to refresh a label without explicit approval or a safe maintenance window.
5. Verify the actual rendered picker or live API after reload before saying the UI is fixed. Do not substitute unit tests or importing the modified function in a fresh interpreter for runtime verification.

See `references/runtime-reload-boundaries.md` for a compact diagnosis and verification recipe.

## Common Pitfalls

- **Restarting the wrong layer**: Cmd+Q/reopening Electron refreshes the renderer and its environment, but not a remote dashboard's imported code or registry cache.
- **Mistaking old processes for orphans**: inspect `pstree`, session ownership, and service cgroups first. Never infer orphan status from age or duplicate-looking commands alone.
- **`launchctl setenv` then reopen without quitting**: The old process keeps the stale env. Must Cmd+Q fully.
- **Launcher script using `open` can preserve/reintroduce stale env**: verify the real process environment with `ps auxwwE | grep '/Applications/Hermes V2.app/Contents/MacOS/Hermes'`. If it still shows an old `HERMES_DESKTOP_REMOTE_URL` (for example `http://localhost:9119`), launch the binary directly instead of `open`: `HERMES_DESKTOP_REMOTE_URL=http://100.91.35.121:8788 HERMES_DESKTOP_REMOTE_TOKEN=no-auth "/Applications/Hermes V2.app/Contents/MacOS/Hermes" &`. Patch `/usr/local/bin/hermes-v2` to exec the app binary with explicit env.
- **Stubborn `localhost:9119` fallback**: if LaunchServices or old app state keeps returning to `http://localhost:9119`, create a user LaunchAgent that runs a tiny Python TCP proxy from `127.0.0.1:9119` to the working Tailscale endpoint (for example `100.91.35.121:8788`). Verify with `curl http://127.0.0.1:9119/api/status`; then even stale desktop env works.
- **Three separate auth gates can fail independently**: `/api/status` is public, but REST API, `/api/ws`, and handler-level `_require_token()` may each still reject stale Electron tokens. If the deployment intentionally trusts the Tailscale/local proxy path, patch all three paths consistently: `auth_middleware`, `_require_token()`, and `_ws_auth_reason()`. Verify with wrong-token tests: `curl http://127.0.0.1:9119/api/config -H 'X-Hermes-Session-Token: wrong'` and `ws://127.0.0.1:8787/api/ws?token=wrong` should both succeed only in that trusted deployment.
- **Token mismatch**: The Mac `HERMES_DESKTOP_REMOTE_TOKEN` and server `HERMES_DASHBOARD_SESSION_TOKEN` must be identical unless the server was deliberately patched to ignore tokens for trusted Tailscale clients.
- **Host header rejection (v0.18.2+)**: The dashboard now validates `Host` headers against the bound interface (GHSA-ppp5-vxwm-4cf7). Tailscale IP or MagicDNS connections are rejected with 400. Fix: add the server's Tailscale addresses to `_TAILSCALE_ACCEPTED_HOSTS` in `web_server.py`, or switch to an SSH tunnel (Host becomes `127.0.0.1`). See `desktop-app-tailscale` references for the code patch.
- **Build artifact missing after update**: If `hermes desktop --force-build` was interrupted or failed, `dist/` may be missing. The app loads a blank page silently — no error dialog.
- **`/usr/bin/ssh: cannot execute binary file` on Mac**: Indicates corrupted SSH binary or architecture mismatch. Not a Hermes issue but blocks tunnel-based connectivity.

## Also covers (hermes-desktop-debug)

Read `references/merged-hermes-desktop-debugging/hermes-desktop-debug.md` for connection resolution, TLS failures, current v0.20.x proxy/Host behavior, dashboard cgroup restart traps, or Desktop cycling despite successful REST probes.

It documents `connection.json` taking precedence over environment variables, then local bootstrap. Electron rejects self-signed/internal-PKI certificates; use the documented plain-HTTP forwarding path. For the current deployment, keep Dashboard on loopback and use the supervised Mac proxy: `127.0.0.1:9119` → Tailscale server `8788` → Dashboard `127.0.0.1:8787`, rewriting upstream Host to the loopback authority. `HERMES_DASHBOARD_ACCEPTED_HOSTS` is unused; do not set `dashboard.public_url` to a Tailscale IP as a Host workaround. Verify protected routes reject unauthenticated requests and arbitrary Hosts remain rejected.

Its detached dashboard reload helper addresses session shells inside the service cgroup; retain the kept skill's approval and process-ownership guardrails. For recurring disconnects, soak an authenticated WebSocket beyond the relay timeout; Python relays must clear the upstream timeout after connecting.

Read `references/merged-hermes-desktop-debugging/references/commands.md` for diagnostic steps and `references/merged-hermes-desktop-debugging/references/server-config.md` for service, auth, Host, and port details.
