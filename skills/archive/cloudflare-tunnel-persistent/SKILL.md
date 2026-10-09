---
name: cloudflare-tunnel-persistent
category: devops
description: Set up persistent Cloudflare Tunnels for local services (Flask, etc.). Covers credential discovery, tunnel creation, DNS routing, watchdog patterns, and free-tier limitations.
---

# Cloudflare Tunnel Persistent Setup

## Credential Discovery

Cloudflare API tokens are often stored in MCP config files, not in .env or shell profiles:

```bash
# Most common location
cat /root/.hermes/mcp/mcporter.json
# Look for CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID
```

Also check:
- `~/.cloudflared/credentials.json` (tunnel-specific, has TunnelID + TunnelSecret)
- `~/.wrangler/cache/wrangler-account.json` (account ID only)
- `~/.hermes/.env` (sometimes present but often commented out)

## API Token Scope Check

Before proceeding, verify what the token can do:

```bash
# Verify token is active
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer <TOKEN>"

# Check zones (requires Zone scope)
curl -s "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer <TOKEN>"

# Tunnels (requires Account/Tunnel scope)
curl -s "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/cfd_tunnel" \
  -H "Authorization: Bearer <TOKEN>"

# Workers subdomain (always works with any active token)
curl -s "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/workers/subdomain" \
  -H "Authorization: Bearer <TOKEN>"
```

**Scope limitations**: MCP tokens usually have Tunnel + Account scope only. They can create/manage tunnels but NOT manage DNS zones. For DNS, you need `Zone.Zone.Read` + `Zone.DNS.Edit`.

## Free Tier Reality Check

| Solution | URL Type | Permanent? | Cost |
|---|---|---|---|
| `trycloudflare.com` | Random (`abc123-trycloudflare.com`) | NO | Free |
| Named tunnel + domain | Fixed (`dashboard.yourdomain.com`) | YES | Need domain ($1-10/yr) |
| Workers.dev | Fixed (`name.account.workers.dev`) | YES | Free (but has account name in URL) |

**Key limitation**: trycloudflare.com URLs are RANDOM and change on every restart. There is NO way to get a fixed free URL without owning a domain in the Cloudflare account.

## Workflow A: Quick Tunnel (trycloudflare.com) — Temporary

```bash
# Quick launch (no account needed)
cloudflared tunnel --url http://localhost:5001
# Watch logs for: https://xxx-yyy-zzz.trycloudflare.com
```

### Watchdog Script for Persistence

Create `/root/projects/ad-video-pipeline/watch_cloudflared.py`:

```python
#!/usr/bin/env python3
"""Maintains a trycloudflare.com tunnel permanently with auto-reconnect."""
import subprocess, time, re, signal, sys

FLASK_PORT = 5001
LOG_FILE = "/tmp/cloudflared_permanent.log"
STATE_FILE = "/tmp/cloudflared_url.txt"
running = True

def signal_handler(sig, frame):
    global running
    running = False
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line, end="")
    with open(LOG_FILE, "a") as f:
        f.write(line)

def main():
    log("=== Tunnel watchdog started ===")
    attempt = 0
    while running:
        attempt += 1
        backoff = min(2 ** min(attempt, 6) * 2, 120)
        log(f"Starting cloudflared (attempt #{attempt})")
        
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{FLASK_PORT}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        
        # Wait for URL
        deadline = time.time() + 15
        url = None
        while time.time() < deadline:
            for line in iter(proc.stdout.readline, ""):
                m = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
                if m:
                    url = m.group(0)
                    with open(STATE_FILE, "w") as f:
                        f.write(url)
                    log(f"Tunnel URL: {url}")
                    break
            if url:
                break
            time.sleep(0.5)
        
        if url is None:
            proc.kill()
            log(f"Failed, retrying in {backoff}s...")
            time.sleep(backoff)
            continue
        
        # Monitor until crash
        while running:
            ret = proc.poll()
            if ret is not None:
                log(f"cloudflared exited with code {ret}")
                break
            time.sleep(5)
        
        try:
            proc.kill()
        except:
            pass
        time.sleep(backoff)

if __name__ == "__main__":
    main()
```

Launch: `nohup python3 watch_cloudflared.py >> /tmp/cloudflared_watchdog.log 2>&1 &`

## Workflow B: Named Tunnel (Fixed URL) — Requires Domain

### Step 1: Create Tunnel
```bash
export CLOUDFLARE_API_TOKEN="<TOKEN>"
export CLOUDFLARE_ACCOUNT_ID="<ACCOUNT_ID>"

wrangler tunnel create ad-video-dashboard
# Returns: ID like a984dc7a-28b9-4499-a5d7-d0f42f9806bb
```

