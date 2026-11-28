---
name: comfyui-headless-deployment
description: Deploy ComfyUI on a headless GPU-less server with Fal.ai backend and expose it via Cloudflare Tunnel. Covers installation, custom node setup, credential wiring, systemd persistence, and conflict resolution.
version: 1.0.0
author: W.Alter
license: MIT
platforms: [linux]
compatibility: Requires ComfyUI (CPU mode), cloudflared, Fal.ai API key, Cloudflare API token with Zone.DNS.Edit + Account.Cloudflare Tunnel Edit.
prerequisites:
  commands: [python3, cloudflared, git]
setup:
  help: "Run the reference deployment guide at references/headless-fal-deployment.md"
metadata:
  hermes:
    tags: [comfyui, fal.ai, cloudflare-tunnel, headless, cpu-only, deployment, systemd]
    related_skills: [comfyui, cloudflare-tunnel-named, cloudflare-named-tunnel-setup]
    category: devops
---

# ComfyUI Headless Deployment with Fal.ai Backend

Deploy ComfyUI on a server without GPU, wire it to Fal.ai for actual generation, and expose the web UI securely via Cloudflare Tunnel.

## When to Use

- You have a CPU-only server (VPS, Oracle Cloud ARM, etc.) and want a persistent ComfyUI interface.
- You want to design workflows locally/visually but execute them on Fal.ai GPUs.
- You need ComfyUI accessible from anywhere via a custom domain.

## Architecture

```
[User] → https://comfy.example.com (Cloudflare Tunnel)
              ↓
        [ComfyUI :8188] (CPU-only, workflow editor)
              ↓
        [Fal.ai API] (GPU inference via custom nodes)
```

## Prerequisites

- Linux server with ≥4 GB RAM, ≥10 GB disk
- No GPU required (CPU mode)
- Cloudflare zone with API token (`Zone.DNS.Edit` + `Account.Cloudflare Tunnel Edit`)
- Fal.ai API key (from https://fal.ai/dashboard/keys)
- `cloudflared` installed
- `python3`, `git`, `curl`

## Quick Deploy

### 1. Install ComfyUI (CPU mode)

```bash
# Using comfy-cli via uvx (cleanest, no global pip pollution)
uvx --from comfy-cli comfy --skip-prompt install --cpu

# Or pip install if uvx unavailable
pip install --user comfy-cli
comfy --skip-prompt install --cpu
```

Default path: `~/comfy/ComfyUI`. The venv is at `~/comfy/ComfyUI/.venv`.

### 2. Launch and verify

```bash
uvx --from comfy-cli comfy launch --background -- --listen 0.0.0.0 --port 8188 --cpu
curl -s http://127.0.0.1:8188/system_stats | python3 -m json.tool
```

### 3. Install Fal.ai custom nodes

Two complementary node packs:

```bash
cd ~/comfy/ComfyUI/custom_nodes

# Pack 1: Direct Fal API nodes (image gen, video gen, etc.)
git clone https://github.com/gokayfem/ComfyUI-fal-API.git

# Pack 2: Workflow execution on Fal.ai Comfy Server
git clone https://github.com/badayvedat/ComfyUI-fal-Connector.git
```

Install Python deps:
```bash
cd ~/comfy/ComfyUI
source .venv/bin/activate
pip install fal-client fal httpx httpx-sse opencv-python
```

### 4. Wire Fal.ai credentials

**Option A: Config files (persistent, survives restarts)**

```bash
# For ComfyUI-fal-API
cat > ~/comfy/ComfyUI/custom_nodes/ComfyUI-fal-API/config.ini << 'EOF'
[API]
FAL_KEY = your_fal_key_here
EOF

# For ComfyUI-fal-Connector
cat > ~/comfy/ComfyUI/custom_nodes/ComfyUI-fal-Connector/fal-config.ini << 'EOF'
[fal]
application_name = fal-ai/comfy-server/stream
api_key = your_fal_key_here

[huggingface]
token = your_hf_token_here  # optional
EOF
```

**Option B: Environment variable (also set in systemd service)**

```bash
export FAL_KEY="your_fal_key_here"
```

The nodes check env var first, then fall back to config files.

### 5. Expose via Cloudflare Tunnel (Named)

Create tunnel via API (see `cloudflare-named-tunnel-setup` skill for full details):

```bash
# 1. Create tunnel → save credentials from POST response
# 2. Write config.yml with ingress rule pointing to localhost:8188
# 3. Create CNAME DNS record → <tunnel-id>.cfargotunnel.com
# 4. Run cloudflared
```

Minimal config:
```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: comfy.example.com
    service: http://localhost:8188
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

### 6. Systemd services (auto-start on boot)

**ComfyUI service** (`/etc/systemd/system/comfyui.service`):
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
Environment=FAL_KEY=your_fal_key_here

[Install]
WantedBy=multi-user.target
```

**Tunnel service** (`/etc/systemd/system/cloudflared-comfy.service`):
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

Enable and start:
```bash
systemctl daemon-reload
systemctl enable comfyui.service cloudflared-comfy.service
systemctl start comfyui.service cloudflared-comfy.service
```

## Pitfalls

1. **Port conflict from previous launch** — If you launched ComfyUI via `comfy launch --background` earlier, the port 8188 is already bound. The systemd service will fail with "Address already in use". Kill the old process before starting the systemd service:
   ```bash
   ps aux | grep "python.*main.py"
   kill <PID>
   ```

2. **Missing `opencv-python`** — The `ComfyUI-fal-API` node pack imports `cv2`. Install it in the venv:
   ```bash
   source ~/comfy/ComfyUI/.venv/bin/activate && pip install opencv-python
   ```

3. **FAL_KEY not in env var** — The systemd service must include `Environment=FAL_KEY=...` because the Fal nodes read env at import time. Config files are a fallback but env var is most reliable.

4. **Credentials only in POST response** — When creating a Cloudflare tunnel via API, the `credentials_file` field is ONLY present in the POST create response. If you miss it, delete and recreate the tunnel.

5. **Catch-all ingress rule MUST be last** — cloudflared errors if `service: http_status:404` is not the final rule.

6. **CPU mode is slow for local generation** — Expect 10-30 min per image. Always use Fal.ai nodes for actual generation; local ComfyUI is only for workflow design and queue management.

## Verification Checklist

- [ ] `curl http://127.0.0.1:8188/system_stats` returns JSON
- [ ] `systemctl is-active comfyui.service` = active
- [ ] `systemctl is-active cloudflared-comfy.service` = active
- [ ] `curl -sI https://comfy.example.com/system_stats` returns HTTP 200
- [ ] Fal nodes appear in ComfyUI node list (no import errors in logs)
- [ ] `journalctl -u comfyui.service | grep -i fal` shows key loaded

## References

- `references/headless-fal-deployment.md` — Full session transcript with exact commands, API calls, and error resolutions.
