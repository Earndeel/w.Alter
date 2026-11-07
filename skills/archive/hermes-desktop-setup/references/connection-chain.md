# Connection Chain Architecture

The Electron app connects through an SSH forward to the dashboard behind a relay.

## Token flow

1. Server generates token → injected into systemd user units as `HERMES_DASHBOARD_SESSION_TOKEN`
2. Mac sets same token as `HERMES_DESKTOP_REMOTE_TOKEN` via `launchctl setenv`
3. Electron sends it as `X-Hermes-Session-Token` header (see `main.cjs` `fetchJson()`)
4. Dashboard validates via `_has_valid_session_token()` in `web_server.py`

## Systemd injection pattern

```ini
[Service]
Environment="HERMES_DASHBOARD_SESSION_TOKEN=<token>"
```

Both `hermes-gateway.service` and `hermes-dashboard.service` need it.

After editing: `daemon-reload` then `restart` both units.

## Boot sequence (from main.cjs)

1. `resolveRemoteBackend()` — checks both env vars exist
2. `waitForHermes()` — polls status endpoint with token
3. Falls through to local bootstrap if remote URL is unset
4. Renderer crash handler only handles `crashed`/`oom`, not `killed` (SIGTERM)

## Why not bypass auth

`_has_valid_session_token()` prevents DNS rebinding. `return True` bypass breaks 23 tests. Always sync the real token.