### Step 2: Get Tunnel Token
```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/cfd_tunnel/<TUNNEL_ID>/token" \
  -H "Authorization: Bearer <TOKEN>" | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])"
```

### Step 3: Decode JWT Token (contains TunnelSecret)
```python
import base64, json

jwt_token = "<TOKEN_FROM_STEP2>"
parts = jwt_token.split('.')
for i, part in enumerate(parts):
    padding = 4 - len(part) % 4
    if padding != 4:
        parts[i] = part + '=' * padding

decoded = json.loads(base64.urlsafe_b64decode(parts[0]))
# decoded = {"a": "<account_id>", "t": "<tunnel_id>", "s": "<tunnel_secret>"}
```

### Step 4: Update Credentials
```python
import json
creds = {
    "AccountTag": decoded["a"],
    "TunnelSecret": decoded["s"],
    "TunnelID": decoded["t"],
    "Type": "tunnel"
}
with open('/root/.cloudflared/credentials.json', 'w') as f:
    json.dump(creds, f, indent=2)
```

### Step 5: Create config.yml
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/credentials.json

ingress:
  - hostname: dashboard.yourdomain.com
    service: http://localhost:5001
  - service: http_status:404
```

### Step 6: Add DNS Record via API (requires Zone scope!)
```bash
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/<ZONE_ID>/dns_records" \
  -H "Authorization: Bearer <DNS_TOKEN>" \
  -H "Content-Type: application/json" \
  --data '{
    "type": "CNAME",
    "name": "dashboard",
    "content": "<TUNNEL_ID>.cfargotunnel.com",
    "ttl": 1,
    "proxied": true
  }'
```

### Step 7: Run Tunnel
```bash
cloudflared tunnel --config /root/.cloudflared/config.yml run
# Or in background:
nohup cloudflared tunnel --config /root/.cloudflared/config.yml run >> /tmp/tunnel.log 2>&1 &
```

## Wrangler v4 Tunnel Commands (Limited)

Wrangler v4's tunnel subcommands are LIMITED:
- `wrangler tunnel create <name>` ✅
- `wrangler tunnel delete <tunnel>` ✅
- `wrangler tunnel info <tunnel>` ✅
- `wrangler tunnel list` ✅
- `wrangler tunnel run [tunnel]` ✅
- `wrangler tunnel quick-start <url>` ✅
- `wrangler tunnel route dns` ❌ **DOES NOT EXIST**

Must use Cloudflare API or Dashboard for DNS configuration.

## Webtop Chromium CDP for Browser Automation

When API tokens lack Zone/DNS scope, use the webtop container's Chromium via CDP:

```bash
# 1. Start Chromium in webtop with CDP (preserves Google login)
docker exec webtop bash /config/custom/restart-with-cdp.sh

# 2. Connect Playwright from host
pip3 install playwright --break-system-packages  # Ubuntu 24.04 needs --break-system-packages

