# Multi-Service Parallel Opening

## Critical Rule

**Inject ALL cookies in ONE call.** Multiple `/sessions/walter/cookies` calls with same userId OVERWRITE previous cookies — last call wins.

## Pattern

```python
import http.client, json, time
from concurrent.futures import ThreadPoolExecutor

# 1. Extract + decrypt cookies for ALL services
# 2. Merge into single list, deduplicate by (domain, name)
# 3. Inject ONCE

h = http.client.HTTPConnection('localhost', 9378, timeout=10)
h.request('POST', '/sessions/walter/cookies', 
          json.dumps({'cookies': all_cookies}),
          {'Content-Type': 'application/json'})
h.getresponse().read()

time.sleep(1)  # Let cookies settle

# 4. Open tabs in parallel
SERVICES = {
    'gemini': 'https://gemini.google.com/app',
    'suno':   'https://suno.com',
    'grok':   'https://grok.com',
}

def open_tab(name, url):
    ts = int(time.time())
    sk = f'{name}-{ts}'
    conn = http.client.HTTPConnection('localhost', 9378, timeout=10)
    conn.request('POST', '/tabs', 
                 json.dumps({'userId': 'walter', 'sessionKey': sk, 'url': url}),
                 {'Content-Type': 'application/json'})
    r = json.loads(conn.getresponse().read().decode())
    return name, r.get('tabId'), sk

with ThreadPoolExecutor(max_workers=3) as pool:
    futures = [pool.submit(open_tab, n, u) for n, u in SERVICES.items()]
    for f in futures:
        name, tab_id, sk = f.result()
        print(f'{name}: {tab_id}')

time.sleep(6)  # Wait for pages to load

# 5. Take screenshots in parallel
def screenshot(name, tab_id, sk):
    h = http.client.HTTPConnection('localhost', 9378, timeout=15)
    h.request('GET', f'/tabs/{tab_id}/screenshot?userId=walter&sessionKey={sk}')
    data = h.getresponse().read()
    with open(f'/tmp/svc-{name}.png', 'wb') as f:
        f.write(data)
    return name, len(data)

# 6. Close all tabs after use
def close_tab(tab_id):
    h = http.client.HTTPConnection('localhost', 9378, timeout=5)
    h.request('DELETE', f'/tabs/{tab_id}?userId=walter')
    h.getresponse().read()
```

## Cookie Splitting by Service

```python
# After extracting all cookies, split by domain
def filt(*domains):
    return [c for c in cookies if any(d in c['domain'] for d in domains)]

by_svc = {
    'gemini': filt('google', 'gemini'),
    'suno':   filt('suno'),
    'grok':   filt('grok', 'x.ai'),
}
```

## Performance (tested 2026-05-31)

- Extract: ~5s (SSH to Mac)
- Decrypt + split: ~0.5s
- Inject + navigate ×3: ~7.8s (parallel)
- Screenshots ×3: ~2s (parallel)
- Total: ~15s for 3 services

## Cloudflare Bypass

Grok.com uses Cloudflare Turnstile. Bypass with Tailscale exit node:
```bash
tailscale set --exit-node=100.127.150.1  # Mac residential IP
```
