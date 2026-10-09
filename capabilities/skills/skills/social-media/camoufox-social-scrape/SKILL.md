---
name: camoufox-social-scrape
description: Scrape social media profiles (X/Twitter, Facebook, Instagram) via Camoufox browser API when API credentials are unavailable. Also covers multi-platform OSINT people search — finding a person's real name, profiles, and digital footprint from partial information.
tags: [camoufox, twitter, scraping, social-media, fallback, osint, people-search]
related_skills: [contact-intelligence-systems, web-service-browser]
---

# Camoufox Social Scrape + OSINT

Fallback for scraping social media when official APIs aren't available. Uses Camoufox's local browser API (port 9377) to navigate profiles and extract content from the accessibility tree. Also covers multi-platform people search (OSINT) to identify a person from partial info (name, phone, city, profession, physical traits).

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

## When to Use

### Social Scraping
- X/Twitter API credentials not configured (x-cli unavailable)
- Read-only scraping of public profiles
- Need visual content (images, video previews) alongside text
- Avoid API rate limits or costs

### OSINT / People Search
- Finding a person's real name, social profiles, or digital footprint
- Cross-referencing partial data: first name + city + profession + physical traits
- Phone number lookup via social platform search
- Profile picture analysis (reverse image, EXIF, background clues)

## Prerequisites
- Camoufox running on `localhost:9378` (camoufox-max server; check: `GET /health` → `{"ok": true}`). Port 9377 is the older non-max instance.
- No social media API keys needed
- **Tinder API** available for match data (see `references/tinder-api-osint.md`)
- **Webtop non-headless browsing** for Google/Bing without CAPTCHA (see `references/webtop-nonheadless-browsing.md`)
- **OSINT image search methodology** — the right way to search and visually match (see `references/osint-image-search-methodology.md`)
- **OSINT professional platform cross-reference** — deep dive into Codeur/Malt/LinkedIn after finding a name (see `references/osint-professional-platform-crossref.md`)
- **Instagram deep extraction without login** — Google+StarNgage+screenshot pattern (see `references/instagram-deep-extraction.md`)

## Quick Start

**Note**: For cookie-based authenticated browsing, see `web-service-browser` skill — it has the optimized pipeline (extract → decrypt → inject → navigate).

## Quick Start

**See also** `references/localstorage-extraction.md` for SPA auth extraction via LevelDB, and `references/api-key-extraction.md` for extracting masked API keys from dashboards via screenshot + vision.

```python
import json, http.client, time

def camoufox(method, path, body=None):
    conn = http.client.HTTPConnection("localhost", 9378)
    if body:
        headers = {"Content-Type": "application/json"}
        conn.request(method, path, json.dumps(body), headers)
    else:
        conn.request(method, path)
    resp = conn.getresponse()
    raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else {}

# 1. Create tab
tab = camoufox("POST", "/tabs", {"userId": "hermes", "listItemId": "scrape"})
tab_id = tab["tabId"]

# 2. Navigate
camoufox("POST", f"/tabs/{tab_id}/navigate", {
    "userId": "hermes", "listItemId": "scrape",
    "url": "https://x.com/USERNAME"
})
time.sleep(5)

# 3. Scroll to load content (X lazy-loads)
for i in range(8):
    camoufox("POST", f"/tabs/{tab_id}/scroll", {
        "userId": "hermes", "listItemId": "scrape",
        "direction": "down"
    })
    time.sleep(1)

# 4. Capture snapshot
snap = camoufox("GET", f"/tabs/{tab_id}/snapshot?userId=hermes&listItemId=scrape")
print(json.dumps(snap, indent=2)[:5000])

# 5. Cleanup
camoufox("DELETE", f"/tabs/{tab_id}?userId=hermes&listItemId=scrape")
```

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

## Sending Results to Telegram

**Format**: `parse_mode=HTML` (not Markdown). Telegram does NOT support `<table>` tags.
**Limit**: 4096 chars per message. Split if needed.
**Rule**: Send EXACT response from service, never reformat. No screenshots/files unless user asks.

**User frustration signals** (from session corrections):
- "je t'ai pas demandé un screenshot" — don't add screenshots without request
- "c'est pas la réponse exacte" — send raw text, not summaries
- "je veux simplement ouvrir mon message Telegram et avoir un message propre" — user wants to READ in Telegram, not download files

