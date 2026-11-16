---
name: hermes-desktop-debug
description: Decision-tree for Hermes V2 Electron desktop failures (white screen, connectivity, auth). Load references/ for commands.
category: devops
tags: [hermes, electron, desktop, debugging]
---

# Hermes Desktop App Debugging

Decision tree for diagnosing Hermes V2 macOS Electron app failures. For specific commands, load `references/commands.md`.

## Architecture

Electron loads local bundled HTML, then connects to backend. Connection resolution order (see `main.cjs`):

1. **connection.json** — `~/Library/Application Support/Hermes/connection.json` (macOS). If `mode: "remote"`, app connects to `remote.url` with `remote.token.value` as `X-Hermes-Session-Token`.
2. **Environment variables** — `HERMES_DESKTOP_REMOTE_URL` + `HERMES_DESKTOP_REMOTE_TOKEN`.
3. **Local bootstrap** — If neither source provides a remote config, app spawns `hermes serve` locally.

The app never loads a remote URL as window content — only API calls go remote.

## White Screen Flow

Proceed in order. Stop at first failure.

1.  **Environment variables** — On the Mac, verify both required env vars are set. If the URL var is set but the token var is empty, the app will produce a white screen.
2.  **Bundled assets** — Verify the HTML entry point exists inside the app bundle. Missing → rebuild the desktop app.
3.  **Backend reachable** — From the server, verify the dashboard responds to authenticated requests.
4.  **Protocol compatibility** — If routing through an HTTPS proxy that uses self-signed or internal-PKI certificates, Electron will reject them because main.cjs does not enable certificate error bypass. Use a plain-HTTP path instead.

## Common Patterns

| Symptom | Likely Cause |
|---------|-------------|
| White screen on launch | Missing env vars, or TLS certificate rejection |
| Connection refused | Forwarding layer not running or wrong destination |
| Auth loop / boot failure | Token mismatch between Mac env and server config |
| 401 Unauthorized | `connection.json` token ≠ server `_SESSION_TOKEN` |
| Timeout / "did not become ready" | Host header rejected by loopback middleware |

## Server Configuration

The dashboard binds to loopback and should run as a supervised service, not a manual background process. Unsupervised processes die silently on parent exit, OOM, or unhandled exceptions, cascading into unreachable desktop. Two patterns for external access:

- **SSH tunnel** — no server patches needed, but dies on Mac sleep.
- **Local desktop proxy over Tailscale** — for the current Hermes v0.20.x deployment, keep the Dashboard on loopback and use the supervised Mac `127.0.0.1:9119` proxy through Tailscale to server port 8788. Do not rely on `HERMES_DASHBOARD_ACCEPTED_HOSTS` (this code path does not read it), and do not set `dashboard.public_url` to a Tailscale IP merely to fix Host validation: `public_url` declares a browser-facing public origin and can activate the auth gate.

### Restarting the dashboard kills your own session shell (cgroup trap)

Terminal-tool shells for TUI/Desktop sessions run INSIDE the `hermes-dashboard.service` cgroup. Running `systemctl restart hermes-dashboard.service` from within a session SIGTERMs that session's own commands (exit -15, turn interrupted) and can leave the service stuck in `deactivating` until the stop timeout force-kills it. To reload the dashboard after editing source (e.g. `hermes_cli/runtime_provider.py`, `agent/*.py`), use a detached helper that survives the cgroup teardown:

```bash
systemd-run --unit=dash-reload-helper --collect sh -c 'sleep 2; systemctl restart hermes-dashboard.service'
```

Then verify the new PID's start time is AFTER the mtime of the edited files (`ps -o lstart -p <pid>` vs `stat -c %y <file>`), plus the port listener (`ss -ltnp | grep :8787`).

### Port conflict

If the dashboard crashes in a restart loop, a zombie process holds its port. Identify and remove the blocker — the supervisor restarts automatically.

## Host Validation — Current Deployment

The current Dashboard code uses `dashboard.public_url` as a trusted browser-facing origin; it does not consume `HERMES_DASHBOARD_ACCEPTED_HOSTS`. Keep the server Dashboard bound to `127.0.0.1` and connect the macOS app through its supervised local proxy (`127.0.0.1:9119` → Tailscale server port `8788` → Dashboard `127.0.0.1:8787`). The proxy must rewrite the upstream Host to the loopback Dashboard authority.

Do **not** set `dashboard.public_url` to a Tailscale IP as a Host-header workaround. That setting is for a real browser-facing reverse-proxy origin and can activate the non-loopback authentication gate; with no registered auth provider, the Dashboard exits and systemd enters a restart loop.

Verify the split before changing anything:

- loopback Dashboard and local proxy return HTTP 200 on `/api/status`;
- the gateway user service is active with a stable PID and `NRestarts=0`;
- the Desktop log reports `Remote Hermes backend is ready`;
- a protected API route returns `401` without a token (never print the token), while the Desktop's authenticated path reaches readiness;
- an arbitrary Host remains rejected with `400` when tested directly against the loopback-bound Dashboard.

If a direct Tailscale endpoint is required instead, treat it as a separate authenticated reverse-proxy design and validate the current source's host/auth behavior first; do not assume an environment allowlist that the running version does not implement.

## Validated Failure Signature: REST Works, Desktop Cycles

Do not stop after `/api/status` returns `200`: the Desktop depends on the authenticated WebSocket and on long-lived relay sockets. When the Desktop alternates `ready → offline → connecting → checking` while short HTTP probes succeed, hold the authenticated WebSocket open past the relay's connect timeout. A close at a fixed interval strongly indicates that a forwarding layer retained its connect timeout for later `recv()` calls; in Python relays, call `upstream.settimeout(None)` (and use blocking full-duplex relay semantics) immediately after the bounded `create_connection()` succeeds. Verify the fix with an idle WebSocket soak, not only a handshake.

Keep the diagnosis layers separate: (1) the user gateway service, (2) the Dashboard/API service, (3) the macOS connection file and active bundle, and (4) each local/network relay. Inspect `connection.json` and `connections.json` with tokens redacted, compare the Desktop log against the exact configured endpoint, and check the running bundle path. After changing any LaunchAgent, re-check sibling listeners and the Desktop's liveness window; a successful `launchctl` command is not proof that every relay job remains loaded. The validated steps are documented in this section and in the two existing references below.

## References

- `references/commands.md` — Exact shell commands for each diagnostic step
- `references/server-config.md` — Service format and auth details
