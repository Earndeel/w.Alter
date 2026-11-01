---
name: cloudflare-named-tunnel-setup
description: "Set up and manage Cloudflare Named Tunnels — create via API, custom domains, multi-host routing, systemd persistence, quick tunnel watchdogs, and troubleshooting."
version: 2.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [cloudflare, tunnel, cloudflared, custom-domains, systemd, networking]
---

# Cloudflare Named Tunnel Setup

## When to use
- Exposing local services (Flask, etc.) via custom domains
- Multi-hostname routing (one tunnel, many services)
- Production-grade tunnel with auto-restart

## Steps

### 1. Create tunnel via API
```python
import json, urllib.request

token = "cfut_..."  # API token with Zone.DNS.Edit + Cloudflare Tunnel
account_id = "..."
zone_id = "..."

# Create tunnel
payload = json.dumps({"name": "my-tunnel"}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    tunnel = json.loads(resp.read())["result"]

tunnel_id = tunnel["id"]
```

### 2. Save credentials
```python
cred_path = f"/root/.cloudflared/{tunnel_id}.json"
with open(cred_path, "w") as f:
    json.dump(tunnel["credentials_file"], f)
```

### 3. Write config with ingress rules
```yaml
# /root/.cloudflared/config.yml
tunnel: <tunnel_id>
credentials-file: /root/.cloudflared/<tunnel_id>.json

ingress:
  - hostname: app.example.com
    service: http://localhost:5000
  - hostname: api.example.com
    service: http://localhost:5001
  - service: http_status:404  # catch-all MUST be last
```

### 4. Create CNAME DNS records
```python
for sub in ["app", "api"]:
    payload = json.dumps({
        "type": "CNAME",
        "name": sub,
        "content": f"{tunnel_id}.cfargotunnel.com",
        "proxied": True
    }).encode()
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
        data=payload, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=10)
```

### 5. Create systemd service
```ini
# /etc/systemd/system/my-tunnel.service
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable my-tunnel
systemctl start my-tunnel
```

## Switching Hostnames (Zero-Downtime)

When replacing an old hostname with a new one on an already-running tunnel:

1. Edit config.yml — add new hostname first, keep old as temporary alias
2. Create new DNS CNAME pointing to `{tunnel_id}.cfargotunnel.com`
3. Validate: `cloudflared tunnel ingress validate ~/.cloudflared/config.yml`
4. Restart: `systemctl restart my-tunnel`
5. Verify both return HTTP 200, then remove old alias later

## Quick Tunnel (Temporary — No Domain Needed)

```bash
cloudflared tunnel --url http://localhost:5001
# Watch logs for: https://xxx-yyy-zzz.trycloudflare.com
```

**⚠️ trycloudflare.com URLs are RANDOM and change on every restart.** There is NO way to get a fixed free URL without owning a domain. CNAME to trycloudflare.com FAILS when proxied — must use named tunnels with `cfargotunnel.com`.

## Free Tier Reality

| Solution | URL Type | Permanent? | Cost |
|---|---|---|---|
| trycloudflare.com | Random | NO | Free |
| Named tunnel + domain | Fixed | YES | Need domain ($1-10/yr) |
| Workers.dev | Fixed | YES | Free (has account name in URL) |

## Wrangler Tunnel Commands (Limited)

- `wrangler tunnel create <name>` ✅
- `wrangler tunnel delete/info/list` ✅
- `wrangler tunnel route dns` ❌ **DOES NOT EXIST** — must use API or dashboard

## Adding a Service to an Existing Tunnel

When deploying a new webapp (e.g. ExcaliDash, MiroShark, etc.) behind an already-running tunnel:

1. **Add ingress rule** — insert BEFORE the catch-all (`- service: http_status:404`):
   ```bash
   sed -i '/^- service: http_status:404$/i - hostname: myapp.walter-ai.cloud\n  service: http://localhost:6767' /root/.cloudflared/config.yml
   ```

2. **Create DNS CNAME record** pointing subdomain to the tunnel:
   ```python
   import json, urllib.request
   token = "..."  # CF API token
   zone_id = "..."
   tunnel_id = "8cd279c0-..."  # from config.yml
   payload = json.dumps({
       "type": "CNAME",
       "name": "myapp",  # subdomain only
       "content": f"{tunnel_id}.cfargotunnel.com",
       "proxied": True
   }).encode()
   req = urllib.request.Request(
       f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
       data=payload, method="POST",
       headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
   )
   urllib.request.urlopen(req, timeout=10)
   ```

3. **Restart the tunnel service**:
   ```bash
   # Service name varies — check: systemctl list-units | grep cloud
   systemctl restart cloudflared-tunnel
   ```

4. **Verify** — wait 5-10s for DNS propagation, then:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" https://myapp.walter-ai.cloud
   ```

**Pitfall:** The systemd service may be named `cloudflared.service`, `cloudflared-tunnel.service`, or custom. Always check with `systemctl list-units --type=service | grep cloud` before restarting.

## Pitfalls
- **Scoped tokens can't use `/user` endpoint** — use `/user/tokens/verify` or just try listing zones to validate
- **Named tunnels need credentials** — quick tunnels (`cloudflared tunnel --url`) are unstable and can't use custom domains
- **credentials_file may be empty on first API creation** — delete tunnel and recreate to get credentials properly
- **Catch-all ingress rule MUST be last** — cloudflared will error if it's not
- **DNS propagation can take minutes** — don't panic if HTTP 000 at first, wait 10-15s
- **Service must listen on 0.0.0.0** — not just localhost, since cloudflared connects locally
- **HTTP 530 = tunnel connected but origin down** — check the local service is running
- **HTTP 522 = DNS not propagated yet** — wait or flush DNS cache
- **Restart tunnel after changing config.yml** — `systemctl restart my-tunnel`
- **CNAME to trycloudflare.com doesn't work** — must use named tunnel with cfargotunnel.com
- **Vite dev server blocks custom domains** — returns 403 "Blocked request. This host is not allowed." Fix: add `allowedHosts: ['your.domain.com']` in `vite.config.js` under `server:`. Same for Vite 6+ which restricts by default.
- **Tunnel secret can't be empty** — Cloudflare API requires a non-empty `tunnel_secret` when creating tunnels. Generate with `base64.b64encode(os.urandom(32)).decode()`.
- **Tunnel token vs API token** — `cloudflared tunnel run --token` expects the tunnel's JWT (from `/cfd_tunnel/{id}/token` API), NOT the Cloudflare API token. The JWT is ~180 chars.
- **Tunnel config via API** — when `remote_config: true` (default), ingress rules are set via `PUT /cfd_tunnel/{id}/configurations`, not via local config.yml.
