# AWS Console Automation via Camoufox

## Architecture

```
Mac Brave (cookies) → SSH + CDP → extract cookies → Camoufox-max → inject → navigate AWS Console
                              → Tailscale exit node (Mac IP)
```

## Full Workflow

### 1. Extract cookies from Mac Brave

```python
import subprocess, http.client, json, time, websockets, asyncio

# SSH tunnel to Mac Brave CDP
proc = subprocess.Popen(
    ["ssh", "-o", "StrictHostKeyChecking=no", "-L", "19222:localhost:9222",
     "-N", "lucasjouvencon@100.127.150.1"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(2)

# Get browser WS URL
conn = http.client.HTTPConnection("localhost", 19222)
conn.request("GET", "/json/version")
resp = json.loads(conn.getresponse().read())
ws_url = resp["webSocketDebuggerUrl"].replace("ws://localhost:9222", "ws://localhost:19222")

# Extract all cookies
async def get_cookies():
    async with websockets.connect(ws_url, max_size=50*1024*1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        resp = json.loads(await ws.recv())
        return resp.get("result", {}).get("cookies", [])

cookies = asyncio.run(get_cookies())
proc.terminate()
```

### 2. Inject cookies + navigate

```python
def cf(method, path, body=None):
    conn = http.client.HTTPConnection("localhost", 9377, timeout=60)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, json.dumps(body) if body else None, headers)
    return conn.getstatus(), json.loads(conn.getresponse().read())

# Inject AWS cookies
aws_cookies = [c for c in cookies if ".aws.amazon.com" in c.get("domain", "")]
cf("POST", "/session/cookies", {"cookies": aws_cookies})

# Navigate with Tailscale proxy
status, result = cf("POST", "/session", {
    "url": "https://us-east-1.console.aws.amazon.com/iamv2/home#/users",
    "proxy": {"server": "socks5://100.127.150.1:1080"}
})
```

### 3. Create IAM user via evaluate

```python
tab_id = result["tabId"]

# Click "Create user" button
cf("POST", "/tab/evaluate", {
    "tabId": tab_id,
    "expression": """
        document.querySelectorAll('button').forEach(b => {
            if (b.textContent.includes('Create user')) b.click();
        });
    """
})

# Set username (React input - needs native setter)
cf("POST", "/tab/evaluate", {
    "tabId": tab_id,
    "expression": """
        const input = document.querySelector('input[name="username"]') ||
                      document.querySelector('input[placeholder*="User name"]');
        if (input) {
            const setter = Object.getOwnPropertyDescriptor(
                HTMLInputElement.prototype, 'value'
            ).set;
            setter.call(input, 'walter-bedrock');
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    """
})
```

### 4. Extract access keys after creation

```python
# After "Create access key" dialog appears
status, result = cf("POST", "/tab/evaluate", {
    "tabId": tab_id,
    "expression": """
        Array.from(document.querySelectorAll('td, span')).map(e => e.textContent).join('|');
    """
})
# Parse: Access Key ID = first 20 chars starting with AKIA
# Secret Key = 40-char string after the key ID in TBODY concatenation
```

## Pitfalls

- **CORS blocks direct AWS API calls from browser** — Cannot call `iam.amazonaws.com` from the console page. Must use UI automation via `/evaluate`.
- **AWS Console URL hash encoding** — React router encodes `/` as `%2F` in hash. Direct navigation to `#/users/details/walter-bedrock/security-credentials` double-encodes. Use `/evaluate` to click through tabs instead.
- **Root user security credentials page ≠ IAM user page** — The hash `#/security_credentials` goes to root. IAM user credentials require navigating through the users list.
- **Tailscale SOCKS proxy required** — AWS Console sessions are IP-bound. Must proxy through Mac's Tailscale exit node to match the original session IP.
- **Cookie domain matching** — AWS uses multiple domains (`console.aws.amazon.com`, `signin.aws.amazon.com`, `us-east-1.console.aws.amazon.com`). Inject ALL `.aws.amazon.com` cookies.
