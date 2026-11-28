# Google Flights / OTA comparison notes

Use this reference when comparing a live Google Flights result with an OTA such as Trip.com.

## Constraint ledger

Canonicalize the search before collecting: origin and destination airport sets, exact departure/return dates, one-way vs round-trip, passenger count and type, cabin, nonstop/max-stops, max duration, baggage, locale, market/geo, currency, and session/account scope. A cache key that omits market, currency, or session can compare different fares by accident.

## Price evidence tiers

Keep these tiers separate:

1. **Calendar teaser**: “from” price or date-grid price; discovery only.
2. **Search-result offer**: an offer for the exact date and constraints; suitable for the first comparison.
3. **Checkout/booking quote**: final price after supplier, baggage, payment, and currency conditions; required before purchase.

Never compare a calendar teaser from one platform with a bookable result from another. Report the tier and collection time with every price.

## Cache and reparse policy

Store both the normalized offer and a short-lived raw snapshot (HTML/JSON/RPC response) with `source`, `query_key`, `collected_at`, `expires_at`, `transport`, `session_scope`, and `parser_version`.

- Cache-hit within the freshness TTL: reuse the normalized offer without a new request.
- Parser change while raw data is retained: reparse the raw snapshot; do not refetch solely because the parser changed.
- Expired result, changed constraints, or purchase intent: refetch and verify.
- Final booking check: always use a fresh rendered/session-aware verification, even if the cached result is recent.

SQLite is sufficient for the initial store; raw snapshots should have a shorter retention period than normalized historical prices. Never persist cookies, auth headers, or credentials in the offer cache.

## Transport observations

Google Flights’ `tfs` state is Google-specific; it is useful for a Google adapter, not a cross-platform protocol. Direct HTTP and rendered-browser collection can produce materially different fares for the same visible search (one probe returned 613 EUR over raw HTTP and 354 EUR in the rendered browser). Treat transport, locale, market, and session as evidence fields, and use the rendered/session-aware path for final comparison.

Trip.com’s form generated a `showfarefirst` request for the exact one-way date. A normal headless Playwright request was rejected by WhaleGuard with HTTP 432, while the stealth fetch returned HTTP 200 and exposed exact-result prices (371 EUR, then 373 EUR and 410 EUR). A protection response is not “no availability”; route through the anti-bot fallback and record the transport used.

## Minimum normalized offer

```text
source, query_key, collected_at, price, currency, price_tier,
origin, destination, departure_date, return_date, itinerary,
stops, duration, baggage, supplier, booking_url,
transport, session_scope, parser_version, verification_status
```

For cross-platform reporting, preserve the raw source label and the exact URL alongside normalized fields; parsers are adapters, not interchangeable selectors.
