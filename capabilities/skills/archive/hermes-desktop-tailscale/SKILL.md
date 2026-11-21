---
name: hermes-desktop-tailscale
description: Connect Hermes V2 Mac desktop app directly via Tailscale interface — four web_server.py patches + supervised socat forwarder to eliminate SSH tunnel dependency and survive updates.
category: devops
tags: [hermes, desktop, tailscale, connectivity]
---

# Hermes Desktop — Tailscale Direct

Bypass the SSH tunnel. The desktop app connects to the dashboard through the server's Tailscale interface after three web_server.py patches.

## Why

SSH tunnels die on Mac sleep. Tailscale survives. The dashboard binds loopback-only for security — two targeted patches extend that trust to the server's own Tailscale address without opening the dashboard to the internet.

## Server patches (`web_server.py`)

**Four patches** are required. Three cover HTTP; the fourth covers WebSocket. Missing any one of them causes a different failure mode — see Diagnosis below.

### Patch 1: Host header acceptance

Register the server's Tailscale address so the anti-DNS-rebinding middleware accepts it:

- Define `_TAILSCALE_ACCEPTED_HOSTS` frozenset with the server's Tailscale IP(s).
- In `_is_accepted_host`, loopback branch: after checking `_LOOPBACK_HOST_VALUES`, also check `_TAILSCALE_ACCEPTED_HOSTS`.

### Patch 2: Token bypass in `_require_token`

`_require_token` compares the request token against a random `_SESSION_TOKEN`. Tailscale connections are network-trusted via Patch 1 — skip token validation:

- In `_require_token`, before the `auth_required` / `_has_valid_session_token` check: extract the Host header and bound host, call `_is_accepted_host(host_header, bound_host)`. If accepted, return immediately.

### Patch 3: Token bypass in `auth_middleware` (CRITICAL — easy to miss)

`auth_middleware` (registered after `_dashboard_auth_gate`) enforces the session token as a middleware layer, BEFORE any route handler runs. Patch 2 alone won't help — the middleware returns 401 before `_require_token` is ever called.

- In `auth_middleware`, after the `token_authenticated` and `auth_required` short-circuits, but before the `_has_valid_session_token` check: same bypass as Patch 2 — extract Host header, check `_is_accepted_host`, return `await call_next(request)` if accepted.

### Patch 4: WebSocket auth bypass in `_ws_auth_reason` (NEW — v0.18.2+)

The Chat tab and desktop app chat use `/api/ws` WebSocket. Its auth path (`_ws_auth_reason`) is completely separate from the HTTP middleware chain — Patches 2+3 don't cover it. Without this patch, HTTP returns 200 but the WebSocket upgrade returns 403, and the desktop app reports "Could not connect to Hermes gateway."

- In `_ws_auth_reason`, after the `auth_required` gate block and before the legacy `token = ws.query_params.get("token", "")` line: extract the Host header from `ws.headers.get("host", "")`, get `bound_host` from `app.state`, and call `_is_accepted_host(host_header, bound_host)`. If accepted, return `None, "trusted_host"`.

The exact insertion point is right before the `token = ws.query_params.get(...)` line — that's the fallback path for insecure/loopback mode. See `references/patch4-websocket-bypass.md` for the exact old→new code diff and verification test.

### Activation

All four patches require dashboard restart. **Verify the restart actually succeeded** — see "Stale process detection" in Pitfalls below.

## Forwarder Supervision (systemd — REQUIRED)

The socat forwarder that exposes the dashboard on the Tailscale interface MUST be supervised. Without supervision, every dashboard restart or update breaks the desktop app because the forwarder dies or desynchronizes. This is the #1 cause of "encore un problème de gateway après update."

**Create `/root/.config/systemd/user/hermes-forwarder-9119.service`:**

```ini
[Unit]
Description=Hermes Desktop Forwarder (9119 → dashboard)
BindsTo=hermes-dashboard.service
After=hermes-dashboard.service

[Service]
Type=simple
ExecStart=/usr/bin/socat TCP-LISTEN:9119,reuseaddr,fork,bind=0.0.0.0 TCP:127.0.0.1:8787
Restart=always
RestartSec=5

[Install]
WantedBy=hermes-dashboard.service
```

**Deploy:**

