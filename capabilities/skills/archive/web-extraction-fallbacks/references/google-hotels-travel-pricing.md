# Google Hotels — Travel Pricing Research via browser_navigate

## When to Use

When researching hotel/accommodation pricing for specific future dates and:
- `web_search` is rate-limited (Brave 429)
- Agoda/Booking.com pages fail to render useful content via `browser_navigate` (heavy JS SPAs)
- Scrapling stealthy_fetch times out on OTA search results
- You need actual per-night pricing for a date range, not "from" rates

**Google Hotels is a lighter aggregator that renders well in browser_navigate** and returns concrete pricing data for specific date ranges.

## URL Pattern

```
https://www.google.com/travel/hotels?q=<destination+keywords>&check_in=YYYY-MM-DD&check_out=YYYY-MM-DD&adults=N&curr=THB&gl=TH&hl=en
```

### Parameters

| Param | Example | Notes |
|-------|---------|-------|
| `q` | `Koh+Samet+beachfront+bungalow` | Search terms; supports natural language |
| `check_in` | `2026-08-17` | ISO date format |
| `check_out` | `2026-08-21` | ISO date format |
| `adults` | `2` | Number of guests |
| `curr` | `THB` | Currency code (THB, USD, EUR, etc.) |
| `gl` | `TH` | Country code for localized results |
| `hl` | `en` or `fr` | Language for UI |

## What You Get

After `browser_navigate` + `browser_snapshot(full=true)`, the snapshot contains property listings with:
- Property name
- Per-night price in the target currency (e.g., `THB 1,010`)
- Source OTA (Agoda, Booking.com, Trip.com, Skyscanner, Official Site)
- Star rating, review count, and average rating
- Amenity tags (Beach access, Pool, Kid-friendly, etc.)
- Sometimes: "Sponsored" markers, "GREAT DEAL" badges

## Extraction Pattern

```python
# After browser_navigate + read_file on the snapshot
# Properties appear as lines like:
# "Sunrise Villas Seaview"
# "THB 1,010"
# " Agoda"
# "4.3/5"
# "(296)"

# Parse with regex:
import re
pattern = r'([A-Z][^\n]+?)\nTHB\s*([\d,]+)\n\s*(Agoda|Booking\.com|Trip\.com|Skyscanner|Official Site)'
```

## Limitations

1. **"Beach access" ≠ "Beachfront"**: Google Hotels uses "Beach access" as a broad amenity tag that can mean anything from "directly on the sand" to "500m from the beach." You MUST verify beachfront status from the property's own description on TripAdvisor/Booking.com/official site. Many properties tagged "Beach access" are set back from the beach.

2. **Pricing may be indicative**: The price shown is the best available rate from one OTA for the date range. Different room types may have different prices. The same property may appear multiple times with different prices from different OTAs.

3. **Google Hotels may not list all properties**: Smaller guesthouses and independent bungalows may not appear.

4. **Future dates work**: Google Hotels accepts dates far in advance (tested: August 2026 searched in August 2026). OTAs often show "no availability" for distant dates; Google Hotels aggregates what's available.

5. **Snapshot is large**: The full snapshot can be 1000+ lines. Use `read_file` with pagination or grep the file directly.

## Complementary Sources

After identifying candidates via Google Hotels, verify details from:
- **TripAdvisor**: Property descriptions often contain precise location info (e.g., "steps from Hat Sai Kaew Beach" vs "beachfront on Ao Phai")
- **Official sites**: Confirm amenities (AC, bungalow type) and get direct booking
- **Booking.com / Agoda**: Room-type-level pricing and availability

## Real-World Example

This technique was validated on 2026-08-03 searching for August 2026 Koh Samet accommodations:
- Google Hotels returned 12+ properties with concrete THB pricing
- Agoda and Booking.com direct searches failed (JS-rendered pages, timeouts)
- Identified Sea Breeze Bungalow at THB 500/night (beachfront, AC, Ao Phai) — a property that didn't appear in web_search results
- Distinguished true beachfront from "beach access" properties by cross-referencing TripAdvisor descriptions
