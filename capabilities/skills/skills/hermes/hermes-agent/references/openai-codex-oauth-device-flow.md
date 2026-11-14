# OpenAI Codex OAuth — Device Code Workaround

## Problem

`hermes auth add openai-codex --type oauth` may hang or fail in restricted environments (CI, headless VMs, corporate networks) due to:

- Local HTTP callback port conflicts (port 8080/3000 already in use)
- Firewall blocking `localhost` callback endpoint
- No accessible browser / display (SSH only)
- Network egress restrictions to `chatgpt.com` endpoints (403 responses)

> **Note:** Hermes v0.13.0+ uses device code flow by default for `hermes auth add`, but older versions or certain environments still trigger the interactive browser-based OAuth.

## Solution: Manual Device Code Flow

Use a standalone Python script to perform the OAuth device code flow locally (on a machine with browser access), then copy the resulting JSON entry into the target profile's `auth.json`.

### Option A — Web UI via Cloudflare Tunnel (easiest for end users)

When the VM is headless or its IP is blocked by the OAuth provider, serve a minimal HTML page that handles the device code flow in the user's browser, exposed via a temporary Cloudflare tunnel.

**1. On the VM, create and serve the page:**

```html
<!-- oauth.html — place in /root/oauth.html -->
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>OAuth Device Code</title></head>
<body>
<button id="btn" onclick="start()">Start Auth</button>
<pre id="out"></pre>
<script>
const CID="epzv2CtY5jto6arw9O302XZbGAV2hWFk";
async function start(){
  const d=await (await fetch("https://chatgpt.com/backend-api/codex/auth/device/code",{
    method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({client_id:CID,scope:"codex model:read model:write offline"})})).json();
  document.getElementById("out").textContent="URL: "+d.verification_uri+"\nCode: "+d.user_code;
  window.open(d.verification_uri,"_blank");
  for(let i=0;i<120;i++){
    await new Promise(r=>setTimeout(r,5000));
    const t=await (await fetch("https://chatgpt.com/backend-api/codex/auth/token",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({client_id:CID,device_code:d.device_code,grant_type:"urn:ietf:params:oauth:grant-type:device_code"})})).json();
    if(t.access_token){document.getElementById("out").textContent=JSON.stringify(t,null,2);break;}
  }
}
</script></body></html>
```

**2. Serve the page and expose it:**

```bash
# Serve locally on an unused port
python3 -m http.server 8766 --directory /root

# In another terminal, create a temporary public tunnel
cloudflared tunnel --url http://localhost:8766
# → outputs: https://<random>.trycloudflare.com/oauth.html
```

**3. User opens the tunnel URL in their local browser**, clicks "Start Auth", signs in to their 2nd ChatGPT account, enters the code, and waits for the JSON tokens to appear.

**4. Copy the JSON** (containing `access_token` and `refresh_token`) and paste it into the chat. The agent injects it into the target profile's `auth.json`.

**Why this works:** the browser runs on the user's local machine (residential IP, not blocked), while the page itself is hosted from the VM via the tunnel. The OAuth calls originate from the user's browser, bypassing VM IP restrictions.

---

### Option B — Run the script locally (recommended)

Save this as `oauth_codex_device.py` on your local machine (not the VM):

```python
#!/usr/bin/env python3
import requests, json, time, webbrowser, sys

CLIENT_ID = "epzv2CtY5jto6arw9O302XZbGAV2hWFk"
DEVICE_URL = "https://chatgpt.com/backend-api/codex/auth/device/code"
TOKEN_URL = "https://chatgpt.com/backend-api/codex/auth/token"

# Step 1: Get device code
r = requests.post(DEVICE_URL, json={
    "client_id": CLIENT_ID,
    "scope": "codex model:read model:write offline"
})
dc = r.json()
print(f"URL: {dc['verification_uri']}")
print(f"Code: {dc['user_code']}")
webbrowser.open(dc['verification_uri'])

device_code = dc['device_code']
interval = dc.get('interval', 5)

# Step 2: Poll until user authorizes
for _ in range(120):
    time.sleep(interval)
    tr = requests.post(TOKEN_URL, json={
        "client_id": CLIENT_ID,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
    })
    if tr.status_code == 200:
        tokens = tr.json()
        print(json.dumps(tokens, indent=2))
        break
else:
    print("Timeout — user did not authorize in time")
    sys.exit(1)
```