```bash
# 1. Kill any manual forwarder on port 9119
kill $(ss -tlnp | grep ':9119' | grep -oP 'pid=\K\d+') 2>/dev/null

# 2. Enable and start the supervised service
systemctl --user daemon-reload
systemctl --user enable --now hermes-forwarder-9119.service

# 3. Verify
systemctl --user status hermes-forwarder-9119.service
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Host: 100.91.35.121:9119" http://127.0.0.1:9119/api/status
# Must return: HTTP 200
```

**Robustness test — restart dashboard and confirm forwarder auto-recovers:**

```bash
systemctl --user restart hermes-dashboard.service
sleep 3
systemctl --user status hermes-forwarder-9119.service | grep "Active:"
# Must show: Active: active (running) — with a NEW PID (proves it restarted)
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Host: 100.91.35.121:9119" http://127.0.0.1:9119/api/status
# Must return: HTTP 200
```

`BindsTo=` ensures the forwarder stops/starts with the dashboard. `Restart=always` catches crashes. Result: zero-touch survival across updates.

## Mac launcher (`hermes-v2`)

1. Kill existing V2 instance.
2. Write `connection.json` to `~/Library/Application Support/Hermes/` with Tailscale URL and server token.
3. Launch via `open`.

Token: extract `HERMES_DASHBOARD_SESSION_TOKEN` from `/proc/PID/environ` on the server. Once Patches 2+3 are active, any string works.

## connection.json path

macOS: `~/Library/Application Support/Hermes/connection.json` (NOT `com.nousresearch.hermes/`).

## Diagnosis

- `HTTP 200` on `/api/status` → Host header accepted (Patch 1 OK).
- `HTTP 400` → Patch 1 not applied/active.
- `HTTP 200` on `/api/status` but `HTTP 401` on `/api/config` → Patch 2 or Patch 3 missing (or both). Test: `curl -H "Host: <tailscale-ip>:<port>"` against a protected endpoint. If `auth_middleware` wasn't patched (Patch 3), it returns 401 before `_require_token` even runs.
- **WebSocket `/api/ws` returns HTTP 403 but `/api/status` returns 200** → Patch 4 missing. The WebSocket auth path (`_ws_auth_reason`) is separate from HTTP middleware. Desktop app symptom: "Could not connect to Hermes gateway" after the initial `waitForHermes` succeeds. Test: Python websockets client connecting to `ws://127.0.0.1:<port>/api/ws` with Tailscale Host header.
- `/api/status` is public — `waitForHermes` succeeds if Host header passes. API call failures are the real error.

## Pitfalls

- **Patch 4 is the most commonly missed step.** `_ws_auth_reason` is completely separate from HTTP middleware — patching only `_require_token` and `auth_middleware` (Patches 2+3) leaves the WebSocket Chat tab returning 403. The desktop app reports "Could not connect to Hermes gateway." Always apply all four patches.
- **Stale process detection before restart** — the most insidious failure mode: you patch the code, restart the dashboard, tests pass… but the OLD process is still holding the port. The new process died silently (port in use) and you're testing against the old bytecode. Before restarting: `ss -tlnp | grep <port>` to identify the current owner. Kill it explicitly with its PID, verify the port is free, then restart. `pkill -f` only matches the current user's UID — a process running as a different user (e.g., `hermes` user via privilege drop) survives `pkill` and requires `kill -9 <PID>` as root.
- **Supervision required** — dashboard and port forwarder need supervision; manual processes die on parent exit.
- **Port conflict on restart** — if the supervisor restarts while a zombie process holds the port, identify the blocker and remove it.
- **Token ephemeral** — changes on restart; Patches 2+3+4 eliminate this dependency.
- **User data path** — `Hermes/` not `com.nousresearch.hermes/`.
- **systemd crash loop** — if a `hermes-dashboard.service` exists and the operator starts the dashboard manually, the systemd service will crash-loop trying to bind the same port. Stop it: `systemctl stop hermes-dashboard.service`. The service restart counter climbing past zero in journalctl is the tell.
- **Gateway port mismatch** — if the desktop connects but reports a gateway error, verify that the dashboard-reported `api_server` port matches the gateway's actual listening port. Mismatch means `host`/`port` are outside `extra:` in `config.yaml`. Load `hermes-config-extra-pitfall` for the full diagnosis.
