# Structured preflight flight search

## What was observed

A flight-only preflight engine can reproduce the useful part of a SerpAPI-style search without calling SerpAPI:

- Google Flights accepts a generated `tfs` state in its public travel URL. For the tested one-way shape, `tfs` is URL-safe base64 around a protobuf-like wire message containing the date, origin, destination, stop constraint, and maximum duration.
- A direct HTTP GET of the resulting Google Flights URL returned roughly 2.2–2.3 MB of HTML in the tested locale and included flight cards with accessible `aria-label` text. Those labels exposed the displayed price, carrier, stop count, departure/arrival times, total duration, and layover summary.
- The page contained duplicate accessibility cards; deduplicate on a stable card id when available, otherwise on a normalized label plus route/date/price tuple.
- A small standard-library parser scanned three dates without SerpAPI and recovered 13, 13, and 14 unique cards; it found a 354 EUR, one-stop, 23 h 15 min BKK→GVA candidate on the tested 2026-08-30 snapshot.
- SerpAPI's native REST response exposed the same conceptual layers: generated Google URL, normalized flight JSON, raw response artifact, prettified artifact, and metadata. The MCP server is an adapter, not the flight engine.

## Recommended architecture

1. Accept a canonical `FlightQuery`: origins, destination airport set, date window, passengers, cabin, max stops, max duration, currency and locale.
2. Generate Google Flights query state locally for the supported query shapes, then fetch the public result page with a bounded, polite HTTP fast path.
3. Parse accessibility labels and structured DOM attributes into a canonical itinerary schema. Store `source`, `collected_at`, locale, query parameters, raw URL and parser version.
4. Deduplicate, filter and rank locally. Keep airport transfer estimates as a separate leg instead of mixing them into air duration.
5. Use Playwright/Camoufox/Brave only for shortlisted candidates that need segment detail, baggage rules, booking links, or final-price verification.
6. Retain SerpAPI as a benchmark/fallback while the home parser is being validated; compare by query and timestamp, not by assuming prices are immutable.

## Important limits

- The exact internal SerpAPI implementation is not known; reproduce observable behavior, not proprietary code.
- Google flight prices are live and changed between successive requests in the same session. Every result needs a collection timestamp and a final verification step.
- The `tfs` wire layout must be extended and regression-tested for round trips, multiple airports, cabin/passenger variants, date ranges and advanced filters. Do not guess fields silently.
- HTML labels and DOM classes are presentation surfaces. Prefer semantic attributes and keep a browser fallback when labels disappear or the page is blocked.
- A preflight parser is for discovery and ranking, not proof that a fare, baggage allowance, transit condition or booking token remains available at checkout.

See this file from `agentic-web-navigation/SKILL.md` whenever a live comparison can be split into a cheap structured scan followed by browser verification.
