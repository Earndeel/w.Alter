# web-service-browser — X/Twitter cumulative and list scraping.

Moved verbatim from SKILL.md on 2026-11-01.

## X Cumulative Scraping Pattern

X lazy-loads content. Snapshot without scroll = ~7 posts. With scroll = ~12. To get 40-50+ posts, use cumulative extraction:

```python
all_posts = {}
for i in range(25):
    scroll()
    time.sleep(random.uniform(2.0, 4.0))
    snap = snapshot()
    posts = extract_posts(snap)  # key = first 80 chars
    for p in posts:
        if p['key'] not in all_posts:
            all_posts[p['key']] = p['full']
```

Scroll via HTTP API can timeout (20s+). Use `timeout=25` per scroll call. If scroll timeouts persist, use keyboard press `End` or `PageDown` instead.

## X/Twitter Cumulative Scraping (KEY TECHNIQUE)

X uses **virtual scrolling** — only visible posts are in the DOM. Snapshot captures instantaneous DOM state, so scrolling REPLACES old posts with new ones. To accumulate:

```python
# Pattern: snapshot → extract → scroll → snapshot → extract → MERGE with dedup
all_posts = {}  # key = first 80 chars of article text

for i in range(25):
    scroll()
    time.sleep(random.uniform(2.0, 4.0))  # Human-like delays
    snap = snapshot()
    for post in extract_posts(snap):
        if post['key'] not in all_posts:
            all_posts[post['key']] = post['full']
```

**Dedup key**: first 80 chars of article text (author + handle + start of content). This is unique per tweet.

**Performance**: ~1.7 new posts per scroll. 25 scrolls ≈ 44 posts in ~90s.

**Script**: `scripts/x-cumulative-scraper.py` — ready to run:
```bash
docker cp scripts/x-cumulative-scraper.py webtop:/tmp/
docker exec webtop python3 /tmp/x-cumulative-scraper.py TAB_ID SESSION_KEY 25
```

## X/Twitter List Scraping

Navigate to specific lists (e.g., "Artificial Intelligence") to scrape curated feeds.

```python
# 1. Navigate to user's lists page
conn.request('POST', f'/tabs/{tab_id}/navigate', 
    json.dumps({'userId': 'walter', 'sessionKey': sk, 'url': 'https://x.com/earndeel/lists'}),
    {'Content-Type': 'application/json'})

# 2. Snapshot to find the list link
# Look for: link "List Name N members" [eN]
snap = snapshot(tab_id, sk)
# Example: link "Artificial intelligence 41 membres" [e24]

# 3. Click the list link
conn.request('POST', f'/tabs/{tab_id}/click',
    json.dumps({'userId': 'walter', 'sessionKey': sk, 'ref': 'e24'}),
    {'Content-Type': 'application/json'})

# 4. Wait for feed to load, then snapshot
time.sleep(6)
snap = snapshot(tab_id, sk)  # Contains tweets as article elements

# 5. Scroll for more tweets (10 scrolls ≈ 12 tweets total)
for i in range(10):
    conn.request('POST', f'/tabs/{tab_id}/scroll',
        json.dumps({'userId': 'walter', 'sessionKey': sk, 'direction': 'down', 'amount': 800}),
        {'Content-Type': 'application/json'})
    time.sleep(random.uniform(1.5, 3.0))  # Human-like delays
```

**List URL pattern**: `https://x.com/i/lists/{list_id}` — but IDs may change. Better to navigate via user's lists page.

**Parsing tweets from snapshot:**
```python
import re
tweets = re.findall(r'article "(.+?)"', snapshot)
# Each tweet format: "DisplayName ✓ @handle Il y a N heures text... N réponses, N reposts, N J'aime, N vues"
```

**X-specific gotchas:**
- ~7 tweets per snapshot without scrolling, ~12 with 10 scrolls
- Scroll too fast → "Something went wrong" error
- Use 20s+ timeout for scroll operations (default 10s may fail)
- Snapshot can be >15K chars — parse in sections
- `Compte certifié` = verified account
- Reposts show as "DisplayName a reposté OriginalAuthor"

