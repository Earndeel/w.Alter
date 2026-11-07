# Host Header Validation Bypass for Tailscale

## Context

Backend frameworks increasingly add Host header validation as a DNS rebinding defence. When the backend is bound to `127.0.0.1`, it rejects any request whose `Host` header isn't a loopback address. This breaks Tailscale-based access because requests arrive with `Host: <tailscale-ip>` or `Host: <magicdns-hostname>`.

In Hermes Agent v0.18.2+, this validation was added via `host_header_middleware` (GHSA-ppp5-vxwm-4cf7) in `hermes_cli/web_server.py`.

## Symptom

```
400: {"detail":"Invalid Host header. Dashboard requests must use the hostname the server was bound to."}
```

The desktop app shows: `Error: Hermes backend did not become ready: 400: Invalid Host header`

This appears after a server update that added Host header checking, even though nothing changed on the client side. The server works fine from localhost (`curl http://127.0.0.1:8787/api/status` returns 200).

## Diagnosis

```bash
# Test from server with different Host headers
curl -s -w "\nHTTP %{http_code}" -H "Host: 127.0.0.1:9119" http://127.0.0.1:8787/api/status      # Should work
curl -s -w "\nHTTP %{http_code}" -H "Host: 100.91.35.121:8788" http://127.0.0.1:8787/api/status   # 400 if broken
```

If the second command returns 400 but the first returns 200, the Host header gate is rejecting the Tailscale IP.

## Fix (Hermes-specific)

In `hermes_cli/web_server.py`, two changes:

### 1. Add the constant (near `_LOOPBACK_HOST_VALUES`, ~line 383)

```python
_TAILSCALE_ACCEPTED_HOSTS: frozenset = frozenset({
    "100.91.35.121",  # server's Tailscale IP
})
```

### 2. Modify `_is_accepted_host()` (line ~446)

Change:
```python
if bound_lc in _LOOPBACK_HOST_VALUES:
    return host_only in _LOOPBACK_HOST_VALUES
```

To:
```python
if bound_lc in _LOOPBACK_HOST_VALUES:
    if host_only in _LOOPBACK_HOST_VALUES:
        return True
    return host_only in _TAILSCALE_ACCEPTED_HOSTS
```

### 3. Restart the dashboard

```bash
systemctl --user restart hermes-dashboard.service
```

## Alternative: SSH Tunnel (no server change)

If you can't modify the server, use an SSH tunnel on the client so the Host header is `127.0.0.1`:

```bash
ssh -L 9119:127.0.0.1:8787 walter-ts -N
```

Then point the desktop app at `http://127.0.0.1:9119`. This works without any server-side change because the Host header becomes `127.0.0.1:9119` which passes loopback validation.

## Connection.json Location (macOS)

The desktop app reads `connection.json` from Electron's `userData` path:

```
~/Library/Application Support/com.nousresearch.hermes/connection.json
```

If the file is missing, the app falls through to env vars (`HERMES_DESKTOP_REMOTE_URL`) or local bootstrap.