## Parsing Tips
- 5-10 scrolls covers ~10-15 tweets
- Too-fast scrolling may trigger "Something went wrong" — add 1-2s delays
- Snapshots can be very large (>15K chars) — parse in Python, print sections
- Public profiles only — login-gated content needs session cookies
- **Virtual scrolling**: X removes old posts from DOM as you scroll. Use cumulative scraping (snapshot → extract → scroll → merge with dedup) to accumulate. See `web-service-browser` skill → `scripts/x-cumulative-scraper.py`.
- **Scroll timeouts**: default 10s may fail. Use 20s+ timeout. Snapshot still succeeds even if some scrolls fail.
- **Performance**: ~1.7 new posts per scroll. 25 scrolls ≈ 44 posts in ~90s.
- **Scroll operations timeout at default 10s** — use 20s+ timeout for X scrolls
- **Cloudflare Turnstile on X/Grok**: datacenter IPs get blocked. Route through Mac's residential IP via Tailscale exit node: `tailscale set --exit-node=100.127.150.1`. Container inherits host routing. Deactivate after use if slow: `tailscale set --exit-node=""`
- **Tab lifecycle**: always close tabs after scraping (`DELETE /tabs/:id?userId=...`) to save RAM

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

## OSINT People Search Methodology

When trying to identify a person from partial information, use this ordered search funnel. **Start with the lowest-friction methods and escalate.**

### Tier 0: Tinder API (if match exists) — HIGHEST VALUE, ZERO FRICTION
If the target is a Tinder match, the API gives direct access to their **real profile name** (often different from display name), **birth date**, **photos** (full-res URLs), **bio**, **jobs**, **schools**, and **full conversation history**. This is worth more than hours of web scraping.

```bash
# Token in vault: vault get tinder/api_token
TINDER_TOKEN="<token>"

# /updates returns all matches + messages (v2/matches often 401s)
curl -s "https://api.gotinder.com/updates" \
  -H "X-Auth-Token: $TINDER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"nudge":false,"message_page":0,"page_token":null}' \
  -o /tmp/tinder_updates.json
```

```python
import json
with open('/tmp/tinder_updates.json') as f:
    data = json.loads(f.read(), strict=False)  # strict=False required — control chars in messages

for m in data.get('matches', []):
    person = m.get('person', {})
    name = person.get('name', '')
    if target_name.lower() in name.lower():
        photos = [p['url'] for p in person.get('photos', [])]
        # Download: curl -s -o /tmp/tinder_photo_N.jpg "$URL"
        # Analyze each photo with vision_analyze for location, clothing, lifestyle clues
```

**Key data available via Tinder:**
- `person.name` — often a first name or nickname (may differ from real name)
- `person.birth_date` — exact DOB (calculate age)
- `person.photos[].url` — full-resolution photos (gotinder.com CDN)
- `person.bio` — self-description
- `person.jobs` / `person.schools` — professional/education info
- `messages[]` — full conversation with timestamps and sender IDs
- `distance_mi` — proximity at match time

**Photo OSINT workflow:** Download all photos → `vision_analyze` each for: location landmarks, clothing brands, jewelry, hair color (natural vs dyed), background architecture, text/signs, setting (hotel, resort, apartment style). Cross-reference with known data.

**Pitfall:** Tinder photo URLs are ephemeral CDN links — download immediately, don't just save URLs.

### Tier 1: Brave API (fast, anonymous) — HARD CAP 10 QUERIES
Run 8-10 queries varying name, city, profession, platform. Try BOTH first names, quoted and unquoted.
**Hard-won reality (2026-05-22)**: For low-profile French people with only a first name, Brave returns ZERO across 40+ query variations. If 10 queries return nothing, STOP and move to Tier 2. Burning time on Brave is the #1 OSINT time-waster.

### Tier 2: Facebook public search via Camoufox (BEST unauthenticated option)
```
https://www.facebook.com/public/{FirstName}-{City}
```
Facebook public search works WITHOUT login and returns profile names + partial bios. This is the single best unauthenticated people search. Parse `link "Name Surname"` entries from the accessibility tree snapshot. **This should be your FIRST browser-based search**, not Instagram or LinkedIn.

