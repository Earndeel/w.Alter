---
name: desktop-app-tailscale
description: Patterns for connecting Electron desktop apps to backend APIs through Tailscale serve — host header gates, auth token alignment, env var persistence, and sleep-resilient connectivity.
version: 1.0.0
author: W.Alter
license: MIT
---

# Desktop App to Backend via Tailscale

General pattern for connecting an Electron desktop app to a backend API through Tailscale serve, avoiding fragile SSH tunnels.

## Pattern

```
Desktop App ──Tailscale MagicDNS──▶ server.tailnet.ts.net ──▶ tailscale serve ──▶ localhost:port (backend)
```

The app reads two env vars: a remote URL and an auth token. It sends the token as a header on every request. The backend validates it.

## Why Tailscale over SSH Tunnels

SSH port forwards die on laptop sleep. The app then falls back to local process spawning, which fails. Tailscale serve is connectionless — the endpoint resolves as long as both machines are on the tailnet.

## Server-Side Steps

**1. Expose the backend port via Tailscale serve:**
```bash
tailscale serve --bg <port>
```

This persists in the tailscaled daemon across reboots.

**2. Inject the auth token into the backend's systemd unit:**
```
[Service]
Environment=<TOKEN_ENV_VAR>=<value>
```

Reload and restart the unit.

**3. Patch the host header validation.**
Backends often reject non-localhost Host headers as a security measure against DNS rebinding. When remote access is intentional (token is configured), accept the Tailscale MagicDNS hostname in the host check function. Add a conditional block after the loopback check.

## Client-Side Steps

Set env vars and relaunch:
```
launchctl setenv <REMOTE_URL_VAR> https://<tailscale-hostname>
launchctl setenv <REMOTE_TOKEN_VAR> <token>
```

For persistence across reboots, also write to the shell profile (`.zshenv` or `.bash_profile`).

## Validation

- Public status endpoint: should answer without auth
- Protected endpoint: should reject without token, accept with correct token header
- Both cases must work through the Tailscale hostname, not just localhost

## Common Failures

- Token env var missing on client → set it and relaunch
- SSH tunnel died, app fell back to local spawn → switch to Tailscale serve
- Backend rejects MagicDNS hostname → patch host header gate
- Token mismatch → align both sides
- Tailscale serve not running → check status and port
