# Cloudflare Tunnel for Voice-Call — Setup Reference

## Deployed configuration

### Tunnel config (`~/.cloudflared/config.yml`)
```yaml
- hostname: call.walter-ai.cloud
  service: https://localhost:8765
  originRequest:
    noTLSVerify: true
```

### DNS (Cloudflare API)
```
CNAME  call  →  8cd279c0-a805-4e06-91dd-edacd1eccb35.cfargotunnel.com  (proxied)
Zone: walter-ai.cloud (ba01ee08564dc4b2f66fa60b968a75f8)
```

### Process management
cloudflared runs directly (not systemd): `/usr/local/bin/cloudflared tunnel --config /root/.cloudflared/config.yml run`
Multiple cloudflared processes may be running — one per config file. Kill duplicates by matching config path.

## Pitfalls

1. **`noTLSVerify: true` is mandatory.** The voice-call server's TLS cert is for `w-alter.tail32cf1c.ts.net` (Tailscale/Let's Encrypt). Cloudflare tunnel connects to `localhost:8765` and the cert hostname doesn't match → TLS handshake fails silently → 502/523 errors. Without `noTLSVerify`, the tunnel appears to work but returns errors.

2. **`service` must be `https://` not `http://`.** The voice-call server only serves HTTPS. Using `http://localhost:8765` returns empty responses or connection refused.

3. **WebSocket works out of the box.** Cloudflare Tunnel supports WebSocket proxying. Gemini Live connects from the browser directly to Google's WebSocket endpoint (not through the tunnel), so the tunnel only needs to serve static files and the token API.

4. **Duplicate processes.** `ps aux | grep cloudflared` may show multiple instances with different configs. The main tunnel config is `config.yml`; others are `comfyui-config.yml` and token-based tunnels. Kill by PID matching the specific config file.

5. **DNS propagation.** After creating the CNAME record, wait 30-60s before testing. `curl -sk https://call.walter-ai.cloud/health` should return the health JSON.

## Verification
```bash
# Health check
curl -sk https://call.walter-ai.cloud/health | python3 -c "import json,sys; print(json.load(sys.stdin))"

# Token API (POST required)
curl -sk -X POST https://call.walter-ai.cloud/api/token | python3 -c "import json,sys; print(json.load(sys.stdin).get('token','?')[:20])"

# HTML page
curl -sk https://call.walter-ai.cloud/ | head -5
```
