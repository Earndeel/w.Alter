# X/Twitter Scraping Patterns

## Feed Extraction via Camoufox Snapshot

X uses virtual scrolling — only visible posts are in the DOM. Single snapshot = ~7 posts. Cumulative scraping (scroll + snapshot + merge) = ~44 posts in 25 scrolls (~90s).

### Parsing Posts from Snapshot

Posts appear as `article "..."` entries in the accessibility tree:

```
article "Author ✓ @handle Il y a X heures Texte du post... N réponses, N reposts, N J'aime, N vues"
```

Regex to extract:
```python
articles = re.findall(r'article "([^"]+)"', snapshot)
```

### Deduplication Key

Use first 80 chars (author + handle + start of text) as unique key:
```python
key = article_text[:80].strip()
```

### Engagement Metrics Parsing

```python
views = re.search(r'([\d,]+)\s*vues', text)
likes = re.search(r"([\d,.]+)\s*J['']aime", text)
reposts = re.search(r'([\d,.]+)\s*reposts', text)
replies = re.search(r'([\d,.]+)\s*réponses', text)
```

### List Navigation

1. Navigate to `https://x.com/USERNAME/lists`
2. Snapshot → find list link by name → click ref
3. Wait 6s for list feed to load
4. Start cumulative scraping

### Rate Limiting

- 2-4s random delays between scrolls (human_sim pattern)
- No detection issues with Camoufox humanize=True + residential IP
- 25 scrolls = safe limit, ~44 posts collected

## AI List Analysis Pipeline (2026-05-31 tested)

Full workflow: scrape X list → inject into Gemini → get analysis → send to Telegram.

1. Extract X cookies from Mac Brave (63 cookies)
2. Inject into Camoufox webtop (port 9378)
3. Navigate to X lists page → click target list
4. Cumulative scrape (25 scrolls, ~90s)
5. Prepare condensed prompt (~2000 chars for Gemini type API)
6. Navigate to Gemini → type prompt → Enter → wait for response
7. Parse response from accessibility tree
8. Send to Telegram (sendMessage for text, sendPhoto for screenshot)
9. Close all tabs

**Key insight**: Camoufox type API has no `append` parameter. For long prompts, prepare a condensed version instead of trying to type in chunks.

## Nitter vs Camoufox Comparison

| | Camoufox + cookies | Nitter |
|---|---|---|
| **Auth** | ✅ Logged in as user | ❌ Public only |
| **Access** | Personal feed, lists, DMs, bookmarks | Public profiles, public tweets |
| **Speed** | Slow (~3-4s per scroll) | Fast (direct HTTP) |
| **RAM** | ~200MB (browser) | ~0 (curl sufficient) |
| **Detection** | DataDome/Turnstile risk | Rate-limit risk |
| **Interaction** | Scroll, click, type | Read-only |

**Use Camoufox** for: private lists, personalized feeds, authenticated content
**Use Nitter** for: monitoring specific public accounts, lightweight cron jobs, mass public profile scraping

**Best approach**: combine both — Nitter for daily monitoring of public accounts, Camoufox when you need authenticated/personalized content.

## Cumulative Scraping Pattern (X/Twitter)

X uses **virtual scrolling** — only visible posts are in DOM. Snapshot captures instantaneous state. To accumulate posts:

```python
all_posts = {}  # key = first 80 chars of article text

for i in range(25):
    scroll()
    time.sleep(random.uniform(2.0, 4.0))  # Human-like delays
    snap = snapshot()
    for post in extract_posts(snap):
        key = post[:80].strip()
        if key not in all_posts:
            all_posts[key] = post

# Result: ~44 unique posts from 25 scrolls (~90s)
```

## Image Analysis for Posts with Visual Content

Many X posts contain charts, diagrams, screenshots with critical data. The snapshot text misses this entirely.

**Pipeline:**
1. Snapshot → extract post text
2. `GET /tabs/:id/images` → get image URLs (filter: width > 100, skip `profile_images`)
3. `vision_analyze` on each image → extract visual content
4. Merge text + image analysis → complete understanding

**Performance:** Posts with images contain 10x more information than text alone. Example: Teknium's Kanban post had only "Vous pouvez désormais faire fonctionner vos tâches Kanban avec /goal" as text, but the image contained the complete 4-step workflow diagram with acceptance criteria, status indicators, and budget handling.

**Use `vision_analyze` with focused questions:**
- "Extract ALL text, labels, workflow steps from this diagram"
- "What data/charts are shown in this image?"
- Better than generic "describe this image"

## Cumulative Scraping (for feeds/lists)

X uses **virtual scrolling** — only visible posts are in DOM. Snapshot captures instantaneous state, so scrolling REPLACES old posts. To accumulate ALL posts across scrolls, use the cumulative pattern:

```python
import http.client, json, time, random, re

all_posts = {}  # key = first 80 chars of article text

def snapshot(tab_id, sk):
    h = http.client.HTTPConnection('localhost', 9378, timeout=25)
    h.request('GET', f'/tabs/{tab_id}/snapshot?userId=walter&sessionKey={sk}')
    return json.loads(h.getresponse().read().decode()).get('snapshot', '')

def extract_posts(snap):
    articles = re.findall(r'article "([^"]+)"', snap)
    return [{'key': a[:80].strip(), 'full': a} for a in articles if len(a) >= 50]

for i in range(25):
    scroll(tab_id, sk)
    time.sleep(random.uniform(2.0, 4.0))
    snap = snapshot(tab_id, sk)
    for p in extract_posts(snap):
        if p['key'] not in all_posts:
            all_posts[p['key']] = p['full']
    print(f'Scroll {i+1}: {len(all_posts)} total posts')
```

