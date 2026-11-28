---
name: research-evidence-operations
description: Use for live research prices, dates, and constraint claims.
tags: [research, evidence, availability, flights, comparison, constraints]
metadata:
  hermes:
    tags: [research, evidence, availability, flights, comparison, constraints]
---

# Research Evidence Operations

Use this umbrella for current prices, date-specific availability, live flight searches, ranked shortlists, and any research claim that can change after retrieval.

## Constraint ledger

Freeze the date/window, party size, currency, budget, transport scope, hard constraints, preferences, and ranking objective before searching. Resolve only the highest-impact missing input; make provisional date interpretations explicit instead of silently inventing them.

## Evidence levels

Classify each item as confirmed, live quote, indicative lead, or rejected. Prefer the primary booking/purchase flow, then exact-date OTA/metasearch evidence, then reputable secondary sources. A “from” price, cached result, property-level description, or generic route page cannot prove a room-level price, exact inventory, beachfront access, or a scheduled flight.

Verify hard constraints independently, retain rejected near-matches, and build a matrix with one row per candidate and one column per constraint. Cross-check spatial claims, room features, baggage, stops, airport transfers, visas, taxes, ferry legs, and one-way/return scope rather than hiding compromises in prose.

## Flights and date windows

Scan the requested date window or label a single date as provisional. Discover provider schemas before sending calls, inspect both primary and alternative flight result sets, deduplicate by date/price/duration/airport/flight numbers, and separate ticket economics from ground transfer. Report price, duration, stops, airports, baggage, source timestamp, and the main trade-off.

## API/model pricing

For dynamic model prices, freeze a baseline and keep provider units, resolution bands, input mode, audio, references, taxes, quotas, and reseller/marketing claims separate. Convert only when the source exposes enough formula; label derived values approximate. Distinguish absolute cheapest from cheapest usable for the user's region.

## Verification

Retain source URLs and retrieval time, inspect exact visible state after date/filter interaction, reconcile conflicting prices instead of averaging them, and state plainly when no exact match was confirmed. Never promote a lead into a booking or a generic route into exact-date inventory.

Exact historical comparative-research and live-flight procedures are routed in `references/curator-research-archive-routes.md`.
