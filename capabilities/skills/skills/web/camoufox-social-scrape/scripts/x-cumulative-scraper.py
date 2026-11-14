"""
Cumulative X/Twitter Feed Scraper
Extracts posts by scrolling and merging snapshots (dedup by key).

Usage:
    docker cp x-cumulative-scraper.py webtop:/tmp/x-cumulative-scraper.py
    docker exec webtop python3 /tmp/x-cumulative-scraper.py

Requires: X cookies already injected via /sessions/walter/cookies
"""
import http.client, json, time, random, re

TAB_ID = "REPLACE_WITH_TAB_ID"  # From POST /tabs response
SESSION_KEY = "x-scrape"         # Must match the sessionKey used
SCROLLS = 25                     # ~1.7 posts per scroll average
SCROLL_AMOUNT = 800              # Pixels per scroll
MIN_DELAY = 2.0                  # Min seconds between scrolls
MAX_DELAY = 4.0                  # Max seconds between scrolls

def api(method, path, body=None):
    h = http.client.HTTPConnection('localhost', 9378, timeout=25)
    if body:
        h.request(method, path, json.dumps(body), {'Content-Type': 'application/json'})
    else:
        h.request(method, path)
    return h.getresponse().read()

def snapshot():
    data = json.loads(api('GET', f'/tabs/{TAB_ID}/snapshot?userId=walter&sessionKey={SESSION_KEY}').decode())
    return data.get('snapshot', '')

def extract_posts(snap):
    """Extract articles from accessibility tree. Returns list of {key, full}."""
    articles = re.findall(r'article "([^"]+)"', snap)
    posts = []
    for a in articles:
        if len(a) < 50:  # Skip short UI elements
            continue
        key = a[:80].strip()  # Dedup key: author + start of text
        posts.append({'key': key, 'full': a})
    return posts

def scroll():
    api('POST', f'/tabs/{TAB_ID}/scroll', {
        'userId': 'walter', 'sessionKey': SESSION_KEY,
        'direction': 'down', 'amount': SCROLL_AMOUNT
    })

# --- Main ---
all_posts = {}  # key -> full text

# Initial snapshot
snap = snapshot()
for p in extract_posts(snap):
    all_posts[p['key']] = p['full']
print(f'Initial: {len(all_posts)} posts', flush=True)

# Scroll loop
for i in range(SCROLLS):
    try:
        scroll()
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        time.sleep(delay)
        
        snap = snapshot()
        new_count = 0
        for p in extract_posts(snap):
            if p['key'] not in all_posts:
                all_posts[p['key']] = p['full']
                new_count += 1
        
        print(f'Scroll {i+1}/{SCROLLS}: +{new_count} new (total: {len(all_posts)})', flush=True)
    except Exception as e:
        print(f'Scroll {i+1} error: {e}', flush=True)
        time.sleep(3)

# Save
with open('/tmp/x-scraped-posts.json', 'w') as f:
    json.dump(list(all_posts.values()), f, ensure_ascii=False, indent=2)

print(f'\nDone. {len(all_posts)} unique posts saved.', flush=True)
