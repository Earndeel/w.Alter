# Dynamic OTA verification

Use this reference when an OTA or hotel page exposes prices, dates, filters, room images, or availability through JavaScript.

## Required sequence

1. Run a cheap static/bulk fetch for triage and candidate discovery. Parallelize independent URLs, but do not treat a `202`, empty extraction, search snippet, or partial page as proof of no availability.
2. Open the candidate in a rendered browser session. Inject the target dates and occupancy in the URL when supported, then inspect the rendered form: query parameters are often ignored or reset to the page default.
3. Select check-in and check-out through the visible date picker when necessary. Verify the selected labels after each interaction; capture the actual state, not the intended state.
4. Submit the search and wait for the result section. If the button is inert, the form is a marketing/vitrine page, or the page remains unchanged, classify the price as a property-level lead only.
5. Inspect the room-category result: exact category, occupancy, cancellation/payment, final total and nightly price, taxes/fees, and availability. `From` prices and “approximate price for one night” labels are not booking evidence.
6. Inspect the exact room/category images. A generic property gallery cannot prove air conditioning, sea view, or the room’s position. Pair visual evidence with a room-facilities list and an independent spatial source.
7. Distinguish spatial labels rigorously: `Beachfront`/direct sand is different from `Beach Nearby`, a stated metre distance, a promenade, or an unqualified “sea view.” Verify the shoreline context with maps/satellite and independent reviews.

## Date and price pitfalls

- A page can display the requested calendar month while still using the wrong dates.
- A property page can show “If you’re flexible, these dates are available” with alternative nights; this is evidence about those alternatives, not the requested stay.
- A visible price must be attached to the requested dates, occupancy, room category, and number of nights before it enters the verified ledger.
- Never infer a four-night total from a one-night “from” price, or a nightly price from a total, without an explicit calculation and source state.
- Preserve the failed interaction and missing field in the evidence ledger; do not silently downgrade it to an estimated value.

## Parallel browser discipline

Parallelize independent candidate/source sequences with separate browser sessions where possible. Serialize interactions within one session because date pickers, occupancy controls, and lazy-loaded results share state. When a dynamic source blocks extraction, escalate to a rendered or stealth browser and then to an alternate OTA/direct property page; record the escalation path and its result.

## Minimum evidence row

`candidate | source | captured_at | dates/occupancy confirmed | room_category | availability | total | nightly | taxes/fees | AC | sea_view | direct_sand | image_refs | url | confidence | missing_checks`

A row with any hard field unknown remains `lead`, not `verified`.
