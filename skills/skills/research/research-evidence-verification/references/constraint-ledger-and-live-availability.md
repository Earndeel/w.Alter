# Constraint ledger and live-availability verification

Use this reference for multi-candidate lodging, travel, marketplace, or service comparisons where price and availability are date-sensitive.

## 1. Freeze the request before searching

Create one canonical tuple and repeat it in every live search:

- destination / property scope
- check-in and check-out dates
- occupants, rooms, category, currency
- origin and transport assumptions
- hard constraints versus soft preferences
- whether the budget is per night, total, tax-inclusive, or tax-exclusive

For a strict threshold such as `price < 1,500 THB/night`, an offer shown at exactly 1,500 is not compliant. For a four-night stay, calculate the total ceiling with a tool rather than mental arithmetic.

## 2. Evidence states are mutually exclusive

Use a candidate registry with these states:

- **verified**: exact dates/parameters, live availability, price basis, and every hard constraint are supported by a current source; cross-check the critical location/amenity claim independently.
- **lead**: promising signal, but at least one hard field is unknown (usually live availability, exact room category, AC, direct access, or fees). A lead must never be presented as bookable or recommended without an explicit gap label.
- **rejected**: a hard constraint is disproved, or exact availability is disproved. Keep the evidence and rejection reason.

A snippet, monthly “from” price, cached search card, or property amenity page is evidence of a **lead**, not of an exact reservation.

## 3. Dynamic OTA / marketplace protocol

1. Open the property or search page with the canonical dates and occupation encoded in the URL where supported.
2. Inspect the rendered UI, not only extracted HTML. Confirm the date fields and guest count after the page loads; dynamic sites can silently reset them.
3. Read the room card or checkout step. Record category, occupancy, cancellation, taxes/fees, and price basis (night, stay, room, dorm bed).
4. Capture a screenshot or stable DOM text for the critical claim.
5. Cross-check beachfront/direct-access, AC, sea-view, or equivalent physical claims against an independent source (official property page, map/review source, or satellite when available).
6. If an OTA is blocked or JS data is not exposed, preserve the signal as a lead and record the failed verification path. Do not fill the gap with a search snippet or a plausible number.

False cheap results are common: a low card may be a dormitory bed, a different date, a non-AC category, a nearby property, or a price before taxes.

## 4. Sub-agent reconciliation

Sub-agent reports are discovery artifacts, not proof of side effects or live availability. Before using them in the final answer:

- verify every delivered file exists and read it back;
- inspect the exact candidate blocks and source URLs, not only the summary;
- compare independent workstreams for contradictions in dates, units, and status;
- independently re-check the few claims that change the recommendation;
- downgrade a claim when the underlying screenshot, DOM, or direct source is missing.

When one agent says “best candidate” but its own row says “price/dispo unknown,” retain **lead**, not **verified**.

## 5. Transport and total-cost ledger

For door-to-door comparisons, decompose each direction into origin transfer, terminal wait, main leg, ferry/flight, local transfer, and hotel arrival. Mark which segment each price covers. A local songthaew/taxi fare that is merely mentioned in the route must not silently disappear into a supposedly complete total.

Report ranges and confidence levels when sources expose ranges. Keep the flight branch separate: verify the actual airport route and date; “nearest airport” is not evidence of a commercial flight. Compare flight total cost only after adding airport transfers, ferry/road legs, baggage, and schedule friction.

## 6. Final report format

Lead with the verdict: whether any candidate is fully verified. Then provide:

- candidate table: state, exact availability, category, total/night price, fees, cancellation, AC, location/direct-access evidence, sea view, unknowns;
- transport table: route segments, one-way duration, round-trip range, inclusions, confidence;
- explicit rejected candidates and reasons;
- raw URLs in plain text or backticks, never hidden behind Markdown link text when the client renders links poorly;
- capture date/time and tool/source limitations;
- next action that closes the most important unknown (usually direct contact with a precise request).

Do not recommend a candidate while a hard constraint remains unknown. Say “no verified match” when that is the evidence-backed result.