### Tier 3: Mac Brave Cookies → Camoufox (if Mac accessible via SSH)
**NEVER connect Scrapling/Playwright to Mac Brave CDP** — it opens visible tabs/pop-ups on Monsieur's Mac (port 9226 is the W.Alter instance with NO cookies; the main Brave has NO remote debugging).

Instead: extract cookies from the Mac Brave SQLite DB via SSH, decrypt them, and inject into Camoufox. Full workflow in `references/brave-cookie-extraction.md`.

Quick sequence:
1. `scp` the Cookies DB from Mac (`~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies`)
2. Query target domains with `sqlite3`
3. Get Keychain password from vault (`macos/lucas_password`) → run on Mac terminal directly
4. Decrypt with PBKDF2 + AES-128-CBC (strip first 16 garbled bytes)
5. Inject into Camoufox via `POST /tabs/:id/set_cookies`
6. Navigate to platform → verify login state with screenshot

### Tier 3b: Google/Bing Image Search — BEST for visual matching

**Search query formula: Identification + Activity/Profession + Location**
Do NOT add physical traits to the search query (no "rousse", "bouclée", etc.). The search engine won't find a specific person by hair color. Instead, search for:
- `{name} {profession} {city}` (e.g. "Marika marketing SEO Montpellier")
- `{name} {activity} {city}` (e.g. "Marika danse orientale Montpellier")
- `{name} {profession} {activity}` (e.g. "Marika SEO freelance")

Then use **visual cross-referencing**: look at the actual image results and compare each photo against known physical description (hair color, age, ethnicity, distinguishing features). The search finds candidates by professional identity; your eyes do the physical matching.

**Image examination protocol (MANDATORY — do not skip):**
1. Take a screenshot of the search results page
2. Run `vision_analyze` on the screenshot asking: "Look at EVERY photo. Is there ANY woman matching [physical description]? List each real person photo individually."
3. Do NOT rely on link titles alone — titles are generic ("Image result for..."). The actual photos may show the target.
4. When a promising image is found, check for **watermarks** and **source labels** beneath the image — these often reveal the person's business name, website, or social handle.
5. Click through promising results to find the source URL.

**Platform notes:**
- **Google Images** works from Webtop non-headless Camoufox (no CAPTCHA). Only Google Lens gets 403. See `references/webtop-nonheadless-browsing.md`.
- **When Google rate-limits (CAPTCHA)**: Use Scrapling stealthy_fetch with solve_cloudflare=True to bypass. Returns text with image source labels. For screenshots, open a Scrapling stealthy session. See `references/osint-image-search-methodology.md`.
- **Bing Images** is a fallback when Google is fully blocked. BUT: Google returns substantially better results for professional identity searches. Always try Google first, then Bing.
- **Always try BOTH Google and Bing** — they return different images for the same query. The target may appear in one but not the other.
- Both platforms return ~8-10 images above the fold. Scroll down for more results if the first batch has no match.
- **URL slug analysis**: When image results link to profile/about pages, the URL slug often contains the person's full name (e.g., `/a-propos-marieke-moliner`). Extract and parse these even when the page title is generic.

### Tier 4: Instagram handle guessing + Reverse Image Search
**Reverse image search first** (if you have photos): Use Yandex Images (see `references/reverse-image-search.md`). Check the "Sites" tab for exact matches. Google Lens is blocked — don't bother.

Then try handle patterns via HEAD requests (existence check only — viewing requires login):
- `{name}_{city}`, `{name}.{city}`, `{name}_{profession}`
- `{name}.{trait}`, `{name}_{trait}`
**WARNING**: Instagram returns 200 for ALL handles (even non-existent) with a login page. Check `<title>` tag: real profiles show `Name (@handle) • Instagram photos and videos`, non-existent just show `Instagram`.
X/Twitter: `x_search(query="{name} {city} {profession}")`

