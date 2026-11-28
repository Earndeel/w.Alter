---
name: live-flight-search
description: Use for live flight searches and date-window comparisons. Covers self-healing adapters and fair process benchmarks; see references/self-healing-and-benchmarking.md.
---

# Live flight search

Use this skill when Monsieur asks for current flight prices, availability, or the simplest/cheapest itinerary across a date window. Produce an evidence-backed shortlist, not a generic route suggestion.

## Operating principles

- Treat flight prices and availability as live, volatile observations. Record the search date, the scanned date window, the source, and the currency.
- Never invent a departure date when availability depends on it. If Monsieur gives a vague period such as “late August”, make the interpretation explicit (for example, 22–31 August) and search that window; ask for correction only after returning a useful provisional result when the request permits it.
- Respect hard constraints before ranking: one-way/return, maximum stops, maximum total duration, departure/arrival airport scope, passenger count, cabin, and baggage assumptions.
- Ask one high-value follow-up question at a time. Use guided intake: resolve the blocker that most changes the search, then run the next search rather than presenting a questionnaire.
- Separate the flight itinerary from the ground transfer. An airport near a city or linked by high-speed rail is an alternative, not the same arrival airport; label the extra time, cost, and operational risk.
- Report trade-offs honestly: cheapest is not automatically simplest, and a short connection or unfamiliar transit airport may be less robust than a slightly more expensive itinerary.

## Standard workflow

1. **Build the constraint ledger.** Capture origin airport(s), destination airport(s), travel direction, date or date window, trip type, passengers, cabin, checked baggage, maximum stops, maximum total duration, acceptable ground-transfer radius, currency, and ranking priority.
2. **Resolve only the critical missing input.** For a live one-way search, the departure date/window is usually the first blocker. Ask a single concise question when it cannot be inferred; otherwise state the assumption and proceed.
3. **Define the airport perimeter.** Start with the requested airport. Add plausible alternatives only when the user explicitly allows accessible airports (for example, Paris with TGV/OUIGO or Geneva with a ground transfer). Do not silently include remote airports whose transfer changes the economics.
4. **Discover the provider schema before calling it.** For SerpAPI MCP, inspect the `search` tool schema and the engine resource instead of guessing parameter placement. The wrapper expects `mode` plus a nested `params` object; Google Flights parameters are engine-specific.
5. **Scan the date window.** Query each candidate departure date (or the provider’s calendar endpoint if available). Use bounded concurrency only when the provider tolerates it; avoid hammering the API. Keep the raw response available long enough to verify the normalized shortlist.
6. **Normalize and filter.** Read both `best_flights` and `other_flights`. Reject itineraries that exceed the stop or duration limit, have an unapproved final airport, or have no usable price. Deduplicate by date, price, duration, final airport, and segment flight numbers; sort by price first when “cheapest” is the goal, then duration.
7. **Validate operational details.** For shortlisted options, check whether the connection is on one ticket, baggage is included, the transfer airport requires a visa or a terminal change, and whether the ground transfer is realistic. Treat these as verification items, not assumptions.
8. **Present a compact shortlist.** Lead with the cheapest qualifying option, then give two or three alternatives with date, price, total duration, stops, airports, airlines, and the main trade-off. State that prices are observed live and can change.
9. **Continue with one question.** Ask the next decision-changing question, usually whether an alternate arrival airport/transfer is acceptable or whether to lock baggage and passenger details.

## SerpAPI MCP quick rules

- Search wrapper: `tools/call` → tool `search` → arguments shaped as `{ "mode": "complete|compact", "params": { ... } }`.
- Google Flights baseline for a one-way economy scan: `engine=google_flights`, `departure_id`, `arrival_id`, `type=2`, `outbound_date`, `travel_class=1`, `adults=1`, `currency`, `gl`, `hl`, `sort_by=2` (price), `stops=2` (zero or one stop), and `max_duration=1500` (25 hours).
- Confirm the exact engine schema through the provider resource before relying on enum semantics or multi-airport syntax. Details and a provider probe are in `references/serpapi-flight-mcp.md`.
- Keep credentials out of commands, logs, reports, and skill content. Use the configured secret reference; never echo the key or paste it into a final answer.

## Common pitfalls

- Searching one arbitrary date and calling it “the cheapest in the month”. Scan the stated window or clearly label the result as provisional.
- Asking a long batch of intake questions before doing an obvious low-risk first scan. Ask one question at a time and keep the conversation moving.
- Treating `stops=2` as exactly one stop without checking the provider’s documented semantics; in Google Flights it means one stop or fewer.
- Filtering only `best_flights`; cheaper qualifying options can be in `other_flights`.
- Comparing an airport ticket price with a Lyon ticket price without adding the ground-transfer burden.
- Claiming that no Lyon/Paris itinerary exists merely because a multi-airport query’s first returned candidates all use another airport. Run destination-specific checks before making an absence claim.
- Presenting a live price as guaranteed or omitting baggage, self-transfer, transit-visa, and connection-risk caveats.
