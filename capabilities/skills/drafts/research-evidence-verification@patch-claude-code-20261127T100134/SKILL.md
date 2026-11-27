---
name: research-evidence-verification
description: Use when a research answer depends on exact current prices, availability, schedules or other claims a dynamic page can invalidate: evidence levels (confirmed / live quote / lead / rejected), source hierarchy, reconciliation of conflicting prices, evidence matrix. Specialised procedures (API pricing, provider access, Google Trends, review/UX audits, OTA transport) are in its references.
---

# Research Evidence Verification

Use this skill when a web-research task depends on current prices, date-specific availability, inventory, schedules, or any other claim that can be invalidated by a dynamic page. It complements `comparative-research`: that skill ranks candidates; this one determines what is actually evidenced.

## Core rule

Never promote a lead into a confirmed offer. Every factual claim must carry an evidence level:

- **Confirmed** — the primary booking or purchase flow visibly accepts the exact dates, party size, room/product, and price, with availability shown.
- **Live quote** — a source shows a price for the relevant date window and item, but the final booking step or complete availability cannot be verified.
- **Indicative lead** — an aggregator, editorial page, review, cached result, “from” price, or general range suggests a candidate but does not prove the requested transaction.
- **Rejected** — it fails a hard constraint or the source contradicts the claim.

If dates, party size, room type, currency, taxes, or availability are missing, downgrade the claim rather than filling the gap from context.

## Procedure

1. **Freeze the request as testable constraints.** Write the exact date window, number of nights, guests, currency, ceiling/floor, and binary requirements. Distinguish hard constraints (`directly on sand`, `air conditioning in the room`) from preferences (`quiet`, `sea view`, `short transfer`).
2. **Check the live date.** Use the system/tool date, then state the research date and timezone. Do not silently reinterpret “next week”, “August”, or a flexible window. For flexible dates, test each viable start date or clearly say the source was only checked for one representative interval.
3. **Use the source hierarchy.** Prefer, in order: primary property/vendor booking flow; OTA result with the exact dates; metasearch/Google Hotels as a discovery and price-lead layer; reputable transport aggregators and operator pages; editorial guides/reviews; forums and snippets only as leads. A lower-tier source may support a description, but not a final price or availability claim when a higher-tier source disagrees.
4. **Verify page state after interaction.** Before reading a price, record the visible check-in, checkout, guests, currency, room/product, and selected filters. After a date-picker action, take a fresh snapshot and verify both fields; keyboard navigation can alter checkout while leaving check-in unchanged. Treat a URL parameter as a request, not proof that the page applied it.
5. **Reconcile conflicting prices.** Keep the exact displayed value, source, room/product, dates, and whether it is `from`, nightly, total, tax-inclusive, or a package. If Google Hotels says 500 and the property-facing page says “from 1,440”, report the discrepancy and downgrade the 500 value; do not choose the attractive number. Never mix a general monthly range with an exact-date offer.
6. **Test semantic constraints independently.** `Beachfront`/`on the beach` is not the same as `beach access`, `near beach`, `by the sea`, or `steps from the beach`. `Air-conditioned property` is not proof that the requested room has AC. `Sea view` does not prove direct sand access. Record the exact wording and location distance where available.
7. **Audit transport scope.** Separate one-way from return, scheduled route from exact-date inventory, and operator package from separately purchased legs. State whether ferry, terminal transfers, park fees, local taxis, and baggage are included. A fast route page can still be wrong for the requested date if its calendar remains on the default day.
8. **Cross-check independently.** For each top candidate, seek at least one independent confirmation of the critical constraint and one of the price/date. If a dynamic OTA cannot be read reliably, preserve the candidate as a lead and switch to the primary page, a second OTA, a direct call/contact route, or a transparent no-confirmation statement.
9. **Build an evidence matrix.** Use columns such as `candidate`, `hard constraints`, `price/date evidence`, `transport evidence`, `status`, `confidence`, `failure reason`, and `URL`. Keep rejected near-matches in a separate section so marketing wording cannot silently inflate the shortlist.
10. **Stop honestly.** A useful answer can conclude that no exact match was confirmed. Explain the smallest compromise that makes the search viable: raise the budget, move 50–100 m inland, accept fan-only, extend the trip, or choose a less scenic beach.

## Output format

Lead with the verdict, then separate:

1. **Confirmed / live quotes** — only items with evidence at the appropriate level.
2. **Indicative leads to verify** — useful candidates, explicitly not booked.
3. **Rejected near-matches** — which hard constraint failed.
4. **Transport and hidden-cost note** — one-way/return, ferry, local transfers, fees, and date caveats.
5. **Next verification action** — the single check that would turn the best lead into a decision.

For each candidate, include the exact displayed price and source date, not a smoothed estimate. Keep URLs as plain text or inline code; do not hide them behind marketing labels.

## Pitfalls

- Subagent summaries are reports, not proof: inspect the produced artifact and independently verify the critical source before repeating “confirmed”.
- A page can retain the wrong date after several keyboard operations; never infer the selected date from the last action.
- `from` prices and metasearch snippets are discovery signals, not exact-date inventory.
- A property description can prove beachfront or AC only at property level; room-level evidence is still required.
- Dynamic pages that cannot expose exact state should produce a confidence downgrade, not an invented number.
- If a transport page defaults to today or another date, use it for route structure only and label fares as route-level ranges.
- Do not let one spectacular low price outweigh a contradictory primary-source price.

## Reusable reference

For the dynamic-booking and conflicting-price pattern captured during a Thailand beach search, see `references/evidence-labels-and-dynamic-booking.md`.
For OTA URL parameter formats, tool-specific `wait_until` strategies (Booking.com → domcontentloaded, not load), Thai hotel pricing pitfalls (prices in images, not HTML text), and the tool preference order for OTA verification, see `references/ota-url-patterns.md`.

## Specialised procedures (references)

Read only the one the task needs:

- API / model prices (normalising billing units, resolutions, hidden charges) and provider access (absolute cheapest vs cheapest usable): `references/api-model-pricing-and-access.md`; dated provider snapshots in the other `references/*-pricing*.md` files.
- Google Trends collection and Keyword Planner gaps: `references/google-trends-keyword-planner.md`.
- Customer reviews and UX audits without over-reading the evidence: `references/customer-reviews-ux-audit.md`.
- Constraint ledger, dynamic-OTA protocol, sub-agent reconciliation: `references/constraint-ledger-and-live-availability.md`; Google Flights/OTA transport and price cache: `references/google-ota-transport-and-price-cache.md`.
