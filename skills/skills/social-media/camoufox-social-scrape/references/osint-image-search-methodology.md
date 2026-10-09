# OSINT Image Search Methodology

## The Right Search Formula

**Identification + Activity/Profession + Location** — NOT physical traits.

### Why NOT physical traits
Searching "Marika rousse boucle Montpellier" on Bing/Google Images returns:
- Stock photos of random redheads
- Generic "danse orientale" group photos
- Marion Rousse (cyclist) results
- Elden Ring fan art (character named Marika)

The search engine has no concept of "find this specific redhead." It matches on keywords, not visual features.

### Why identity + activity + location works
Searching "Marika danse orientale Montpellier" returns:
- Actual dance school photos with watermarks ("Marika Danse")
- Studio group photos where the target may appear
- Business pages with team photos
- YouTube thumbnails from local dance schools

The search engine excels at finding businesses, professionals, and content by name + profession + location. The target appears in these results as a side effect of being in the industry.

### Visual Cross-Referencing
After getting search results:
1. Screenshot the results page
2. Use `vision_analyze` to examine EVERY photo for physical match
3. Don't just check link titles — the actual images may show the target
4. Check watermarks and source labels for business names / handles
5. Click through promising results to find source URLs

### Query Variations to Try
```
{name} {profession} {city}           # Marika marketing SEO Montpellier
{name} {activity} {city}             # Marika danse orientale Montpellier
{name} {profession} {activity}       # Marika SEO freelance
"{name}" "{profession}" "{city}"     # Exact match (Bing/Google)
{name} {profession} site:linkedin.com
{name} {profession} site:facebook.com
```

### What Each Platform Excels At
- **Google Images**: BEST relevance for professional identity searches. Finds business pages, LinkedIn profiles, agency team photos. Works from non-headless Webtop (not Lens). **When rate-limited (CAPTCHA), bypass with Scrapling stealthy_fetch** (see below).
- **Bing Images**: Less aggressive anti-bot. Good watermark visibility. BUT: worse relevance for French local professional searches. **Bing may show completely different images than Google for the same query** — always try BOTH.
- **Yandex Images**: Best for reverse image search. Works without CAPTCHA. Good for visual similarity.
- **Facebook Public Search**: Best unauthenticated people search. Works without login.

### Scrapling Bypass for Google CAPTCHA
When non-headless Camoufox gets rate-limited by Google (CAPTCHA after 5-8 searches), use Scrapling's stealthy fetcher — it has a different fingerprint and can bypass the block:

```
mcp_scrapling_stealthy_fetch(
    url="https://www.google.com/search?q=Marika+marketing+SEO+Montpellier&udm=2",
    solve_cloudflare=True,
    extraction_type="text"
)
```

The text output contains image source labels (e.g., "Digital Bliss — A propos", "LinkedIn — Marika Seo") that identify which websites the images come from. These labels are often MORE informative than Bing's equivalents.

For actual screenshots (needed for visual cross-referencing), open a Scrapling stealthy session:
```
mcp_scrapling_open_session(session_type="stealthy", solve_cloudflare=True)
mcp_scrapling_screenshot(session_id=..., url="https://www.google.com/search?q=...&udm=2", wait=5000)
```

### URL Slug Analysis — Hidden Identity Gold
When Google/Bing image results link to profile or about pages, **the URL slug often contains the person's full name** even when the page title doesn't show it. Always extract and parse URLs from search results.

**Real example**: Google Images for "Marika marketing SEO Montpellier" returned a link titled "A propos — Digital Bliss" from `digitalbliss.fr`. The URL was:
```
https://www.digitalbliss.fr/a-propos-marieke-moliner
```
The slug `marieke-moliner` revealed the full name **Marieke Moliner** — and the page itself confirmed "Hello, je suis Marika !" (she goes by Marika, a nickname for Marieke).

**Technique**: Use Scrapling to extract `<a href>` attributes from Google results:
```
mcp_scrapling_stealthy_fetch(
    css_selector="a[href]",
    extraction_type="html",
    url="https://www.google.com/search?q=...&udm=2"
)
# Parse href attributes for /a-propos-*, /about-*, /team-* patterns
```

### Google Images vs Bing Images — Try Both
Google and Bing return substantially different image results for the same query. The target may appear in one but not the other. **Always try Google Images first** (better relevance), then Bing as fallback. If Google is CAPTCHA'd, use Scrapling bypass before falling back to Bing.

**Real example**: "Marika marketing SEO Montpellier"
- Bing Images: showed Léa (SEO consultant), Kisytech illustration, generic agency stock photos — NO match
- Google Images (via Scrapling): showed Digital Bliss (red/auburn curly hair woman), LinkedIn profiles, marikaseo.com — MATCH found at Digital Bliss

### Community Cross-Reference — Finding Handles via Related Accounts

When a direct name search fails, find the person through their COMMUNITY:

1. **Search for events/festivals** they participate in (e.g., "Oriental Marathon Festival Montpellier")
2. **Find community leaders' posts** that tag or mention members (e.g., Yaël Zarca's Facebook post: "Marika Palma de Montpellier")
3. **Check association member lists** (e.g., Passion de Scène on montpellier.fr Antigone des associations)
4. **Search for competition/festival lineups** — performers are often listed by name

**Real example flow:**
- Bing Images "Marika danse orientale Montpellier" → watermark "Marika Danse" on group photo → source label "Passion de Scène"
- Google "Yaël Zarca Marika Oriental Marathon Festival" → Facebook post: "Marika Palma de Montpellier"
- Google "Marika Palma Montpellier danse orientale" → Instagram @marika.palma (3.8K followers)
- StarNgage @marika.palma → "Founder of @maisonsantal" → CONFIRMED same person as Marika Moliner

The community's public posts often reveal handles that the person's own private profile does not.

### Real Example: Watermark → Instagram → Identity Confirmation
Query: "Marika danse orientale Montpellier" on Bing Images.
Result: Group photo from a dance studio. Watermark reads "Marika Danse". Source label: "Antigone des associations — Passion de Scène" (Montpellier belly dance association).
Searching "Marika Palma Montpellier danse orientale" (name found via Yaël Zarca Facebook post: "Marika Palma de Montpellier — Oriental Marathon Festival") led to Instagram @marika.palma (3.8K followers).
**StarNgage** analytics for @marika.palma showed bio: *"Bellydance Paris & Montpellier — Founder of @maisonsantal — Digital Marketing VA — Currently Bkk"*
"@maisonsantal" = Maison Santal = the e-shop founded by Marika Moliner (the marketing freelancer found via Google Images) → **PROOF that Marika Palma (dancer) = Marika Moliner (marketing freelancer)**.
Lesson: Watermarks in image results are branding clues. Cross-reference multiple search queries to find social handles. Use StarNgage to read Instagram bios without login.
