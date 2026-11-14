---
name: cloudflare-tunnel-named
category: devops
description: Expose local services via custom domains using Cloudflare Named Tunnels
---

# Cloudflare Named Tunnels with Custom Domains

## When to use
Exposing local services (Flask, APIs, dashboards) via custom domains using Cloudflare Named Tunnels. NOT quick tunnels (those can't use custom domains).

## Prerequisites
- Cloudflare API Token with `Zone.DNS.Edit` + `Account.Cloudflare Tunnel Edit`
- `cloudflared` installed
- Domain added as a zone in Cloudflare

## Steps

### 1. Create tunnel via API
```python
payload = json.dumps({"name": "my-tunnel"}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/cfd_tunnel",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    tunnel = json.loads(resp.read())["result"]
tunnel_id = tunnel["id"]
```

### 2. Save credentials (from POST response)
```python
creds = tunnel.get("credentials_file", {})
with open(f"/root/.cloudflared/{tunnel_id}.json", "w") as f:
    json.dump(creds, f)
```

### 3. Write config.yml
```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: admin.example.com
    service: http://localhost:5050
  - hostname: api.example.com
    service: http://localhost:5051
  - service: http_status:404
```

### 4. Create DNS CNAMEs → `<tunnel-id>.cfargotunnel.com`
### 5. Run: `cloudflared tunnel --config config.yml run`
### 6. Persist with systemd service (Restart=always)

### 7. Systemd service for persistence
```bash
cat > /etc/systemd/system/my-tunnel.service << 'EOF'
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
EOF
systemctl daemon-reload
systemctl enable my-tunnel
systemctl start my-tunnel
```

### 8. Cloudflare Pages deployment
Requires API Token with `Account → Cloudflare Pages → Edit` permission.
```bash
# Create project first
# Via API: POST /accounts/{id}/pages/projects {"name": "my-site", "production_branch": "main"}
# Then deploy:
CLOUDFLARE_API_TOKEN=xxx npx wrangler pages deploy ./dist --project-name my-site

# Add custom domain to Pages:
# Via API: POST /accounts/{id}/pages/projects/{name}/domains {"name": "custom.example.com"}
# Also add CNAME: custom → {project}.pages.dev
```

## Pitfalls
- Quick tunnels + CNAME = 403/530. Must use named tunnels.
- **Credentials only in POST response**: The `credentials_file` field is only in the POST create response. If you miss it, delete and recreate the tunnel. GET `/cfd_tunnel/{id}` returns empty `credentials_file: {}`.
- `origincert` error? Use `credentials-file` path in config.yml, NOT `origincert`.
- 530 = origin not running. Check `curl localhost:PORT` first.
- 522 = tunnel disconnected. Check `systemctl status my-tunnel`.
- HTTP 000 = DNS not propagated yet. Wait 1-5 min.
- Scoped token can't access `/user` — use `/user/tokens/verify` or try `/zones` to validate.
- **Flask template path**: if `__file__` is in `admin/dashboard/run.py`, templates are at `os.path.join(ADMIN_DIR, "templates")` NOT `os.path.join(ADMIN_DIR, "dashboard", "templates")`.
- **Module .env path depth**: `admin/integrations/*.py` needs 3x `os.path.dirname()`, `admin/*.py` needs 2x.
- **Wrangler "Project not found"**: Create project via API first, then deploy.
- **Wrangler "Uploaded 0 files"**: `touch` the files to force re-upload.
- **Pages custom domain stuck on "pending"**: Add the CNAME record pointing to `{project}.pages.dev` (not the tunnel).