### Tier 4c: StarNgage — Instagram Analytics Without Login
When you find an Instagram handle but can't view the profile (login required), StarNgage provides public analytics:
```
https://starngage.com/chr/influencers/{handle}
```
StarNgage shows: bio text, follower/following counts, engagement rate, post count, location, business category, and sometimes website links. This was how "Marika Palma" was confirmed as "Marika Moliner" — StarNgage showed "Founder of @maisonsantal" in the bio, linking the dance persona to the known e-shop.
Google `"@handle" site:starngage.com` to find the page, or construct the URL directly.

### Tier 4b: Reverse Image Search (when you have photos)
- **Google Lens = 403 Forbidden** even from non-headless Camoufox with residential IP. Google homepage and regular image search work fine — only Lens has strict anti-bot. Don't attempt.
- **Yandex Images works** without CAPTCHA. Use URL format: `https://yandex.com/images/search?rpt=imageview&url={encoded_image_url}`. Check "Sites" tab for profile matches. "Similar images" tab finds visual matches but rarely the exact person.
- **TinEye**: reliable for exact matches but returns nothing for Tinder/social photos (not indexed).
- **Bing Visual Search**: works when Google is rate-limited. Less aggressive anti-bot.
- **Instagram handle guessing**: test via HEAD requests. Instagram returns 200 for ALL handles (login page). Check `<title>` tag: real profiles show `Name (@handle) • Instagram photos and videos`, non-existent just show `Instagram`.

### Tier 5: Phone lookup + Business registries
- Truecaller (requires login — dead end without session)
- French directories: PagesJaunes, 118712 (useless for mobile numbers)
- French business registries: societe.com, pappers.fr, annuaire-entreprises.gouv.fr

### Persisting Results to Kardex

After identifying a person, persist all findings to the Kardex PostgreSQL schema (`hindsight-pg`, schema `kardex`). This makes the data queryable across sessions and integrates with the broader contact intelligence system.

### Tables to populate (in order)

1. **`kardex.contacts`** — Main identity record
   - `canonical_name`: Real full name (e.g., "Marika Moliner")
   - `aliases`: Array of all known names (real name, nicknames, dating app names, handles)
   - `phone_numbers`, `emails`: Verified contact info
   - `handles`: JSONB of platform → handle mappings
   - `location_current`, `location_home`: Current and home locations
   - `occupation`, `interests`, `key_facts`: Professional and personal data
   - `relationship_type`: How this person connects to the user (e.g., "match_tinder", "contact_beeper")
   - `sources`: Array of data sources used

2. **`kardex.identity_links`** — Platform-specific identifiers
   - One row per platform/handle/URL with confidence score
   - Use `ON CONFLICT (source, identifier_type, normalized_value) DO NOTHING` for idempotency

3. **`kardex.evidence`** — Source quotes and references
   - One row per data source with exact quote and confidence
   - `evidence_type`: 'web_profile', 'api_data', 'image_match', 'messaging'

4. **`kardex.channels`** — Communication channels
   - Platform, platform_id, platform_handle
   - UNIQUE constraint on (contact_id, platform, platform_id)

5. **`kardex.social_graph`** — Relationships to other contacts
   - Link to source contacts (e.g., Lucas → Marika)

### SQL templates
```sql
-- Contact
INSERT INTO kardex.contacts (canonical_name, aliases, phone_numbers, handles, ...)
VALUES ('Name Surname', ARRAY['Alias1','Alias2'], ARRAY['+336...'], '{...}'::jsonb, ...)
RETURNING id;

-- Identity links (use the returned contact_id)
INSERT INTO kardex.identity_links (contact_id, source, identifier_type, identifier_value, normalized_value, strength, confidence)
VALUES (N, 'linkedin', 'profile_url', 'linkedin.com/in/...', '...', 'strong', 0.95)
ON CONFLICT (source, identifier_type, normalized_value) DO NOTHING;

-- Evidence
INSERT INTO kardex.evidence (contact_id, source, source_ref, quote, evidence_type, confidence)
VALUES (N, 'digitalbliss.fr', 'a-propos', 'Hello, je suis Marika...', 'web_profile', 0.95);
```

**Pitfall**: The `emails` column requires `ARRAY[]::text[]` cast, not bare `ARRAY[]`. JSONB handles field needs proper quoting when passed through shell. The `channels` table uses `platform_id` and `platform_handle` (NOT `channel_id` and `display_name`). Write SQL to a temp file and `docker cp` + `psql -f` to avoid shell quoting hell.

