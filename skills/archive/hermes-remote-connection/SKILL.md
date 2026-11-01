---
name: hermes-remote-connection
description: Connect Hermes desktop or TUI client to a remote server when the local gateway is unavailable. Covers ECONNREFUSED 127.0.0.1:9119 and port architecture.
category: devops
---

# Hermes Remote Connection

When the desktop or TUI client fails with `ECONNREFUSED 127.0.0.1:9119`, it cannot reach a dashboard at the expected localhost port.

## Hermes Port Architecture

Three services, three distinct roles — they are NOT interchangeable:

| Service | Typical Port | Exposes |
|---|---|---|
| Gateway messaging | 8642 | Internal messaging bus; only `/health` |
| Dashboard web + API | 9119 (8787 if non-default) | Full UI, REST API, WebSocket at `/api/ws` |
| API Server | 9120 | Platform-specific endpoints |

**The desktop/TUI client connects to the dashboard**, not the gateway. The gateway on port 8642 only serves `/health` — the client needs `/api/status`, `/v1/models`, and `/api/ws` which only the dashboard provides.

## Diagnosis

Identify what is listening on the server (see references/diagnostic.md for commands). Check also the dashboard port in the Hermes configuration file.

## Desktop SSH mode (preferred for current builds)

Current Hermes Desktop builds expose `Settings → Gateway → Connect via SSH`. Use the existing key-based SSH alias that can run Hermes on the remote host, leave the remote Hermes path blank for auto-detection, run `Test SSH`, then `Connect`. Desktop owns a remote dashboard and forwards it to a local loopback port, so the Host header remains compatible without exposing the dashboard publicly.

If the UI reports that `HERMES_DESKTOP_REMOTE_URL` / `HERMES_DESKTOP_REMOTE_TOKEN` override saved settings, clear both macOS launch environment variables, fully quit Desktop, and relaunch before applying the saved SSH configuration.

## Tailscale direct (only after deliberate trust patches)

Tailscale direct survives Mac sleep, but newer dashboards reject non-loopback Host headers by design. Use it only when the HTTP and WebSocket trust paths have both been restricted to the operator-controlled Tailscale host/IP and token validation remains enabled for every other host. Verify an accepted request and a rejected arbitrary Host before relying on the route.

## SSH Tunnel (legacy)

Map a local loopback port to the server's actual dashboard port (see `references/tunnel-setup.md`). Keep the tunnel alive, then point Desktop at the loopback URL. This is a safe compatibility path but can disappear across Mac sleep.

## Attach Mode (Alternative)

Set `HERMES_TUI_GATEWAY_URL` to a WebSocket URL pointing at the remote dashboard before launching the client. The WebSocket path is `/api/ws`, not `/ws` or `/`.

## Update-era Host-header diagnostic

After an update, classify the route before changing services:

- loopback dashboard and loopback forwarder return HTTP 200;
- the direct Tailscale/non-loopback route returns HTTP 400 with `Invalid Host header`.

That pattern means the dashboard is healthy and host-header middleware is rejecting only the direct route. It is not, by itself, a VM outage, port failure, or token mismatch. A successful `/api/status` probe is insufficient; verify the authenticated `/api/ws` path too.

## Pitfalls

- Port 8642 (gateway) is NOT the dashboard. Health check passes but API calls fail.
- A custom `--port` flag on `hermes dashboard` changes the dashboard port from its default.
- The desktop client needs the dashboard's full API and WebSocket surface, not the gateway health port.
- Never disable Host validation or bypass token checks globally as a connectivity workaround.

## References

- `references/diagnostic.md` — Step-by-step port layout diagnosis
- `references/tunnel-setup.md` — SSH tunnel commands and verification
- `references/attach-mode.md` — WebSocket attach mode alternative
