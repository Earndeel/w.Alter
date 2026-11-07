# Session Transcript: ComfyUI + Fal.ai + Cloudflare Tunnel Deployment

**Date:** 2026-05-01
**Server:** w-alter (Oracle Cloud ARM, 24 GB RAM, no GPU)
**Domain:** walter-ai.cloud
**Subdomain:** comfy.walter-ai.cloud

---

## 1. Environment Check

```bash
nvidia-smi                    # NO NVIDIA GPU
lspci | grep -i vga           # No discrete GPU
free -h                       # 23 GB RAM
nproc                         # 4 cores
cloudflared --version         # 2026.3.0 (pre-installed)
```

**Verdict:** CPU-only deployment required. Fal.ai handles GPU inference.

---

## 2. Credentials Retrieved from Vault

```bash
vault list cloudflare          # account_id, api_token
vault list fal                 # api_key
vault get cloudflare/api_token # 53 chars
vault get cloudflare/account_id # 32 chars
vault get fal/api_key          # 69 chars
```

**Zone found:** `walter-ai.cloud` (id=ba01ee08564dc4b2f66fa60b968a75f8)

---

## 3. ComfyUI Installation

```bash
# Install comfy-cli via uvx
uvx --from comfy-cli comfy --version    # 1.7.3

# Install ComfyUI in CPU mode
uvx --from comfy-cli comfy --skip-prompt install --cpu
# Result: installed at /root/comfy/ComfyUI
```

**Launch (initial test):**
```bash
uvx --from comfy-cli comfy launch --background -- --listen 0.0.0.0 --port 8188 --cpu
# Verdict: works, but creates a background process that conflicts with systemd later
```

---

## 4. Fal.ai Custom Nodes Installation

```bash
cd /root/comfy/ComfyUI/custom_nodes
git clone https://github.com/gokayfem/ComfyUI-fal-API.git
git clone https://github.com/badayvedat/ComfyUI-fal-Connector.git
```

**Python dependencies:**
```bash
cd /root/comfy/ComfyUI
source .venv/bin/activate
pip install fal-client fal httpx httpx-sse opencv-python
```

**Note:** `opencv-python` was NOT in the nodes' requirements but is required by `ComfyUI-fal-API/nodes/fal_utils.py` which imports `cv2`.

---

## 5. Credential Wiring

### Config file for ComfyUI-fal-API
```bash
cat > /root/comfy/ComfyUI/custom_nodes/ComfyUI-fal-API/config.ini << 'EOF'
[API]
FAL_KEY = <fal_key_from_vault>
EOF
```

### Config file for ComfyUI-fal-Connector
```bash
cat > /root/comfy/ComfyUI/custom_nodes/ComfyUI-fal-Connector/fal-config.ini << 'EOF'
[fal]
application_name = fal-ai/comfy-server/stream
api_key = <fal_key_from_vault>

[huggingface]
token =
EOF
```

---

## 6. Cloudflare Tunnel Creation (via API)

**API call to create tunnel:**
```python
import urllib.request, json

# POST /accounts/{account_id}/cfd_tunnel
payload = json.dumps({"name": "comfyui-tunnel"}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
# Response includes credentials_file (CRITICAL — only present in POST response!)
```

**Tunnel created:**
- ID: `af4720ac-5e22-402a-9df8-a6c52e913ed4`
- Name: `comfyui-tunnel`

**Credentials saved:**
```bash
/root/.cloudflared/af4720ac-5e22-402a-9df8-a6c52e913ed4.json
```

**Config written:**
```bash
/root/.cloudflared/comfyui-config.yml
```
Contents:
```yaml
tunnel: af4720ac-5e22-402a-9df8-a6c52e913ed4
credentials-file: /root/.cloudflared/af4720ac-5e22-402a-9df8-a6c52e913ed4.json

ingress:
  - hostname: comfy.walter-ai.cloud
    service: http://localhost:8188
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

**DNS record created:**
- Type: CNAME
- Name: `comfy`
- Content: `af4720ac-5e22-402a-9df8-a6c52e913ed4.cfargotunnel.com`
- Proxied: True

---

## 7. Systemd Services

### /etc/systemd/system/comfyui.service
```ini
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
Environment=FAL_KEY=<fal_key>

[Install]
WantedBy=multi-user.target
```

### /etc/systemd/system/cloudflared-comfy.service
```ini
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
```

**Activation:**
```bash
systemctl daemon-reload
systemctl enable comfyui.service cloudflared-comfy.service
systemctl start comfyui.service cloudflared-comfy.service
```

---

## 8. Conflict Resolution

**Problem:** The initial `comfy launch --background` created a persistent process bound to port 8188. When systemd tried to start the service, it failed with:
```
OSError: [Errno 98] error while attempting to bind on address ('0.0.0.0', 8188): address already in use
```

**Fix:**
```bash
ps aux | grep "python.*main.py"
# Found: PID 2444959 (uvx wrapper) and PID 2444970 (actual python)
kill 2444959 2444970
systemctl restart comfyui.service
```

**Lesson:** Always kill manual test launches before enabling systemd services.

---

## 9. Verification

```bash
# Local health
curl -s http://127.0.0.1:8188/system_stats | python3 -m json.tool
# → comfyui_version: 0.20.1, pytorch_version: 2.11.0+cpu

# Public URL health
curl -sI https://comfy.walter-ai.cloud/system_stats
# → HTTP/2 200

# Service status
systemctl is-active comfyui.service          # active
systemctl is-active cloudflared-comfy.service # active

# Fal nodes loaded
journalctl -u comfyui.service | grep "Import times for custom nodes"
# → ComfyUI-fal-API: 0.0 seconds
# → ComfyUI-fal-Connector: 0.0 seconds
```

---

## 10. Node Capabilities Summary

| Node Pack | Purpose | Key Nodes |
|-----------|---------|-----------|
| ComfyUI-fal-API | Direct Fal.ai model inference | Fal Flux, Fal SDXL, Fal Video, etc. |
| ComfyUI-fal-Connector | Execute ComfyUI workflows on Fal's Comfy Server | Save as fal format, remote execution |

**Endpoint for external calls:**
```
POST https://fal.run/fal-ai/comfy-server
```

---

## Files Created

| Path | Purpose |
|------|---------|
| `/root/comfy/ComfyUI` | ComfyUI installation |
| `/root/comfy/ComfyUI/custom_nodes/ComfyUI-fal-API` | Fal API nodes |
| `/root/comfy/ComfyUI/custom_nodes/ComfyUI-fal-Connector` | Fal connector nodes |
| `/root/comfy/ComfyUI/custom_nodes/ComfyUI-fal-API/config.ini` | Fal API key |
| `/root/comfy/ComfyUI/custom_nodes/ComfyUI-fal-Connector/fal-config.ini` | Fal connector config |
| `/root/.cloudflared/af4720ac-...json` | Tunnel credentials |
| `/root/.cloudflared/comfyui-config.yml` | Tunnel ingress config |
| `/etc/systemd/system/comfyui.service` | ComfyUI systemd unit |
| `/etc/systemd/system/cloudflared-comfy.service` | Tunnel systemd unit |
