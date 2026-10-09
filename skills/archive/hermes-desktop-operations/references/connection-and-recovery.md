# Hermes Desktop connection and recovery reference

Use this reference for remote setup, tunnel/Tailscale failures, Host validation, token scope, and renderer recovery. Keep the Dashboard loopback-bound unless a deliberate, authenticated reverse-proxy design has been verified against the running version.

## Connection precedence and token contract

Resolve connection state in this order:

1. The active profile's saved remote override.
2. `HERMES_DESKTOP_REMOTE_URL` plus `HERMES_DESKTOP_REMOTE_TOKEN`.
3. The saved global remote configuration.
4. Local bootstrap only when no remote configuration is selected.

A remote URL without a token is an explicit error. The Electron window still loads its local packaged HTML; remote mode changes API/WebSocket traffic, not the renderer source. On macOS, GUI processes receive `launchctl` values only on a fresh process launch, so fully quit Hermes after changing them. When a saved connection is authoritative, preserve unrelated keys and verify the actual running bundle path.

The server session token and the client token must refer to the same live session unless the current deployment explicitly documents another authenticated mechanism. Never report, commit, or echo token values. A token-like sentinel can pass a public readiness check while protected routes fail.

## Probe ladder

Run probes from the same client path the desktop uses:

1. `GET /api/status` for reachability and basic liveness.
2. A protected REST route for token enforcement.
3. An authenticated `/api/ws` connection held idle longer than the relay's connect timeout.
4. The actual desktop log and renderer state.

A status `200` alone is not a healthy-desktop verdict. An authenticated REST success with a WebSocket that closes at a fixed interval points to a relay retaining its bounded connect timeout after `create_connection`; clear the upstream timeout before full-duplex reads and repeat an idle soak.

## Failure matrix

| Symptom | Isolate first | Safe next action |
|---|---|---|
| Blank/white window | Missing local renderer entry point, missing GUI variables, or rejected TLS/proxy path | Inspect the installed bundle, both remote variables, and the exact endpoint separately. |
| `400 Invalid Host` | Host-validation middleware at a loopback-bound Dashboard | Use an SSH loopback tunnel, or add a narrow current-version Host allowlist for direct Tailscale. |
| `401` on protected routes | Client/server token mismatch or wrong active service | Compare presence and scope without printing values; inspect the service that owns the listener. |
| `403` on WebSocket while HTTP works | Separate WebSocket host/auth path or stale token | Test the WebSocket with the real token and inspect its dedicated auth function; do not bypass auth casually. |
| `ECONNREFUSED` after sleep | Dead SSH forward or supervised relay | Confirm the forward owner and an established connection, then restart only that known forward. |
| Timeout/backend not ready | Wrong endpoint, dead relay, retained socket timeout, or server readiness | Hold REST and WebSocket probes from the client before resetting renderer state. |
| `Gateway needs setup` or offline | Stopped gateway, local-mode connection, wrong bundle, or stale renderer | Query remote status first, then repair the client contract/state. |

## Forwarding choices

### SSH loopback tunnel

Use a loopback SSH forward when the server should remain unchanged or Host validation is uncertain. The client should target a local address such as `127.0.0.1:9119`, which reaches the Dashboard's loopback port. This is reversible and avoids TLS certificate surprises, but Mac sleep can terminate forwarding while leaving a misleading SSH process behind. Check for an established connection, not just a listening port.

### Direct Tailscale

Treat direct Tailscale as an authenticated reverse-proxy design, not a token shortcut:

- Keep the Dashboard bound to loopback.
- Allow only explicit Tailscale IPs or MagicDNS names in the active version's Host-validation policy.
- Keep protected HTTP token validation enabled.
- Validate the independent WebSocket upgrade path; HTTP middleware may not cover it.
- Supervise the forwarder and verify it recovers after a Dashboard restart.
- Reject arbitrary hosts and confirm the rejection remains `400`.

Do not bind the Dashboard to `0.0.0.0`, set a browser-facing `public_url` merely to silence Host validation, or bypass `_require_token`/middleware with a trusted-host sentinel unless a separately reviewed security design explicitly requires it. Environment variable names and helper functions changed across versions; inspect the running source before patching.

## Service and restart ownership

Map every relevant PID to its parent tree, command, working directory, start time, listening ports, and systemd unit. Distinguish the Electron renderer, shared Dashboard, independent TUI session, gateway worker, and relay. A Dashboard restart can terminate active sessions, MCP servers, LSPs, proxies, and user jobs; do not restart it from inside a session cgroup or use it as a generic UI refresh.

After changing source or service environment, verify the active manager owns the listener, the new process start time is later than the change, the restart counter is stable, and the intended port is served. A successful supervisor command is not proof that the new process won or that sibling LaunchAgents survived.

## Reversible client recovery

1. Back up `connection.json` and inspect it with secrets redacted.
2. Gracefully quit Hermes and launch the intended bundle by absolute path when duplicate registrations exist.
3. Re-run public status, protected REST, and WebSocket probes from the client.
4. Only after the network path passes, move renderer-state directories to timestamped backups if corruption is suspected: `Local Storage`, `Session Storage`, `Cache`, `GPUCache`, and `Code Cache`.
5. Preserve Cookies, session databases, connection files, and appearance records. If local storage must be reset, restore or merge the theme, mode, layout, pane, status-bar, backdrop, zoom, and translucency keys from the backup.
6. Relaunch normally and verify the live renderer, desktop log, and process path.

Do not use blanket `pkill`/`killall`, delete all user data, or claim recovery from a curl response without the desktop's authenticated WebSocket and live readiness window.

## Host and auth verification

For a direct path, test a known accepted Host and a deliberately arbitrary Host. Test `/api/status` and at least one protected route. For WebSocket, use the exact client URL and real token; a `403` after Host acceptance means missing or stale credentials unless the current implementation documents a separate reason. Never print the token in command output or reports.
