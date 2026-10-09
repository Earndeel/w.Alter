# Cloudflare Tunnel + Hermes Dashboard loopback pattern

## Symptom

- `cloudflared-tunnel.service` is active and registers QUIC connections, but `https://dashboard.<domain>/` returns `400` with:
  - `Invalid Host header. Dashboard requests must use the hostname the server was bound to.`
- Or `hermes-dashboard.service` restarts in a loop with logs like:
  - `Refusing to bind dashboard to 0.0.0.0 — the auth gate engages on non-loopback binds, but no auth providers are registered.`

## Root cause

Hermes dashboard validates the HTTP `Host` header to defend against DNS rebinding. When the dashboard is bound to `127.0.0.1`, requests arriving through Cloudflare still carry the public hostname unless cloudflared rewrites it. Binding the dashboard to `0.0.0.0 --insecure` is no longer a safe/general workaround; Hermes may refuse it when no dashboard auth provider is configured.

## Durable fix

Run dashboard on loopback and make Cloudflare tunnel rewrite the origin Host header to the loopback host/port.

Systemd user service example:

```ini
[Service]
ExecStart=/root/.hermes/hermes-agent/venv/bin/python -m hermes_cli.main dashboard --host 127.0.0.1 --insecure --no-open --port 8787
Restart=on-failure
RestartSec=30
```

Cloudflared ingress example:

```yaml
- hostname: dashboard.example.com
  service: http://localhost:8787
  originRequest:
    httpHostHeader: localhost:8787
```

Then restart both services and verify:

```bash
systemctl --user daemon-reload
systemctl --user restart hermes-dashboard.service
systemctl restart cloudflared-tunnel.service
curl -sS -m 10 -o /dev/null -w 'local=%{http_code}\n' http://127.0.0.1:8787/
curl -sS -m 20 -o /dev/null -w 'external=%{http_code}\n' https://dashboard.example.com/
```

Expected result: both local and external checks return `200`.

## Related pitfall

If `rc-local.service` fails with `Exec format error`, `/etc/rc.local` likely lacks a shebang. Add `#!/bin/sh` and `exit 0` if that file is meant to run at boot. This is not specific to the dashboard, but it pollutes boot health checks during tunnel/dashboard incidents.
