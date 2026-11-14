#!/usr/bin/env python3
"""Open multiple web services in parallel via Camoufox.
Prerequisites: cookies-*.json files in /tmp (from split-cookies.py)
Run inside webtop container: docker exec webtop python3 /tmp/parallel-open.py gemini suno grok
"""
import http.client, json, time, sys
from concurrent.futures import ThreadPoolExecutor

SERVICES = {
    'gemini':   {'url': 'https://gemini.google.com/app',    'file': '/tmp/cookies-gemini.json'},
    'suno':     {'url': 'https://suno.com',                 'file': '/tmp/cookies-suno.json'},
    'grok':     {'url': 'https://grok.com',                  'file': '/tmp/cookies-grok.json'},
    'twitter':  {'url': 'https://x.com/home',               'file': '/tmp/cookies-twitter.json'},
    'chatgpt':  {'url': 'https://chatgpt.com',              'file': '/tmp/cookies-chatgpt.json'},
    'claude':   {'url': 'https://claude.ai',                 'file': '/tmp/cookies-claude.json'},
}

# Parse CLI args or default to all
targets = sys.argv[1:] if len(sys.argv) > 1 else list(SERVICES.keys())
targets = [t for t in targets if t in SERVICES]

if not targets:
    print(f"Usage: {sys.argv[0]} [gemini] [suno] [grok] [twitter] [chatgpt] [claude]")
    sys.exit(1)

# Step 1: Load and merge ALL cookies (single injection)
all_cookies = []
seen = set()
for name in targets:
    svc = SERVICES[name]
    try:
        with open(svc['file']) as f:
            for c in json.load(f):
                k = (c['domain'], c['name'])
                if k not in seen:
                    seen.add(k)
                    all_cookies.append(c)
    except FileNotFoundError:
        print(f"WARNING: {svc['file']} not found, skipping {name}")

print(f"Merged {len(all_cookies)} unique cookies for {len(targets)} services")

# Step 2: Inject ALL cookies ONCE
h = http.client.HTTPConnection('localhost', 9378, timeout=10)
h.request('POST', '/sessions/walter/cookies', json.dumps({'cookies': all_cookies}), {'Content-Type': 'application/json'})
r = json.loads(h.getresponse().read().decode())
print(f"Injected: {r.get('count')} cookies")

time.sleep(1)

# Step 3: Open tabs in parallel
def open_tab(name):
    svc = SERVICES[name]
    ts = int(time.time())
    sk = f'{name}-{ts}'
    conn = http.client.HTTPConnection('localhost', 9378, timeout=10)
    conn.request('POST', '/tabs', json.dumps({'userId': 'walter', 'sessionKey': sk, 'url': svc['url']}), {'Content-Type': 'application/json'})
    r = json.loads(conn.getresponse().read().decode())
    return name, r.get('tabId'), sk, r.get('url')

t0 = time.time()
results = []
with ThreadPoolExecutor(max_workers=len(targets)) as pool:
    for f in [pool.submit(open_tab, n) for n in targets]:
        results.append(f.result())

elapsed = time.time() - t0
print(f"\nOpened {len(results)} tabs in {elapsed:.1f}s:")
for name, tid, sk, url in results:
    print(f"  {name}: tab={tid} session={sk}")

print(f"\nTo interact: /tabs/{results[0][1]}/snapshot?userId=walter&sessionKey={results[0][2]}")
print("Remember to close tabs when done: DELETE /tabs/:tabId?userId=walter")
