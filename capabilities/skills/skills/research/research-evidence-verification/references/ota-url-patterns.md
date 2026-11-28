# OTA URL Patterns & Interaction Pitfalls
Last updated: 2026-08-03 (Koh Samet verification session)

## Booking.com

### Direct Hotel Page (dates pre-selected)
```
https://www.booking.com/hotel/th/<slug>.html?checkin=YYYY-MM-DD;checkout=YYYY-MM-DD;group_adults=N;no_rooms=N
```
- Dates populate correctly in URL params — the search bar shows them pre-filled.
- The page may show a sign-in popup overlay. Press Escape to dismiss.
- To see room types/prices, click "Check availability" or "Info & prices" tab.
- **Pitfall**: `wait_until: load` causes 60s+ timeouts (too many resources). Use `wait_until: domcontentloaded`.
- **Scrapling**: `stealthy_fetch` with `solve_cloudflare: true` works for initial page load but room/price data is JS-rendered.
- **No-availability signal**: The page shows "We have no availability here between [dates]" in the DOM even when rooms aren't showing. Search snapshot for `no availability` to confirm.

### Search Results Page
```
https://www.booking.com/searchresults.html?ss=<destination>&checkin=YYYY-MM-DD&checkout=YYYY-MM-DD&group_adults=N&no_rooms=N
```
- Simpler than individual hotel pages but still JS-heavy.
- Camoufox browser navigates OK initially but may return 500 errors on subsequent navigations.

## Agoda

### Individual Hotel Page
```
https://www.agoda.com/<slug>/hotel/koh-samet-th.html?checkIn=YYYY-MM-DD&checkOut=YYYY-MM-DD&adults=N&rooms=N
```
- **Pitfall**: URL date params do NOT auto-select dates in the calendar widget. The page shows the calendar but no dates are pre-filled. User interaction (clicking dates) is required.
- Scrapling `stealthy_fetch` works for initial page load (200 OK) but the calendar interaction needs browser clicks.

### Search Results Page (easier target)
```
https://www.agoda.com/search?checkIn=YYYY-MM-DD&checkOut=YYYY-MM-DD&adults=N&rooms=N&city=<city_id>
```
- City ID for Koh Samet: `17602`
- This page is simpler than individual hotel pages — shows property cards with prices.
- Scrapling `stealthy_fetch` returns 200 OK with hotel listings. Prices appear in the response but may be in JSON/JS payloads.

## Google Hotels

### Direct Hotel Search
```
https://www.google.com/travel/hotels?q=<hotel+name>&checkin=YYYY-MM-DD&checkout=YYYY-MM-DD&adults=N
```
- Works as a fallback when OTAs block. Shows OTA price comparison.
- Does NOT always find small/independent properties (Apache Loongdum, Sea Breeze, Tubtim were all missing from Google Hotels results).
- Better for discovering alternatives than verifying specific small hotels.
- Shows "Sponsored·<area> hotels" section with nearby alternatives when the searched hotel isn't indexed.

## Direct Hotel Websites (Thai-specific)

### Common Pitfalls
- **Prices in images**: Many Thai hotels (especially family-run beachfront bungalows) encode their rate tables as JPG/PNG images in the page, not HTML text. `curl` + text extraction will NOT find prices. Need browser screenshot + vision model or OCR.
- **No online booking**: Some properties only show rates/amenities with no booking engine — must contact by phone/email.
- **Grav CMS sites** (e.g., Tubtim Resort): Clean HTML but prices in images. Look for `<img>` tags in `/user/pages/` directory for photos and potential price tables.

### What you CAN extract from direct sites via curl
- Room type names (Fan vs Air Condition)
- Policies (extra bed cost, breakfast included or not, deposit requirements)
- Amenities listed in text (AC yes/no, WiFi, TV, fridge)
- Location description (beachfront, garden view, sea view)
- Contact information (phone, email)

## Tool Preference Order for OTA Verification

1. **Camoufox browser** (`browser_navigate` + `browser_vision` + `browser_snapshot`) — Interactive JS-heavy pages. Best for date selection and room type browsing. May return 500 after first navigation; refresh session if needed.
2. **Scrapling stealthy_fetch** — Good for Agoda search results and Google Hotels. Use `solve_cloudflare: true`, `wait_until: domcontentloaded`. Avoid `wait_until: load` for Booking.com.
3. **Scrapling fetch** (regular, with CSS selectors) — Faster but less stealthy. Works for simpler sites.
4. **curl** — Direct hotel websites, blog reviews, Travelfish, TripAdvisor (often blocked). Good for extracting policies and text-based info.
5. **web_search** — Use for finding URLs, review snippets, and historical price references. NOT for real-time OTA pricing.
6. **web_extract** — Only works if extract_backend is configured (Firecrawl, Tavily, etc.). Does NOT work with Brave Search backend alone.

## Session Evidence

From 2026-08-03 Koh Samet verification:
- Apache Loongdum: Booking.com confirmed NO availability via snapshot ("no availability" ×7 in DOM)
- Tubtim Resort: curl confirmed two room types (Fan/AC), extra bed policies, beachfront. Prices in images only.
- Sea Breeze Bungalow: TripAdvisor 2/5 (66 reviews) — quality risk flag. Direct site returned 520 (down).
- Google Hotels: Found Pandora (860 THB) and Samed Hideaway (1,297 THB) but both were non-beachfront.
