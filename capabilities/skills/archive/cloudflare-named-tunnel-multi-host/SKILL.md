---
name: cloudflare-named-tunnel-multi-host
category: devops
description: Set up Cloudflare Named Tunnels with multiple hostnames routing to different local services.
---

# Cloudflare Named Tunnel — Multi-Host Setup

When exposing multiple local services via a single Cloudflare Named Tunnel with custom domains.

## Setup Steps

### 1. Create Tunnel via API
```python
# Requires: CLOUDFLARE_API_TOKEN (with Account > Cloudflare Tunnel > Edit)
# And: CLOUDFLARE_ACCOUNT_ID
POST /accounts/{account_id}/cfd_tunnel
{"name": "my-tunnel", "config_src": "cloudflare"}
```

### 2. Save Credentials
The API returns `credentials_file` with `AccountTag`, `TunnelID`, `TunnelName`, `TunnelSecret`.
Save to `/root/.cloudflared/{tunnel_id}.json`.

### 3. Create DNS CNAME Records
Each hostname needs a CNAME pointing to `{tunnel_id}.cfargotunnel.com`:
```python
POST /zones/{zone_id}/dns_records
{"type": "CNAME", "name": "subdomain", "content": "{tunnel_id}.cfargotunnel.com", "proxied": true}
```

### 4. Write Config YAML
```yaml
tunnel: <tunnel_id>
credentials-file: /root/.cloudflared/<tunnel_id>.json

ingress:
  - hostname: admin.example.com
    service: http://localhost:5050
  - hostname: api.example.com
    service: http://localhost:5051
  - hostname: dashboard-client1.example.com
    service: http://localhost:5100
  - service: http_status:404  # catch-all required
```

### 5. Run as Systemd Service
```ini
# /etc/systemd/system/scena-tunnel.service
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
systemctl enable scena-tunnel
systemctl restart scena-tunnel
```

## Key Learnings

### Don't use Quick Tunnels for production
`cloudflared tunnel --url http://localhost:PORT` generates random `trycloudflare.com` URLs that:
- Change on restart
- Can't be CNAME'd reliably
- Are unreliable for production

### Named Tunnels require credentials
- Quick tunnel = no credentials needed, random URL
- Named tunnel = credentials file from API, stable URL with your domain

### Token Permissions Required
The API token needs:
- `Account > Cloudflare Tunnel > Edit`
- `Zone > DNS > Edit` (for the specific zone)

### Error: "Failed to get tunnel"
Means the credentials file is empty or wrong. Re-create the tunnel via API and save the `credentials_file` from the response.

### Error: "control stream encountered a failure"
Usually means the tunnel can't connect to Cloudflare edge. Check:
- Firewall blocking QUIC (UDP 7844)
- Try `--protocol http2` fallback
- Verify credentials are correct

### Adding new client routes dynamically
1. Add ingress rule to config.yml (BEFORE the catch-all)
2. Create CNAME DNS record
3. Restart tunnel: `systemctl restart scena-tunnel`
4. Wait 10-15 seconds for connections to register

### HTTP 000 / 530 after config change
After editing config.yml and restarting, wait 10-15s. If still failing:
```bash
systemctl stop scena-tunnel
sleep 3
systemctl start scena-tunnel
sleep 12
curl -sL https://your-host.example.com
```
Sometimes `restart` doesn't fully reconnect. `stop` + `start` works better.

### Origin services must listen on 0.0.0.0
Flask apps must use `app.run(host='0.0.0.0', port=5000)` not `host='localhost'`. The tunnel connects from outside.

### Catch-all rule position
The `service: http_status:404` catch-all MUST be the LAST rule in ingress. Any rules after it are ignored.

### Scoped token can't list zones
A token scoped to a specific zone can't call `GET /zones` (returns empty). Use `GET /zones/{zone_id}/dns_records` directly if you know the zone_id.
