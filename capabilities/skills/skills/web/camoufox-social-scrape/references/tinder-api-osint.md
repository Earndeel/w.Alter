# Tinder API for OSINT

## Authentication
Token from vault: `vault get tinder/api_token`
Header: `X-Auth-Token: <token>`

## Endpoints

### GET /updates (primary — works with expired auth)
```bash
curl -s "https://api.gotinder.com/updates" \
  -H "X-Auth-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"nudge":false,"message_page":0,"page_token":null}' \
  -o /tmp/tinder_updates.json
```
Parse with `json.loads(raw, strict=False)` — responses contain control characters.

### v2 endpoints (require fresh auth, often 401)
- `GET /v2/profile` — own profile
- `GET /v2/matches?count=100` — matches (may 401)
- `GET /v2/recs/core` — recommendations (401)

## Data available per match
```json
{
  "person": {
    "_id": "69dd1c0debf1d75645fb3b28",
    "name": "Elissa",
    "bio": "...",
    "birth_date": "1993-05-25T17:42:12.979Z",
    "gender": 1,
    "jobs": [],
    "schools": [],
    "photos": [
      {"url": "https://images-ssl.gotinder.com/{id}/original_{uuid}.jpg"}
    ]
  },
  "messages": [
    {"from": "{person_id}", "message": "text"},
    {"from": "{your_id}", "message": "text"}
  ],
  "distance_mi": null,
  "last_activity_date": "2026-05-11T12:27:00.844Z"
}
```

## Photo URLs
Pattern: `https://images-ssl.gotinder.com/{person_id}/original_{uuid}.jpg`
Download: `curl -s -o /tmp/tinder_photo_N.jpg "<url>"`
Photos are public URLs — no auth needed to download.

## OSINT from Tinder data
- **birth_date** → exact age calculation
- **name** → may be first name only, nickname, or second name (not necessarily legal name)
- **messages** → reveals language, location (neighborhood), profession, travel history
- **photos** → reverse image search, location clues (landmarks, architecture, vegetation)
- **jobs/schools** → often empty but when present, strong identifiers
- **last_activity_date** → recency of use

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
