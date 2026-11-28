---
name: hermes-desktop-setup
description: Diagnose and fix Hermes V2 Mac desktop app connection failures to a remote server. Covers token mismatch, env var injection, and forwarding architecture.
---

# Hermes Desktop Setup

Diagnose and repair Hermes V2 Mac Electron app connection to remote server.

**All technical details, commands, and architecture diagrams in `references/connection-chain.md`.**

## Symptom → diagnosis

| Error | Root cause |
|-------|-----------|
| `HERMES_DESKTOP_REMOTE_URL is set but HERMES_DESKTOP_REMOTE_TOKEN is not` | Token env var missing on Mac |
| `connect ECONNREFUSED 127.0.0.1:9119` | Forward not running server-side, or SSH tunnel dead |
| Renderer killed (exitCode 15) after local bootstrap | Possibly macOS Gatekeeper — separate from connection issues |

## Rules

- Keep the Dashboard bound to loopback and use the supervised macOS `127.0.0.1:9119` relay to the Tailscale forwarder. The relay must clear the post-connect socket timeout (`settimeout(None)`) so idle WebSockets remain open. Do not use `dashboard.public_url` on a Tailscale IP as a Host-header workaround; it can activate the auth gate and crash a no-provider Dashboard.
- If `HERMES_DESKTOP_REMOTE_URL` is unset, the app auto-bootstraps a local gateway. This is the fallback path and conflicts with remote mode.