python3 -c "
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp('http://172.17.0.2:9223')
context = browser.contexts[0]  # Has all cookies/sessions
page = context.new_page()
page.goto('https://dash.cloudflare.com', wait_until='domcontentloaded')
"
```

**Key finding**: The existing webtop has a Google login session stored in `/config/.config/chromium/`. Using `--user-data-dir=/tmp/*` creates a blank profile. Start without that flag to preserve sessions.

## Workflow C: Named Tunnel via API (Full Automation)

When you need to create tunnels programmatically without wrangler:

### Step 1: Create Tunnel via API

```python
import json, urllib.request

token = "cfut_..."
account_id = "12ee..."

payload = json.dumps({"name": "my-tunnel"}).encode()
req = urllib.request.Request(
    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel",
    data=payload, method="POST",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read())["result"]

tunnel_id = result["id"]
# IMPORTANT: credentials_file may be EMPTY on first creation
# If empty, DELETE and RECREATE — second time it works
creds = result.get("credentials_file", {})
```

**Pitfall**: The `credentials_file` field is sometimes empty on the first API call. If empty, delete the tunnel and recreate it — the second call returns the credentials.

### Step 2: Save Credentials

```python
cred_path = f"/root/.cloudflared/{tunnel_id}.json"
with open(cred_path, "w") as f:
    json.dump(creds, f, indent=2)
# creds = {"AccountTag": "...", "TunnelID": "...", "TunnelSecret": "...", "TunnelName": "..."}
```

### Step 3: Write config.yml

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: admin.example.com
    service: http://localhost:5050
  - hostname: api.example.com
    service: http://localhost:5051
  - service: http_status:404
```

### Step 4: Route DNS to Tunnel

```python
# Delete existing CNAME first (API returns 400 if name already exists)
records = get_dns_records(zone_id)
for r in records:
    if r["name"] == "admin.example.com":
        delete_dns_record(zone_id, r["id"])

# Create CNAME pointing to tunnel
create_dns_record(zone_id, "CNAME", "admin", f"{tunnel_id}.cfargotunnel.com", proxied=True)
```

### Step 5: Start Tunnel

```bash
cloudflared tunnel --config /root/.cloudflared/config.yml run
```

## Multi-Tenant Tunnel Setup

For SaaS with per-client dashboards:

```python
def setup_client_tunnel(client_id, port, domain="example.com", zone_id="...", token="..."):
    """Create tunnel + DNS for a client dashboard."""
    # Create tunnel
    tunnel = create_tunnel(f"client-{client_id}")
    tunnel_id = tunnel["id"]
    
    # Save creds
    save_credentials(tunnel_id, tunnel["credentials_file"])
    
    # DNS
    subdomain = f"dashboard-{client_id}"
    create_dns_record(zone_id, "CNAME", subdomain, f"{tunnel_id}.cfargotunnel.com")
    
    # Config
    add_ingress_rule(tunnel_id, f"{subdomain}.{domain}", f"http://localhost:{port}")
    
    return f"https://{subdomain}.{domain}"
```

## .env Path Resolution in Nested Modules

When integration modules are nested (e.g., `admin/integrations/cloudflare.py`), .env path resolution differs:

```python
# For files in admin/integrations/ (3 levels up to project root):
os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

# For files in admin/ (2 levels up):
os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
```

Always check multiple .env paths in order:
```python
def _get_env(key):
    paths = [
        os.path.expanduser("~/.hermes/.env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
    ]
    for p in paths:
        if os.path.isfile(p):
            with open(p) as f:
                for line in f:
                    if key in line and "=" in line:
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val and val != "***":
                            return val
    return ""
```

## Systemd Service for Tunnel Persistence

Instead of nohup/background processes, use systemd for auto-restart:

```bash
cat > /etc/systemd/system/scena-tunnel.service << 'EOF'
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
systemctl enable scena-tunnel
systemctl restart scena-tunnel
systemctl status scena-tunnel
journalctl -u scena-tunnel -f  # watch logs
```

## Common Pitfalls

1. **trycloudflare.com URL changes on restart** — This is by design. Only named tunnels + owned domains give fixed URLs.

2. **Quick tunnels expire within minutes** — `cloudflared tunnel --url http://localhost:PORT` generates a random `trycloudflare.com` URL that becomes unreachable (Error 1033) after the process exits or after a short TTL. Do NOT use quick tunnels for anything the user needs to open in a browser later.

3. **Use an existing named tunnel instead of quick tunnels for browser flows** — If you already have a named tunnel running (e.g., `temp-scena.walter-ai.cloud` on `:8799`), copy the HTML file into its served directory rather than spawning a quick tunnel. Example:
   ```bash
   # The named tunnel already routes temp-scena.walter-ai.cloud → localhost:8799
   mkdir -p /var/lib/scena-temp-storage/oauth_tmp
   cp my-page.html /var/lib/scena-temp-storage/oauth_tmp/index.html
   # Accessible at: https://temp-scena.walter-ai.cloud/f/oauth_tmp/index.html
   ```

4. **API Token scope errors** — `Zone.Zone.Read` and `Zone.DNS.Edit` are separate from `Account.Tunnel` permissions. MCP tokens typically only have the latter. Solution: create a new token via dashboard, or use webtop CDP.

3. **cloudflared tunnel list fails** — Needs origin certificate. Named tunnels use credentials.json instead; trycloudflare tunnels don't need it.

4. **wrangler tunnel route dns not available** — Not in wrangler v4. Must use API or dashboard.

5. **Workers.dev has account name in URL** — `name.accountname.workers.dev` — the account name is the user's real name, not suitable for client-facing URLs.

6. **Domain purchase** — `.cloud` domains ~$2-15/yr (hostinger: $2, Cloudflare Registrar: ~$8). Must add domain to Cloudflare account + change nameservers.

7. **`kill` command blocks in terminal** — Use `pgrep -f pattern | while read pid; do kill -9 $pid` instead of direct `kill` or `pkill`.

8. **`pip3 install --break-system-packages`** — Required on Ubuntu 24.04. Hermes agent needs this for Python packages.

9. **Creating API tokens via API requires higher privileges** — Even a valid token can't create other tokens (Unauthorized 9109). Must create tokens manually via dashboard.

10. **CNAME to trycloudflare.com FAILS when proxied** — Cloudflare rejects a proxied CNAME pointing to another CNAME (trycloudflare.com). You MUST use named tunnels with `{tunnel_id}.cfargotunnel.com` for custom domains. Quick tunnels are only useful for direct access (copy-paste the URL), not for DNS routing.
