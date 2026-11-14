#!/usr/bin/env python3
"""X/Twitter Cumulative Scraper - snapshot + scroll + merge with dedup.

Usage: python3 x-cumulative-scraper.py TAB_ID SESSION_KEY [scrolls=25]
Output: /tmp/x-{session}-posts.json
"""
import http.client, json, time, random, re, sys

TAB_ID = sys.argv[1] if len(sys.argv) > 1 else None
SK = sys.argv[2] if len(sys.argv) > 2 else None
SCROLLS = int(sys.argv[3]) if len(sys.argv) > 3 else 25

if not TAB_ID or not SK:
    print("Usage: python3 x-cumulative-scraper.py TAB_ID SESSION_KEY [scrolls]")
    sys.exit(1)

def api(method, path, body=None):
    h = http.client.HTTPConnection('localhost', 9378, timeout=25)
    if body:
        h.request(method, path, json.dumps(body), {'Content-Type': 'application/json'})
    else:
        h.request(method, path)
    return h.getresponse().read()

def snapshot():
    data = json.loads(api('GET', f'/tabs/{TAB_ID}/snapshot?userId=walter&sessionKey={SK}').decode())
    return data.get('snapshot', '')

def extract_posts(snap):
    articles = re.findall(r'article "([^"]+)"', snap)
    posts = []
    for a in articles:
        if len(a) < 50:
            continue
        key = a[:80].strip()
        posts.append({'key': key, 'full': a})
    return posts

def scroll():
    api('POST', f'/tabs/{TAB_ID}/scroll', {
        'userId': 'walter', 'sessionKey': SK,
        'direction': 'down', 'amount': 800
    })

all_posts = {}
print(f'Starting: {SCROLLS} scrolls', flush=True)

snap = snapshot()
posts = extract_posts(snap)
for p in posts:
    all_posts[p['key']] = p['full']
print(f'Initial: {len(posts)} posts (total: {len(all_posts)})', flush=True)

for i in range(SCROLLS):
    try:
        scroll()
        delay = random.uniform(2.0, 4.0)
        time.sleep(delay)
        snap = snapshot()
        posts = extract_posts(snap)
        new_count = 0
        for p in posts:
            if p['key'] not in all_posts:
                all_posts[p['key']] = p['full']
                new_count += 1
        print(f'Scroll {i+1}/{SCROLLS}: +{new_count} new (total: {len(all_posts)})', flush=True)
    except Exception as e:
        print(f'Scroll {i+1} error: {e}', flush=True)
        time.sleep(3)

out_path = f'/tmp/x-{SK}-posts.json'
with open(out_path, 'w') as f:
    json.dump(list(all_posts.values()), f, ensure_ascii=False, indent=2)

print(f'\nDone. {len(all_posts)} unique posts saved to {out_path}', flush=True)
