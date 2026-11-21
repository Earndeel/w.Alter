# Universal network-first extraction

Use this reference for dynamic sites where the useful data is delivered through `fetch`/XHR/GraphQL responses rather than stable DOM markup.

## Validated architecture

Separate the system into four layers:

1. **Orchestrator** — receives a URL plus an `ExtractionSpec` containing expected fields, aliases, required fields, invariants, and output limits.
2. **Browser/session layer** — maintains one warm browser fingerprint per target domain, with bounded page concurrency and explicit shutdown.
3. **Network recorder and candidate scorer** — listens to `fetch`/XHR responses, parses JSON, scores payloads by field coverage and repeated-record structure, and rejects large partial payloads that miss required fields.
4. **Normalizer/validator** — extracts repeated objects, preserves source paths and provenance, aggregates valid responses from one page, removes duplicate retries, and reports evidence before conclusions.

Do not make the recorder depend on endpoint names. Endpoint names are useful evidence after capture, not routing prerequisites.

## Scrapling session contract

For Scrapling 0.4.7, the verified persistent browser API is:

```python
from scrapling.fetchers import AsyncStealthySession

session = AsyncStealthySession(headless=True, max_pages=3)
await session.start()
try:
    response = await session.fetch(url, page_setup=page_setup, page_action=page_action)
finally:
    await session.close()
```

Do not rely on `StealthyFetcher.session()` without checking the installed version; that method was not present in the verified runtime. Keep one session per domain/fingerprint, not one fresh stealth browser per URL.

## Candidate-selection rules

- A payload is not valid merely because it is large or contains `price`.
- `required_fields` must be satisfied before early-returning or aggregating a candidate.
- Prefer record-level co-occurrence over payload-level matches. If a value is found only in a sibling/context object, preserve its path as context and require a deterministic join key before treating it as final production data.
- Aggregate multiple valid responses from the same page; some SPAs emit one result per response.
- Keep request method, response path, status, timing, body size, and a request-body hash for evidence. Do not write cookies, authorization headers, or complete sensitive payloads into reports.

## Verified Trip.com probe

A live probe on three concurrent searches discovered, without hardcoding the endpoint in the recorder:

- endpoint: `POST /restapi/soa2/27015/FlightMiddleSearch`
- structure: `journeyList`
- output: five aggregated records per search
- persistent-session wall time: 66.82 s
- fresh-session comparison: 89.98 s
- measured improvement: 25.74% for that run only; do not generalize the number to other domains.

The report was checked for `cookie`, `authorization`, and `set-cookie` strings before delivery.

## Production gaps to close

Before calling the engine universal in production, add:

- deterministic provenance and joins for prices/metadata outside the repeated record;
- request replay in the same warm page/context and a durable, versioned mapping cache;
- a long-lived browser worker if persistence must survive process boundaries;
- adaptive per-domain rate limiting, block detection, and session recovery;
- parsers for GraphQL, protobuf/WebSocket, embedded state, and a true DOM fallback;
- cross-target integration probes (OTA, search, social) rather than extrapolating from one Trip.com success.

## Evidence standard

A successful navigation is not a successful extraction. Require all of: a selected payload, required-field satisfaction, extracted records, source paths/provenance, and a recorded timing/error outcome. When comparing implementations, run the same URLs and concurrency with the same output contract; report wall time and per-request times separately.