## OSINT Pitfalls

- **Google Lens blocked even from non-headless Camoufox with residential IP**: Google returns 403 Forbidden on Lens specifically. However, Google homepage, text search, and regular Google Images search (`udm=2`) all work fine from non-headless Camoufox in Webtop (visible via Selkies on port 3001). Only Lens has strict anti-bot. Use Yandex for reverse image search instead. See `references/webtop-nonheadless-browsing.md` for the full compatibility matrix.
- **Don't search by physical traits — search by identity + activity + location**: Searching "Marika rousse boucle Montpellier" returns generic stock photos of redheads. Searching "Marika marketing SEO Montpellier" returns actual professional profiles and business pages where the person might appear. Then VISUALLY cross-reference the images with known physical description. The search engine finds candidates by professional identity; your eyes do the physical matching.
- **Malt.fr/ComeUp search URLs don't work with query params**: `malt.fr/search?q=...` returns 404. Malt requires using the homepage search box interactively. ComeUp returns "Page cannot be found" for constructed search URLs. Don't try direct URL construction for these platforms.
- **French phone directories are useless for mobile numbers**: PagesJaunes, 118712, sync.me don't return names for mobile numbers (06/07). Truecaller requires login. The phone number approach is a dead end without a Truecaller session.
- **NEVER connect Scrapling/Playwright to Mac Brave CDP (port 9226)**: It opens visible tabs and pop-ups on Monsieur's Mac, disrupting his work. Use Camoufox or Webtop Chromium instead. If you need the Mac's logged-in sessions, extract cookies directly from Brave's SQLite DB (see cookie extraction workflow in `webtop-authenticated-browsing` skill). Port 9226 is the W.Alter Brave instance (`--user-data-dir=/tmp/brave-walter`) — it has NO social media cookies. The main Brave (with cookies) has NO remote debugging enabled.
- **Brave cookie extraction for authenticated searches**: When you need Facebook/Instagram/LinkedIn sessions from Mac Brave, extract cookies from `~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies` via SSH, decrypt with the Keychain password (get via `osascript` with administrator privileges using the Mac password from vault), inject into Camoufox. First 16 bytes of each decrypted cookie are always garbled (wrong IV) — strip them with regex. Domain cookies share the same first ciphertext block (deterministic encryption). Full workflow: `webtop-authenticated-browsing` skill.
- **Instagram handle guessing via curl HEAD**: Returns 200 for BOTH existing AND non-existing handles (Instagram serves a login page with 200 for everything). To verify existence, check the `<title>` tag: real profiles show `"Username (Display Name) • Instagram photos and videos"`, non-existent profiles show just `"Instagram"`. Use: `curl -s "https://www.instagram.com/$handle/" | grep -o "<title>[^<]*</title>"`. Viewing profile content (bio, posts, followers) REQUIRES login via Camoufox with injected cookies — the snapshot will just show "See full profile in the app" without it.
- **Message attribution errors**: On platforms like Beeper where API only returns incoming messages, it's easy to misattribute the OTHER person's statements to the target. Messages like "J'ai fait ma medecine a Montpellier" could be from EITHER party. Cross-validate every claim against known facts about each person BEFORE building the profile.
- **Instagram/LinkedIn require login**: Most searches redirect to login pages. Facebook public search is the best unauthenticated option.
- **Cloudflare protection**: French freelance platforms (Malt.fr, ComeUp) use Cloudflare — Camoufox stealth mode may be needed.
- **Zero digital footprint is common**: Not finding someone doesn't mean they don't exist — it means they have no public web presence. Report this honestly rather than burning excessive time. A ghost result is itself useful intel.
- **Tinder photos are PRIVATE CDN links — reverse image search won't find them**: Tinder photos are served from `images-ssl.gotinder.com` and are only visible to matched users. They are NOT indexed by Google, Yandex, TinEye, or any search engine. Reverse image search will find visually similar photos of OTHER people (because the algorithms match on visual features, not identity), but never the exact Tinder photo. To find someone's public profiles, use their name, handle, or other textual data — not their Tinder photos.
- **Bing image detail panel may show a DIFFERENT image than the thumbnail**: When clicking on a Bing Images result, the detail panel overlay may show a completely different image (e.g., clicking "Agence SEO Kisytech" showed a "Thailand Digital Marketing" image from fortune-thailand.com). Always take a screenshot of the detail panel to verify which image is actually displayed, and check the source URL in the panel header. Don't trust that the thumbnail matches the detail view.
- **Google Images outperforms Bing for professional identity searches**: In testing, "Marika marketing SEO Montpellier" returned the correct match (Digital Bliss, a marketing freelancer in Montpellier) on Google Images but NOT on Bing Images, which showed generic SEO agency stock photos. When an OSINT search on Bing yields nothing, always retry on Google before giving up. Use Scrapling stealthy_fetch to bypass Google CAPTCHA if Camoufox is rate-limited.
- **Always search with the REAL name, not the dating app name**: People often use nicknames or middle names on dating apps (Tinder, Bumble). Their public profiles (LinkedIn, Facebook, Instagram) use their real first name. If you have both names (e.g. real name "Marika" from WhatsApp, Tinder name "Elissa"), prioritize the real name for all web searches. Check the Tinder `person.name` vs. known real name — they're often different.
- **Don't abandon a working lead to chase tangents — FOLLOW THROUGH first**: When the user says your first lead was good but you diverged, it means: if you have a promising lead (e.g., watermark on a group photo), FOLLOW THAT THREAD to its conclusion before exploring alternatives. Don't jump to Facebook (may find a different person in a different country), then YouTube (dead videos), then Codeur.com — all while the original lead (the watermark's source association, the tagged dancers in the photo) goes uninvestigated. Complete one lead before starting the next.
- **Facebook profiles must be VERIFIED before adding to Kardex**: A Facebook profile matching the target's name is NOT sufficient evidence. Real failure: found a Facebook profile with the right name but wrong country (Switzerland vs France). Always verify: (1) location matches, (2) profession/activity matches, (3) connections/context match. If any don't align, discard.
- **Instagram deep extraction WITHOUT login — the Google+StarNgage pattern**: When you find an Instagram handle but can't view the profile (login wall), extract data from three sources: (1) Google search site:instagram.com returns cached post captions, engagement counts, dates, hashtags, and tagged-by info. (2) StarNgage analytics returns bio, follower counts, engagement rate, location. (3) Google Images returns post thumbnails. Combining these gives full bio, post themes, hashtags, who tags them, travel/work locations — all without logging in.
- **Finding handles via community cross-reference**: When a direct search fails, search for the person through their COMMUNITY. Search for: event/festival participants, community leaders posts that tag or mention members, association member lists, competition lineups. The community public posts often reveal handles that the person own private profile does not.
- **Don't stop at the first match — EXHAUST ALL leads before presenting**: When you find a promising match (e.g., "Digital Bliss" for Marika), don't present it immediately and stop. Continue investigating ALL other leads (e.g., "Marika Danse Orientale", "Marika Palma") before reporting back. The user will explicitly correct you: "tu as pas creuser du cote danse." Exhaust all leads in parallel or sequentially, then present the complete picture with cross-references. Only stop when you've confirmed or eliminated each lead. **Real failure**: Found Digital Bliss → presented it → user said "tu as trouver une bonne reponse et tu en as rater une autre" → had to go back and investigate the dance lead separately → found @marika.palma Instagram which PROVED the dance lead was the same person via "Founder of @maisonsantal" in bio.
- **Don't burn 40+ queries on a ghost**: If 10 Brave queries return nothing, STOP. Move to Facebook public search or tell the user the limits. The user will get frustrated watching you run query after query with zero results — be upfront about the wall you hit.
- **NEVER open tabs on Mac Brave CDP** (port 9226): Connecting Scrapling/Playwright to the user's main Brave opens visible tabs and pop-ups on their screen. Use Camoufox (localhost:9377) or Webtop Chromium for all browsing. The only valid use of Mac Brave CDP is reading (cookies, history), never navigation.
- **macOS Keychain cookie decryption via SSH requires osascript**: The `security find-generic-password -w` returns errSecInteractionNotAllowed (-25308) via SSH. Use `osascript -e 'do shell script "..." user name "X" password "Y" with administrator privileges'` instead. The login keychain must be in the search list — add it explicitly if needed.
