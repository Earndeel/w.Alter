---
name: hermes-desktop-tunnel-recovery
description: Recover Hermes V2 Mac desktop app connectivity after Mac sleep — tunnel loss patterns, token auth alignment, and diagnostic approach.
category: devops
---

# Hermes Desktop Tunnel Recovery

What to do when the Hermes V2 Mac desktop app fails with ECONNREFUSED after the Mac was sleeping.

## Root cause

Mac sleep terminates port forwarding without killing the SSH connection. The SSH session survives, so it looks like connectivity is fine, but the tunnel is gone. The desktop app has nothing to connect to.

## Diagnostic sequence

Priority order — stop at first success:

1. **Verify Mac is online** — Check Tailscale status for the Mac hostname
2. **Verify server services** — Check gateway and dashboard are running
3. **Verify tunnel** — Check if the forwarded port has an ESTAB connection from the Mac IP, not just LISTEN
4. **Token check** — Only if user sees "token is not set" in desktop logs, align the env vars

## Token alignment (only if needed)

The desktop app requires both `HERMES_DESKTOP_REMOTE_URL` and `HERMES_DESKTOP_REMOTE_TOKEN`. Missing token causes a boot loop, not ECONNREFUSED.

When both are set, the app sends the token as an HTTP header. The server validates it against its own env var. These two values must match — one on the Mac, one in the server's dashboard service configuration.

## Tailscale diagnostic path

When the SSH tunnel cannot be re-established quickly, verify the server is reachable via its Tailscale address. This confirms the server is healthy without needing a tunnel, isolating the problem to the tunnel layer.

If `hermes-desktop-tailscale` patches are applied server-side, the desktop app can use Tailscale direct connectivity permanently — no tunnel needed at all. Otherwise, Tailscale access proves there is no server-side issue; the fix is to restart the SSH tunnel.
The desktop app still needs a tunnel to connect, but Tailscale access proves there is no server-side issue.

## Port architecture

The desktop app connects to a local port that is forwarded to the server dashboard. The gateway API is on a different port and handles LLM routing and tools.
