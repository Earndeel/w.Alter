---
name: camoufox-social-scrape
description: Scrape social media profiles (X/Twitter, Facebook, Instagram) via Camoufox browser API when API credentials are unavailable. Also covers multi-platform OSINT people search — finding a person's real name, profiles, and digital footprint from partial information.
tags: [camoufox, twitter, scraping, social-media, fallback, osint, people-search]
related_skills: [contact-intelligence-systems, web-service-browser]
---

# Camoufox Social Scrape + OSINT

Fallback for scraping social media when official APIs aren't available. Uses Camoufox's local browser API (port 9377) to navigate profiles and extract content from the accessibility tree. Also covers multi-platform people search (OSINT) to identify a person from partial info (name, phone, city, profession, physical traits).

## Always-on rules

Use Camoufox when X/Twitter API credentials are not configured, for read-only scraping of public profiles, or when you need visual content alongside text. Camoufox must be running on `localhost:9378`; check `GET /health` and expect `{"ok": true}`. No social media API keys are needed. For cookie-based authenticated browsing, see the `web-service-browser` skill. X uses virtual scrolling: only visible posts are in the DOM, and snapshots capture instantaneous state, so use cumulative extraction across scrolls. The scroll API frequently times out at the default 10s; use JS evaluate instead, with bare expressions such as `window.scrollBy(0, 2000)`. Text-only scraping misses critical information in images; extract page images and use `vision_analyze` with focused questions. Always close tabs after scraping to save RAM. Public profiles only; login-gated content needs session cookies. Never connect Scrapling/Playwright to Mac Brave CDP (port 9226); use Camoufox or Webtop Chromium. If 10 Brave queries return nothing, stop and move to Tier 2. Facebook public search works without login and should be your first browser-based search. Google Lens is blocked; use Yandex for reverse image search instead. Search by identity, activity, and location, then visually cross-reference physical descriptions. Verify location, profession/activity, and connections/context before adding a Facebook profile to Kardex. Do not stop at the first promising match; exhaust all leads before presenting results. Persist identified people to the Kardex PostgreSQL schema.

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

## References (read with skill_read(name, file_path=...))

- `references/api-key-extraction.md` — Read when extracting masked API keys from dashboards via screenshots and vision analysis.
- `references/brave-cookie-extraction.md` — Read when authenticated Facebook, Instagram, or LinkedIn sessions must be extracted from Mac Brave and injected into Camoufox.
- `references/instagram-deep-extraction.md` — Read when extracting Instagram profile information without login using Google, StarNgage, and Google Images.
- `references/localstorage-extraction.md` — Read when extracting SPA authentication data from browser LevelDB local storage.
- `references/osint-image-search-methodology.md` — Read when conducting visual people searches, comparing image results, or following the OSINT search funnel and its pitfalls.
- `references/osint-professional-platform-crossref.md` — Read when cross-referencing a discovered identity across Codeur, Malt, LinkedIn, and other professional platforms.
- `references/reverse-image-search.md` — Read when performing reverse image searches with Yandex, TinEye, or Bing Visual Search.
- `references/tinder-api-osint.md` — Read when a Tinder match exists and profile data, messages, photos, or API evidence can identify the person.
- `references/tinder-api.md` — Read for general Tinder API access, endpoints, authentication, and response handling.
- `references/webtop-nonheadless-browsing.md` — Read when using Webtop non-headless browsing for Google, Bing, image search, or CAPTCHA-sensitive sites.
- `references/x-scraping-patterns.md` — Read when scraping X/Twitter, including scrolling, cumulative extraction, parsing, image analysis, and Telegram delivery.
