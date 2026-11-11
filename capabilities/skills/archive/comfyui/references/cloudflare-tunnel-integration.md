# ComfyUI + Cloudflare Named Tunnel

Reference: expose a local ComfyUI instance (CPU or GPU) via a custom domain using Cloudflare Named Tunnels.

## Prerequisites
- Cloudflare API Token with `Zone.DNS.Edit` + `Account.Cloudflare Tunnel Edit`
- `cloudflared` installed (`/usr/local/bin/cloudflared`)
- Domain active as a Cloudflare zone

## One-Shot Setup Script

Replace `DOMAIN`, `SUBDOMAIN`, `CF_TOKEN`, `CF_ACCOUNT_ID`, `ZONE_ID` below.

```python
import urllib.request, json, os

DOMAIN = "walter-ai.cloud"
SUBDOMAIN = "comfy"
CF_TOKEN = "your-token"
CF_ACCOUNT_ID = "your-account-id"
ZONE_ID = "your-zone-id"

# 1. Create tunnel
payload = json.dumps({"name": f"{SUBDOMAIN}-tunnel"}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/cfd_tunnel",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    tunnel = json.loads(resp.read())["result"]

tunnel_id = tunnel["id"]
creds = tunnel["credentials_file"]

# 2. Save credentials
os.makedirs("/root/.cloudflared", exist_ok=True)
cred_path = f"/root/.cloudflared/{tunnel_id}.json"
with open(cred_path, "w") as f:
    json.dump(creds, f)

# 3. Write config.yml
config = f"""tunnel: {tunnel_id}
credentials-file: {cred_path}

ingress:
  - hostname: {SUBDOMAIN}.{DOMAIN}
    service: http://localhost:8188
    originRequest:
      noTLSVerify: true
  - service: http_status:404
"""
config_path = "/root/.cloudflared/comfyui-config.yml"
with open(config_path, "w") as f:
    f.write(config)

# 4. Create DNS CNAME
payload = json.dumps({
    "type": "CNAME",
    "name": SUBDOMAIN,
    "content": f"{tunnel_id}.cfargotunnel.com",
    "proxied": True,
    "ttl": 1
}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    dns = json.loads(resp.read())["result"]

print(f"Tunnel: {tunnel_id}")
print(f"URL: https://{SUBDOMAIN}.{DOMAIN}")
print(f"Config: {config_path}")
```

## Systemd Services

```bash
# ComfyUI
cat > /etc/systemd/system/comfyui.service << 'EOF'
[Unit]
Description=ComfyUI Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/comfy/ComfyUI
ExecStart=/root/comfy/ComfyUI/.venv/bin/python main.py --listen 0.0.0.0 --port 8188 --cpu
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Tunnel (depends on ComfyUI)
cat > /etc/systemd/system/cloudflared-comfy.service << 'EOF'
[Unit]
Description=Cloudflare Tunnel for ComfyUI
After=network.target comfyui.service
Requires=comfyui.service

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/comfyui-config.yml run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now comfyui.service cloudflared-comfy.service
```

## Verify
```bash
curl -sI https://comfy.walter-ai.cloud/system_stats | head -5
# Expect HTTP/2 200
```

## Pitfalls
- ComfyUI MUST listen on `0.0.0.0` (not `127.0.0.1`) for cloudflared to reach it
- `cloudflared` must be installed as a binary, not via snap (snap sandbox blocks tunnel sockets)
- Credentials are ONLY returned in the POST create response; GET never returns them
- DNS propagation: 1-5 min; HTTP 522 = wait longer or check `systemctl status`
