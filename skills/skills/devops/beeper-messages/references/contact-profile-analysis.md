# Contact Profile Analysis from Beeper Conversations

When the user asks to "analyze the conversation with X and build their profile" or "find out who X really is":

## Step 1: Fetch full conversation
- Resolve chat ID (paginate if needed)
- Fetch ALL messages via sortKey pagination
- Count outgoing vs incoming early — if outgoing is 0, you only see one side (known API limitation)

## Step 2: Extract profile data from messages
Look for:
- **Names**: real name, nicknames, second names, aliases mentioned
- **Location**: city of origin, current city, travel plans
- **Profession/studies**: school, degree, job title, industry
- **Physical traits**: hair color, style, distinguishing features
- **Interests/hobbies**: shows, music, sports, food preferences
- **Personality markers**: humor style, communication patterns, emoji usage
- **Relationship signals**: what they're looking for, boundaries, past relationships
- **Shared links or @handles**: any URLs, social media handles, or references

## Step 3: Profile picture
- Get `imgURL` from chat participant data
- SCP from Mac → analyze with `vision_analyze` or OpenRouter vision
- Note: profile pic may be old or misleading

## Step 4: Identity search (multi-platform)

Search for the person's real name across platforms. Cast a wide net. **ORDER MATTERS** — start cheapest, escalate only when needed. **Hard cap Tier 1 at 10 queries** — if nothing after 10, move to Tier 2 immediately. Burning 40+ Brave queries on a ghost is wasted time.

### Tier 1: Brave Search API (fast, free, ~10 queries max)
Run 8-10 queries covering name variations, city, profession. Try BOTH first names if you have two.
```bash
BRAVE_KEY=$(vault get brave/api_key)
# Core combos
"{name1}" + "{name2}" + "{city}"
"{name}" + "{profession}" + "{city}"
# Platform-specific
site:linkedin.com + "{name}" + "{profession}" + "{city}"
# Phone
"{phone_number}"
# Unique traits
"{name}" + "{physical_trait}" + "{city}"
```
**Hard-won reality**: Brave API returns ZERO for most low-profile French people. 80%+ of OSINT targets with only a first name will hit this wall. Move on fast.

### Tier 2: Facebook public search via Camoufox (BEST unauthenticated option)
```
https://www.facebook.com/public/{FirstName}-{City}
```
Facebook public search works WITHOUT login and returns profile names + partial bios. This is the single best unauthenticated people search. Parse `link "Name Surname"` entries from the accessibility tree snapshot.

### Tier 3: Mac Brave CDP (if SSH tunnel active)
If the Mac has social media sessions (Facebook, Instagram, LinkedIn), connect via Scrapling CDP:
```python
mcp_scrapling_open_session(cdp_url="ws://localhost:9226/devtools/browser/{id}", session_id="osint", session_type="dynamic")
```
**Check tabs first**: `curl http://localhost:9226/json` — if no tabs open, the browser has no active sessions. Screenshot the platform homepage to verify login state before attempting searches.

### Tier 4: Instagram handle guessing
Try handle patterns via curl HEAD requests (works without login for existence check):
- `{name}_{city}`, `{name}.{city}`, `{name}_{profession}`
- `{name}.{trait}`, `{name}_{trait}`
A 200 + non-empty `<title>` containing the handle = profile exists. BUT: viewing the profile requires login.

### Tier 5: X/Twitter + Phone lookup
- `x_search(query="{name} {city} {profession}")`
- Truecaller (requires login), Sync.me, Pages Jaunes (mobile numbers rarely listed)
- French business registries: societe.com, pappers.fr, annuaire-entreprises.gouv.fr

### Tier 6: Reverse Image
- Google Lens on WhatsApp profile picture (requires browser with Google session)
- EXIF analysis of profile pic (usually stripped, but check)

### Platforms that REQUIRE login (don't waste time without sessions)
- Instagram search/explore
- LinkedIn people search
- TikTok search
- Facebook search (different from public search)
- Malt.fr search (use homepage search box, not URL params)
- Truecaller

### Platforms that work WITHOUT login
- Facebook public search: `/public/{Name}-{City}`
- X/Twitter via `x_search` tool
- Brave Search API
- GitHub, Behance, Dribbble public profiles
- Instagram profile pages (if you know the exact handle)
- annuaire-entreprises.api.gouv.fr

## Step 5: Compile report
Present as a structured profile:
- **Identité**: names, phone, platform, nationality
- **Profil actuel**: location, profession, appearance
- **Personnalité**: extracted from conversation analysis
- **Événements notables**: timeline of key exchanges
- **Recherche en ligne**: table of platforms searched + results (include count of queries per platform)
- **Photo**: include profile pic via MEDIA: tag
- **Verdict**: what was found vs what remains unknown
- **Escalation suggestions**: what the user can provide to unlock next steps (surname, social handle, screenshot of dating profile)

## Pitfalls
- **CRITICAL — Message attribution before profile building**: When the Beeper API returns only incoming messages (`isOutgoing: false` across all messages), you're missing the user's side of the conversation. The contact's messages often quote or respond to what the user said, making it easy to misattribute the USER's statements (hometown, studies, profession) to the CONTACT. Example: "J'ai grandi a Lyon! Et toi alors?" could be from EITHER party. BEFORE building a profile, verify direction: if all messages are incoming, assume nothing — the contact's 'responses' may actually be their questions. Cross-reference with what you KNOW about the user, and flag uncertain claims. **Lesson learned 2026-05-22**: I mixed up Monsieur's facts (Lyon, medicine) with Marika's (Montpellier, marketing) because all messages appeared as incoming. Always ask: "Is this the contact speaking, or the user?"
- **Low digital footprint**: Many people (especially expats in Asia) have minimal online presence. Don't be surprised if searches return nothing.
- **Name ambiguity**: "Marika" or "Elissa" alone won't find anyone. Need surname + city + profession combos.
- **Profile pictures can be misleading**: Someone using a photo from 5 years ago, or a photo of someone else entirely.
- **Don't fabricate**: If you can't find the person's real name, say so. Don't guess or combine partial matches.
- **Privacy awareness**: The user is doing this for their own contacts (dating context). Don't lecture about privacy — just deliver the analysis.
- **Ghost result is intel**: Zero search results across 15+ platforms and 30+ queries IS useful information — it tells you the person has deliberately minimized their digital footprint. Report this.
- **Don't burn 40+ queries on a ghost**: If 10 Brave queries return nothing, STOP. Move to Tier 2 (Facebook public search) or tell the user the limits. The user will get frustrated watching you run query after query with zero results — be upfront about the wall you hit.
- **Google dorking via Camoufox gets CAPTCHA-blocked**: Google detects automated browsing from non-residential IPs (especially cloud servers). Don't waste time on Google dorking through Camoufox — use Brave API instead.
- **Malt.fr/ComeUp search URLs don't work with query params**: `malt.fr/search?q=...` returns 404. Malt requires using the homepage search box. ComeUp's search is via their own search box. Don't construct direct search URLs for these platforms.
