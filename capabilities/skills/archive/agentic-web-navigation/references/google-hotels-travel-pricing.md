# Google Hotels for Travel Pricing Research

## Why Google Hotels
Google Hotels (`google.com/travel/hotels`) is the most reliable tool for hotel pricing research with specific future dates. Unlike OTAs (Agoda, Booking.com) which use aggressive anti-bot JavaScript, Google Hotels returns actual per-night prices for your exact check-in/check-out dates via the browser.

## URL Pattern
```
https://www.google.com/travel/hotels?q=<destination>&check_in=YYYY-MM-DD&check_out=YYYY-MM-DD&adults=1&curr=THB
```

Add `&max_price=1500` to filter by budget. The "Beach access" amenity filter can be applied via the UI.

## What You Get
- Actual per-night prices for the requested dates (not generic ranges)
- Amenity tags: AC, pool, beach access, Wi-Fi, parking
- Star rating, review count, and score
- These prices are the Google-aggregated listing price — confirm exact taxes/fees via the OTA link

## Limitations
- "Beach access" ≠ "beachfront" (direct sand). Verify independently via Google Maps satellite or TripAdvisor reviews.
- Google Hotels may not show all room types — only the cheapest available.
- Prices are indicative; final total (incl. taxes/fees) requires OTA confirmation.

## When NOT to Use Google Hotels
- For non-hotel accommodations (guesthouses, homestays) it has sparse coverage
- For very remote destinations with few listings
- For last-minute (same-day) bookings — OTAs are more accurate

## Thai-Language Search Strategy
When English web_search hits Brave rate limiting (429), switch to Thai queries:
- ที่พักติดทะเล ราคาถูก = beachfront accommodation cheap
- ห้องแอร์ วิวทะเล = aircon room sea view
- รีวิว 2025 2026 = review 2025 2026

Thai queries consistently return richer local blog content (chiangmaiexpert.com, checkinchill.com, gother.com) and are less affected by rate limits since they hit different result pools.

## OTA Anti-Bot Reality
Agoda and Booking.com both block programmatic access. Do not waste time:
- Blank/empty pages after navigation
- Captcha walls
- 500 errors from the browser bridge
- Scrapling stealthy_fetch also fails (timeout on JS-heavy pages)

TripAdvisor search snippets are the best fallback for independent verification — they confirm beachfront status, AC presence, and price ranges without requiring page loads.
