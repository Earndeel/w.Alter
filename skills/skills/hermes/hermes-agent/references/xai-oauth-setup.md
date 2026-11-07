# xAI OAuth Setup (Remote VPS → Mac CDP)

## Problem
`hermes auth add xai-oauth --no-browser` starts a local HTTP callback server on a random port and prints an auth URL. But:
- It needs a PTY (fails with "open terminal failed: not a terminal" otherwise)
- The callback port is random (not always 56121)
- The callback server runs on the VPS, but the browser is on the Mac

## Solution: PTY + Reverse Tunnel + Mac CDP

### Step 1: Start auth with PTY and capture URL + port
```python
import subprocess, os, pty, time, select, re

master, slave = pty.openpty()
proc = subprocess.Popen(
    ["hermes", "auth", "add", "xai-oauth", "--no-browser"],
    stdin=slave, stdout=slave, stderr=slave, close_fds=True
)
os.close(slave)

# Read output for 10s
output = b""
start = time.time()
while time.time() - start < 12:
    r, _, _ = select.select([master], [], [], 1)
    if r:
        try: output += os.read(master, 4096)
        except: break

text = output.decode("utf-8", errors="replace")
url_match = re.search(r'https://auth\.x\.ai/[^\s\r\n]+', text)
port_match = re.search(r'127\.0\.0\.1:(\d+)/callback', text)
# auth_url and callback_port extracted
```

### Step 2: Reverse tunnel Mac → VPS for callback port
```bash
ssh -o ConnectTimeout=5 -i ~/.ssh/id_ed25519 -f -N -R {callback_port}:127.0.0.1:{callback_port} lucasjouvencon@100.127.150.1
```

### Step 3: Open auth URL in Mac Brave via CDP
```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9222")
context = browser.contexts[0]
page = context.new_page()
page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
# User sees consent page → authorize → callback fires
```

### Step 4: Verify
```bash
hermes auth list 2>&1 | grep "xai-oauth"
# Should show: xai-oauth (N credentials): oauth xai_pkce
```

## Pitfalls
- **Process exits with "open terminal failed"**: Must use PTY (`pty.openpty()`), not subprocess pipes
- **Callback port is random**: Always extract from output, don't hardcode 56121
- **X session required**: The OAuth flow redirects to X login. If X cookies were cleared, user must log in first
- **NEVER clear all cookies**: `context.clear_cookies()` wipes X session. Use domain-specific clearing.
- **Premium+ includes SuperGrok**: No API credits needed when using OAuth. API key approach requires paid credits.
- **Duplicate credentials**: Running auth multiple times creates duplicates. Clean up with `hermes auth remove xai-oauth <index>`
