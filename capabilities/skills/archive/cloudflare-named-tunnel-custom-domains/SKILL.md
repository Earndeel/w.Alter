---
name: cloudflare-named-tunnel-custom-domains
category: devops
description: Set up Cloudflare Named Tunnels with custom domains for multi-tenant SaaS dashboards
---

# Cloudflare Named Tunnel with Custom Domains

Use when exposing multiple services on different subdomains via a single Cloudflare tunnel.

## Prerequisites
- Cloudflare API Token with `Zone.DNS.Edit` + `Cloudflare Tunnel` permissions
- Zone ID and Account ID from Cloudflare dashboard
- `cloudflared` installed

## Steps

### 1. Create Named Tunnel via API
```python
import json, urllib.request
token = "cfut_..."
account_id = "..."

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

### 2. Save Credentials
The `credentials_file` field in the response contains `AccountTag`, `TunnelID`, `TunnelName`, `TunnelSecret`. Save to `~/.cloudflared/{tunnel_id}.json`.

### 3. Write Config
```yaml
tunnel: {tunnel_id}
credentials-file: /root/.cloudflared/{tunnel_id}.json

ingress:
  - hostname: admin.example.com
    service: http://localhost:5050
  - hostname: api.example.com
    service: http://localhost:5051
  - hostname: app-sc0001.example.com
    service: http://localhost:5100
  - service: http_status:404
```

### 4. Create DNS CNAMEs
Each subdomain needs a CNAME → `{tunnel_id}.cfargotunnel.com`

### 5. Switching an Existing Hostname to a New One
When replacing an old public hostname with a new one on an already-running tunnel, do it in this order to avoid downtime:

1. Edit `~/.cloudflared/config.yml` and add the new hostname first
2. Keep the old hostname as a temporary alias to the same local service
3. Create the new Cloudflare DNS CNAME pointing to `{tunnel_id}.cfargotunnel.com`
4. Validate ingress config before restart:
```bash
cloudflared tunnel ingress validate ~/.cloudflared/config.yml
```
5. Restart the systemd tunnel service:
```bash
systemctl restart cloudflared-tunnel.service
systemctl is-active cloudflared-tunnel.service
```
6. Verify both the new hostname and the old alias return HTTP 200, then remove the old alias later if desired

Example:
```yaml
ingress:
  - hostname: dashboard.example.com
    service: http://localhost:3002
  - hostname: old-dashboard.example.com
    service: http://localhost:3002
  - service: http_status:404
```

### 6. Start Tunnel
```bash
cloudflared tunnel --config /root/.cloudflared/config.yml run
```

### 7. Systemd Service
```ini
[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run
Restart=always
RestartSec=5
```

## Pitfalls
- Quick tunnels (`cloudflared tunnel --url`) are unstable — use named tunnels
- CNAME to `trycloudflare.com` does NOT work through Cloudflare proxy
- After changing config.yml, must restart the tunnel service
- DNS propagation can take 1-2 minutes after adding CNAME records
- HTTP 530 = tunnel connected but origin not running
- HTTP 000 = DNS not resolved yet (wait)
- `setMyCommands` Telegram API requires the full bot token (not truncated)