**Performance**: ~1.7 new posts per scroll. 25 scrolls ≈ 44 posts in ~90s.

**Dedup key**: first 80 chars of article text (author + handle + start of content).

**Ready-to-use script**: `web-service-browser/scripts/x-cumulative-scraper.py`

## Parsing Tips
- Tweets appear as `article "..."` entries with structured text
- Format: `USERNAME @handle time ago tweet text... N replies, N reposts, N likes, N views`
- Pinned tweets always appear first
- Reposts show as "X reposted @Y"
- Screenshot available via `GET /tabs/:id/screenshot` for visual verification

## Image Analysis for Post Understanding

Many X posts convey critical info via images (benchmarks, diagrams, screenshots, memes). Text-only scraping misses 10x the information.

### Extract images from page
```python
# After scrolling to load content
conn.request('GET', f'/tabs/{tab_id}/images?userId=hermes&sessionKey=scrape')
images = json.loads(conn.getresponse().read().decode())['images']
# Filter: skip profile pics (width < 100, 'profile_images' in URL)
post_images = [img for img in images if img['width'] >= 100 and 'profile_images' not in img['src']]
```

### Analyze each image
```python
from hermes_tools import vision_analyze
for img in post_images:
    analysis = vision_analyze(img['src'], "Extract ALL text, labels, data, workflow steps from this image")
    # Fuse with post text for complete understanding
```

### What images contain
- Benchmark charts (model comparisons, performance metrics)
- Workflow diagrams (step-by-step processes)
- Architecture diagrams (system designs)
- Code screenshots (terminal output, error messages)
- Infographics (data visualization, statistics)
- Memes with context (cultural references, jokes)

## Scroll Workaround: JS evaluate (PREFERRED)

The scroll API (`POST /tabs/:id/scroll`) frequently times out at default 10s. **Use JS evaluate instead** — it's faster and more reliable:

```python
# Scroll down by pixels
h = http.client.HTTPConnection('localhost', 9378, timeout=15)
h.request('POST', f'/tabs/{tab_id}/evaluate', json.dumps({
    'userId': 'walter', 'sessionKey': sk,
    'expression': 'window.scrollBy(0, 2000)'
}), {'Content-Type': 'application/json'})
h.getresponse().read()
time.sleep(1.5)
```

**Pitfall**: The `evaluate` endpoint does NOT support `return` statements. Use bare expressions like `window.scrollBy(0, 2000)`, not `return window.scrollBy(...)`.

**For cumulative scraping**: use `window.scrollBy(0, 1500-2000)` in a loop with 1.5-2s delays. 5 scrolls × 1500px loads ~10-15 new posts reliably.

## Image Analysis for Post Understanding

Many X posts convey critical info via images (benchmarks, diagrams, screenshots, memes). Text-only scraping misses 10x the information.

### Extract images from page
```python
# After scrolling to load content
conn.request('GET', f'/tabs/{tab_id}/images?userId=hermes&sessionKey=scrape')
images = json.loads(conn.getresponse().read().decode())['images']
# Filter: skip profile pics (width < 100, 'profile_images' in URL)
post_images = [img for img in images if img['width'] >= 100 and 'profile_images' not in img['src']]
```

### Analyze each image
```python
from hermes_tools import vision_analyze
for img in post_images:
    analysis = vision_analyze(img['src'], "Extract ALL text, labels, data, workflow steps from this image")
    # Fuse with post text for complete understanding
```

### What images contain
- Benchmark charts (model comparisons, performance metrics)
- Workflow diagrams (step-by-step processes)
- Architecture diagrams (system designs)
- Code screenshots (terminal output, error messages)
- Infographics (data visualization, statistics)
- Memes with context (cultural references, jokes)

## Cumulative Scraping for Lists/Feeds

X lazy-loads content. Snapshot without scroll = ~7 posts. Use cumulative extraction to get 40-50+:

```python
all_posts = {}
for i in range(25):
    scroll()
    time.sleep(random.uniform(2.0, 4.0))  # Human-like delay
    snap = snapshot()
    posts = extract_posts(snap)  # key = first 80 chars for dedup
    for p in posts:
        if p['key'] not in all_posts:
            all_posts[p['key']] = p['full']
```

Scroll via HTTP API can timeout (20s+). Use `timeout=25`. If timeouts persist, use keyboard press `End` or `PageDown`.

## X/Twitter Feed Extraction Pattern

```python
import re
# After snapshot, extract tweets as article elements
tweets = re.findall(r'article "(.+?)"', snapshot)
for t in tweets:
    # Format: "DisplayName Compte certifié @handle Il y a N heures text... N réponses, N reposts, N J'aime, N signets, N vues"
    handle_match = re.search(r'@(\w+)', t)
    handle = handle_match.group(1) if handle_match else 'unknown'
    # Split at handle to get text after it
    text_part = t[handle_match.end():] if handle_match else t
    # Extract metrics at the end
    metrics = re.findall(r'(\d+)\s*(réponses|reposts|J\'aime|signets|vues)', text_part)
    print(f"@{handle}: {text_part[:100]}...")
```