Run it: `python3 oauth_codex_device.py`, authorize in the browser, and copy the printed JSON.

### Option C — Use the helper script shipped with Hermes

Hermes provides a convenience script at `~/.hermes/scripts/oauth_openai_codex_device.py`.

To use it directly on the target machine (if network allows):

```bash
python3 ~/.hermes/scripts/oauth_openai_codex_device.py
```

If the VM has no browser or blocked egress, copy the script to your local machine and run it there (modify `AUTH_PATH` to point to your local destination).

### Step 3 — Inject into profile auth.json

Take the output JSON (containing `access_token`, `refresh_token`, etc.) and create a credential pool entry.

On the Hermes machine, append to `~/.hermes/profiles/<profile-name>/auth.json`:

```json
{
  "id": "edcfce2",
  "label": "openai2-oauth",
  "auth_type": "oauth",
  "priority": 1,
  "source": "manual",
  "access_token": "<paste-access-token>",
  "refresh_token": "<paste-refresh-token>",
  "last_status": "ok",
  "last_refresh": "2026-05-14T00:00:00.000000Z",
  "request_count": 0,
  "base_url": "https://chatgpt.com/backend-api/codex"
}
```

Ensure the pool array exists:

```json
{
  "version": 1,
  "providers": {},
  "credential_pool": {
    "openai-codex": [ /* your entry here */ ]
  },
  "active_provider": null
}
```

### Step 4 — Configure provider & model

```bash
# Switch to the target profile
hermes profile use openai2

# Set provider to openai-codex (will use the OAuth pool)
hermes config set model.provider openai-codex

# Optional: set default model
hermes config set model.default o3
```

Verify:

```bash
hermes auth list openai-codex
openai2 chat -q "Hello from second account"
```

## Multiple Accounts — Pool Behavior

Hermes rotates through `credential_pool.openai-codex` based on `credential_pool_strategies.openai-codex` (default: `fill_first`):

| Strategy | Behavior |
|----------|----------|
| `fill_first` | Use index 0 until exhausted/explicit reset, then index 1, … |
| `round_robin` | Cycle through all healthy credentials |
| `weighted` | Weight by `priority` (lower = higher priority) |

Set in `config.yaml`:

```yaml
credential_pool_strategies:
  openai-codex: round_robin
```

Each credential has its own `request_count` and health tracking (`last_status`, `last_error_code`). If a credential fails repeatedly, Hermes marks it exhausted and moves to the next one automatically.

## Common Pitfalls

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| 403 on `chatgpt.com/backend-api/codex/auth/*` | IP restriction / Cloudflare block | Run device code flow from a local machine with normal residential IP |
| `hermes auth add` hangs forever | Local callback port busy; no browser | Use manual device code flow (this guide) |
| Token expires after 1 hour | Using `access_token` directly without refresh | Ensure `refresh_token` is present; Hermes auto-refreshes via `auth.json` pool entries |
| Profile doesn't see the new credential | Entry placed in `~/.hermes/auth.json` instead of profile's `auth.json` | Use profile-specific `auth.json` at `~/.hermes/profiles/<name>/auth.json` |
| `hermes auth list` shows no providers | `active_provider` not set; provider not in `credential_pool` key | Run `hermes config set model.provider openai-codex`; verify JSON structure |

## References

- Hermes OAuth docs: https://hermes-agent.nousresearch.com/docs/user-guide/configuration/#oauth-providers
- Provider pool config: https://hermes-agent.nousresearch.com/docs/user-guide/configuration/#credential-pools
- Device code RFC: https://datatracker.ietf.org/doc/html/rfc8628
