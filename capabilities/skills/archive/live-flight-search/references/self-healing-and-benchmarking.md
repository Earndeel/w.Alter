# Flight search: self-healing adapters and fair process benchmarks

## When to use

Use this reference whenever a live-flight comparison includes a direct Google
Flights adapter, an OTA adapter such as Trip.com, or an external oracle such as
SerpAPI. It governs both the search workflow and the recovery path when a site
changes its payload or rendering.

## 1. Compare like with like

A process benchmark must use the same route, date, cabin, passenger count,
stop limit, and maximum duration for every system. Keep these comparisons
separate:

- **Google-house vs SerpAPI Google Flights**: one Google query against one
  SerpAPI `google_flights` query. Measure latency, raw/normalized payload size,
  candidate count, valid-candidate count, and result agreement.
- **House end-to-end vs SerpAPI**: only label this as an end-to-end comparison
  when the house side includes every source being measured. If the house side
  also queries Trip.com, SerpAPI Google Flights is not a Trip.com comparison;
  it is a narrower Google inventory query.
- **Coverage/value**: report separate-source discoveries (for example, an OTA
  price absent from Google Flights) as coverage gains, not as proof that one
  parser is faster.

Always report the number of calls and the stage breakdown. A full house
pipeline can be slower than a single managed API while its Google adapter is
still faster than that API; do not collapse those facts into one ratio.

## 2. Self-healing mapping loop

When an adapter stops extracting results, classify the failure before changing
a mapping:

1. **Transport/access**: timeout, 403/429, CAPTCHA, empty shell, or failed
   browser session. A mapping loop cannot repair access. Apply bounded
   backoff, refresh the session, and route through the configured browser
   hierarchy (Scrapling, then Camoufox, then Brave/Webtop).
2. **Schema/parser drift**: the page/payload is reachable but expected fields
   disappear or violate invariants. Preserve the raw HTML/JSON/network payload
   and the last known-good fixture; do not discard the evidence.
3. **Constraint failure**: data was extracted but date, origin, destination,
   price, duration, currency, or stop count is implausible. Treat it as a
   parser failure until validated, never as a cheap flight.

For parser drift, run a bounded candidate-mapping search over semantic DOM
attributes, stable structural paths, JSON paths, or protobuf field hypotheses.
Score candidates against fixtures and invariants:

- requested origin/destination and departure date match;
- price is a plausible positive fare in the requested currency;
- total duration is within the requested limit;
- stop count and segment sequence are coherent;
- multiple cards agree on the same field interpretation.

Version the mapping, promote it only after several independent fixtures pass,
and retain the previous mapping for immediate rollback. A single successful
page is not sufficient to auto-promote a new mapping.

For Google `tfs`, treat the encoded request builder and the rendered result
mapping as separate components: a valid `tfs` request does not prove that the
result parser is current, and a blocked browser does not prove that the
protobuf mapping is wrong.

## 3. Observable orchestration

Long searches must be staged and observable:

1. freeze the constraint ledger and query matrix;
2. run the fast Google scan and checkpoint each query;
3. run OTA verification with bounded concurrency, per-query timeout, and a
   failure record;
4. normalize and rank only validated candidates;
5. run any external oracle comparison as a separate explicit stage.

Do not run an opaque sequential browser batch or an unbounded parallel browser
batch. If a stage exceeds its timeout or exits unexpectedly, emit the partial
report and continue with the unaffected sources. Never wait silently for a
background runner; surface stage, query, status, and fallback immediately.

## 4. Source roles and fallback policy

Use the direct Google adapter as the primary Google scanner when it is healthy.
Use Trip.com as a separate OTA source when inventory or price coverage matters.
An external Google Flights API is an optional oracle, regression check, or
emergency access fallback—not a substitute for Trip.com coverage and not an
automatic first choice merely because it is managed.

If the user asks for a comparison, do not silently substitute the external API
for a source-specific adapter. State exactly which inventory each process
searched and whether a result is a Google quote, an OTA quote, or a booking
option surfaced by Google.

## 5. Cache and token accounting

Cache raw source responses and normalized records per query key, but send the
model only compact validated records. Track raw bytes, normalized bytes,
request count, cache hits, elapsed time, and failures. Do not use a raw-page
minimum as the fare: calendars, arrival-day markers, widgets, and unrelated
prices must be excluded by card-level parsing and constraint validation.
