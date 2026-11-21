# SerpAPI MCP flight-search reference

## Verified provider contract

The SerpAPI MCP endpoint used in the session exposes three tools: `search`, `search_table`, and `search_dashboard`. The useful call path is the `search` tool.

The tool does **not** accept `engine`, `query`, or Google Flights parameters at the top level. Its arguments are wrapped as:

```json
{
  "mode": "compact",
  "params": {
    "engine": "google_flights",
    "departure_id": "BKK",
    "arrival_id": "LYS,CDG,ORY,GVA",
    "type": "2",
    "outbound_date": "2026-08-30",
    "travel_class": "1",
    "adults": "1",
    "currency": "EUR",
    "gl": "fr",
    "hl": "fr",
    "sort_by": "2",
    "stops": "2",
    "max_duration": "1500"
  }
}
```

Discover the live schema before relying on this example:

- `resources/list`
- `resources/read` with `serpapi://engines`
- `resources/read` with `serpapi://engines/google_flights`
- `tools/list` for the wrapper schema

The Google Flights resource documents engine-specific fields. `max_duration` is in minutes. For Google Flights, `stops=2` means zero or one stop (one stop or fewer), not exactly one stop. Keep a final segment count check as the authoritative filter.

## Date-window scan recipe

For a “cheapest late-August” request without exact dates:

1. State the interpretation, e.g. 22–31 August, instead of silently choosing a single date.
2. Query each date, with bounded concurrency (three workers was sufficient in the verified scan).
3. Read both `best_flights` and `other_flights`.
4. Keep only priced itineraries whose segment count is at most two, total duration is at most 1,500 minutes, and final airport is in the allowed airport set.
5. Normalize by date, price, duration, final airport, airlines, flight numbers, and layover airport/duration.
6. Sort by price, then duration; report the observed timestamp and live-price caveat.

A multi-airport query can bias the returned shortlist toward one destination. It is suitable for finding the cheapest allowed endpoint, but do destination-specific searches before claiming that LYS, CDG, or ORY has no qualifying itinerary.

## Transport/authentication quirk

The configured endpoint carries the SerpAPI credential in its path through a secret interpolation. The server works with no `Authorization` header; adding `Authorization: Bearer <same credential>` caused an HTTP 404 during the verified probe. Therefore configure the MCP server as unauthenticated at the transport layer while keeping the path credential in the secret store. Never print the resolved URL or credential in logs or responses.

The endpoint may answer the MCP initialize/tools calls without returning an `MCP-Session-Id`; the verified provider behaved statelessly. Do not fail a probe solely because that header is absent if independent `tools/list` and `tools/call` requests succeed.

## Reporting checklist

For each candidate, include:

- departure date and price/currency;
- final airport and the separate ground-transfer implication;
- number of stops and total duration;
- airlines and layover airport/duration;
- baggage/ticketing/transit-visa items still unverified.

For a Lyon search, Geneva is a plausible alternate only when Monsieur accepts a ground transfer. Paris CDG/ORY should be labelled as Paris plus onward rail, not as Lyon arrival.
