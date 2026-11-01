# OpenAI Codex OAuth Device-Code Flow — Reproduction Notes

## Problem

The `hermes auth add openai-codex --type oauth` command initiates a device-code flow that polls `chatgpt.com/backend-api/codex/auth/device/code`. On some cloud VPS providers (Oracle Cloud, etc.), this endpoint returns **HTTP 403** at the network level — the request never reaches OpenAI's auth servers.

Symptom:
```
❌ Erreur 403: <html>... Cloudflare block page ...
```

## Workaround: Browser-Based Device-Code Flow

Since the VM cannot reach the auth endpoint, perform the flow from the **user's local browser** and inject the resulting tokens into the target profile.

### Minimal HTML page (self-contained)

Host this on any HTTP server reachable by the user (local `python3 -m http.server`, existing named tunnel, etc.):

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Codex OAuth</title></head>
<body>
  <button id="btn" onclick="start()">Start</button>
  <div id="step1" style="display:none">
    <p>URL: <a id="verifUrl" target="_blank"></a></p>
    <p>Code: <b id="userCode"></b></p>
    <button onclick="poll()">I authorized</button>
  </div>
  <pre id="out"></pre>
  <script>
    const CLIENT_ID = "epzv2CtY5jto6arw9O302XZbGAV2hWFk";
    let deviceCode = "";
    async function start() {
      const r = await fetch("https://chatgpt.com/backend-api/codex/auth/device/code", {
        method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({client_id: CLIENT_ID, scope: "codex model:read model:write offline"})
      });
      const d = await r.json();
      deviceCode = d.device_code;
      document.getElementById("verifUrl").href = d.verification_uri;
      document.getElementById("verifUrl").textContent = d.verification_uri;
      document.getElementById("userCode").textContent = d.user_code;
      document.getElementById("step1").style.display = "block";
      window.open(d.verification_uri, "_blank");
    }
    async function poll() {
      for (let i = 0; i < 120; i++) {
        await new Promise(r => setTimeout(r, 5000));
        const r = await fetch("https://chatgpt.com/backend-api/codex/auth/token", {
          method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({client_id: CLIENT_ID, device_code: deviceCode,
            grant_type: "urn:ietf:params:oauth:grant-type:device_code"})
        });
        if (r.status === 200) {
          const tokens = await r.json();
          document.getElementById("out").textContent = JSON.stringify(tokens, null, 2);
          return;
        }
      }
      document.getElementById("out").textContent = "Timeout";
    }
  </script>
</body>
</html>
```

### Injection into Hermes profile

Once the user copies the JSON output, write it into the target profile's auth pool:

```python
import json, time
from pathlib import Path

PROFILE = "openai2"  # or "default"
AUTH_PATH = Path.home() / ".hermes" / "profiles" / PROFILE / "auth.json"

# The JSON from the browser page:
tokens = {
    "access_token": "eyJhbG...",
    "refresh_token": "rt.1.AA...",
    "expires_in": 3600,
}

new_entry = {
    "id": "unique-id",
    "label": "browser-oauth",
    "auth_type": "oauth",
    "priority": 0,
    "source": "manual",
    "access_token": tokens["access_token"],
    "refresh_token": tokens.get("refresh_token", ""),
    "last_status": "ok",
    "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ", time.gmtime()),
    "request_count": 0,
    "base_url": "https://chatgpt.com/backend-api/codex",
}

auth_db = json.loads(AUTH_PATH.read_text()) if AUTH_PATH.exists() else \
    {"version": 1, "providers": {}, "credential_pool": {}, "active_provider": None}
auth_db.setdefault("credential_pool", {}).setdefault("openai-codex", [])
auth_db["credential_pool"]["openai-codex"].append(new_entry)
AUTH_PATH.write_text(json.dumps(auth_db, indent=2))
```

## Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /backend-api/codex/auth/device/code` | Request device code + user code |
| `POST /backend-api/codex/auth/token` | Poll for tokens (returns 400 `authorization_pending` while waiting) |

## Client ID

The public client ID for ChatGPT/Codex OAuth is `epzv2CtY5jto6arw9O302XZbGAV2hWFk`.

## Related

- `hermes-agent` skill — multi-account OAuth via profiles (`hermes profile create ...`)
- `cloudflare-tunnel-persistent` skill — serving the HTML page through a named tunnel when quick tunnels expire too fast
