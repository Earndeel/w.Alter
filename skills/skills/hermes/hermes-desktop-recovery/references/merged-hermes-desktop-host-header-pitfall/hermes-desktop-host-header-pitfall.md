---
name: hermes-desktop-recovery
description: Diagnose and resolve the Host header validation 400 error that started appearing after Hermes v0.18.2 update on Mac desktop app connections.
category: devops
tags: [hermes, desktop, debugging, host-header]
---

# Host Header Validation Pitfall (v0.18.2+)

## Symptom

Desktop app shows `400: Invalid Host header. Dashboard requests must use the hostname the server was bound to.`

## Cause

v0.18.2 added Host header validation middleware. When the dashboard is bound to loopback, it rejects any Host header that is not a loopback address.

Before v0.18.2, the Mac could connect through Tailscale directly with a non-loopback Host header. This no longer works.

## Fix

**Option A — SSH tunnel (quick fix):** The Mac connects through an SSH tunnel
that terminates on loopback, so the Host header carries a loopback address.
This needs no dashboard source change and is the preferred fallback when direct
Tailscale access is not required.

**Option B — Tailscale direct (secure permanent fix):** Keep the dashboard bound
to loopback and add an explicit operator-controlled allowlist through the
supervised dashboard service, for example:

```ini
[Service]
Environment="HERMES_DASHBOARD_ACCEPTED_HOSTS=<tailscale-ip>,<magic-dns-name>"
```

Extend the loopback branch of `_is_accepted_host()` to accept only loopback
names or entries from that allowlist. The HTTP Host middleware and the
WebSocket `_ws_host_origin_reason()` path both reuse `_is_accepted_host()`, so
one policy change covers both transports. Reload the user systemd unit and
restart only the dashboard after changing the service environment.

**Do not bypass `_require_token`, replace the token with a sentinel, or bind
the dashboard to `0.0.0.0`.** The allowlist fixes Host validation only; the
normal dashboard session token remains required for protected HTTP routes and
WebSocket upgrades.

## Pitfall 1 — WebSocket 403 (chat tab fails)

A WebSocket can still return 403 after the Host allowlist is correct when the
client sends no token or a stale token. Test `/api/ws` with the real dashboard
session token. Do not add a trusted-host token bypass: that weakens the
security boundary and is not required when the forwarder terminates on the
server loopback.

## Pitfall 2 — Stale dashboard process

After changing the source or service environment, verify that the supervised
process actually restarted:

```bash
systemctl --user daemon-reload
systemctl --user restart hermes-dashboard.service
systemctl --user status hermes-dashboard.service --no-pager
journalctl --user -u hermes-dashboard.service -n 20 --no-pager
```

If the listener is still held by an unexpected process, stop and inspect the
owning service through systemd before taking any process-level action. Never
kill an arbitrary PID merely because it owns the dashboard port.

## Pitfall 3 — Stale Python code

A successful source edit is not proof that the running dashboard imported it.
Confirm the new process start time and the `HERMES_DASHBOARD_ACCEPTED_HOSTS`
environment in the service, then rerun the HTTP and WebSocket probes. A
supervised restart is the normal remedy; clearing every `__pycache__` directory
is not a routine step.

## Deployment ownership and authentication companion

Before applying the allowlist, inspect both service managers:

```bash
systemctl status hermes-dashboard.service --no-pager
systemctl --user status hermes-dashboard.service --no-pager
ss -ltnp | grep 8787
```

A drop-in under `~/.config/systemd/user/` has no effect when the active listener belongs to `/etc/systemd/system/`. Disable the duplicate unit and put the Host allowlist in the manager that owns the listener. Also verify the protected path: `/api/status` is public and may return 200 while `/api/config` returns 401. If the desktop connection persists a token, define the same `HERMES_DASHBOARD_SESSION_TOKEN` in the active service drop-in, keep the file mode restrictive, then run `systemctl daemon-reload` and restart the active dashboard.

## Verification

```bash
# HTTP — known Host must return 200
curl -s -o /dev/null -w "%{http_code}" \
  -H "Host: <tailscale_ip>:<tailscale_forward_port>" \
  http://127.0.0.1:8787/api/status

# Arbitrary Host — must return 400
curl -s -o /dev/null -w "%{http_code}" \
  -H "Host: evil.com" \
  http://127.0.0.1:8787/api/status
```

For WebSocket, connect to `ws://<tailscale_ip>:<tailscale_forward_port>/api/ws?token=<dashboard_token>` and assert the handshake succeeds. A 403 at this stage means the token is absent or mismatched; it is not a reason to bypass authentication. Never print the token in logs or reports.

## Related

Load `hermes-desktop-debug` for the full decision tree.
Load `hermes-desktop-tunnel-recovery` for tunnel-specific recovery.
