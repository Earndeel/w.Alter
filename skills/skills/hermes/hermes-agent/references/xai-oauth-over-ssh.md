# xAI OAuth over SSH

## Problem
`hermes auth add xai-oauth --no-browser` starts a local HTTP callback server on a **random port** and waits for the OAuth redirect. It needs a real TTY.

## What doesn't work
- `terminal(background=true)` → "open terminal failed: not a terminal"
- `nohup hermes auth add xai-oauth --no-browser &` → blocked by Hermes foreground check
- `script -q -c "hermes auth ..."` in background → process dies immediately

## Working approach: Python PTY + reverse tunnel

### Step 1: Start auth with PTY, capture URL
```python
import subprocess, os, pty, time, select, sys, re

master, slave = pty.openpty()
proc = subprocess.Popen(
    ["hermes", "auth", "add", "xai-oauth", "--no-browser"],
    stdin=slave, stdout=slave, stderr=slave,
    close_fds=True
)
os.close(slave)

# Read initial output (URL appears within ~10s)
output = b""
start = time.time()
while time.time() - start < 12:
    r, _, _ = select.select([master], [], [], 1)
    if r:
        try:
            data = os.read(master, 4096)
            if data: output += data
        except OSError:
            break

text = output.decode("utf-8", errors="replace")
url_match = re.search(r'https://auth\.x\.ai/[^\s\r\n]+', text)
auth_url = url_match.group(0)
# Extract callback port from redirect_uri
port_match = re.search(r'127\.0\.0\.1:(\d+)', text)
callback_port = port_match.group(1)
print(f"Auth URL: {auth_url}")
print(f"Callback port: {callback_port}")
print(f"Process alive: {proc.poll() is None}, PID: {proc.pid}")
```

### Step 2: Reverse SSH tunnel from Mac
The callback goes to `127.0.0.1:<random_port>` on the browser's machine (Mac). The hermes listener is on the VPS. Bridge them:
```bash
ssh -f -N -R <callback_port>:127.0.0.1:<callback_port> lucasjouvencon@100.127.150.1
```

### Step 3: Open auth URL in Mac's Brave via CDP
```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("http://localhost:9222")
context = browser.contexts[0]
page = context.new_page()
page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
# User sees consent page → click Authorize
```

### Step 4: Authorize (via CDP click or user action)
```python
page.evaluate("""() => {
    const btns = document.querySelectorAll('button');
    for (const btn of btns) {
        const text = btn.textContent.trim().toLowerCase();
        if (text.includes('autoriser') || text.includes('authorize') || text.includes('allow')) {
            btn.click();
            return 'clicked';
        }
    }
}""")
```

## Premium+ vs API credits
- **X Premium+** ($40/mo) includes SuperGrok (web/mobile Grok access)
- **API access** requires either:
  - Paid credits on console.x.ai (minimum $5)
  - OAuth via `hermes auth add xai-oauth` (uses subscription, no credits needed)
- The `x_search` tool works with either XAI_API_KEY or xAI OAuth

## Pitfalls
- **Random callback port**: Not 56121 as docs suggest. Each invocation generates a new port. Always extract from the output.
- **X session required**: The OAuth flow redirects to X login. If X cookies are cleared, auth fails with "Vous n'avez pas pu autoriser l'accès à l'application".
- **Don't clear browser cookies globally**: `context.clear_cookies()` wipes ALL domains. Use per-domain clearing only.
- **Cookie error "RW cookie required"**: xAI Console may show this after session issues. Solution: log out and back in, or use OAuth instead of API key.
