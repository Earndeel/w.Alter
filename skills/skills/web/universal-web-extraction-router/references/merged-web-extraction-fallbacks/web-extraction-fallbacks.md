---
name: web-extraction-fallbacks
description: Resilient backend fallbacks and evidence validation after walter_browse selects the web route.
version: 2.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [browser, fallback, network-interception, extraction, resilience, scraping]
    related_skills: [anti-bot-navigation, webtop-authenticated-browsing, headless-screenshot-qa]
---

# Web Extraction Fallbacks

Use this skill when a web page must be extracted reliably across static HTML, JavaScript SPAs, protected sites, authenticated sessions, or unstable browser facades. The goal is evidence-backed structured data, not merely a successful navigation.

## Core rule

Choose the cheapest reliable transport, but switch strategy after evidence of failure. Do not repeat a browser-facade pattern that already lost state. Prefer a single controlled process or a persistent browser session over a chain of unrelated browser-tool calls.

## Routing order

1. **Static HTTP** — use direct HTTP only when the response contains the requested data and no session/JavaScript is required.
2. **Network interception** — for dynamic SPAs and OTAs, capture `fetch`/XHR JSON, GraphQL, embedded state, and relevant request metadata before parsing the DOM.
3. **Persistent browser session** — keep one warm fingerprint/session per domain, bound page concurrency, and retain cookies only inside the browser context that owns them.
4. **Atomic browser fallback** — use one Playwright/Camoufox process for navigation, interaction, DOM extraction, and screenshots when network capture is insufficient.
5. **Authenticated or strict anti-bot route** — use `anti-bot-navigation`, `webtop-authenticated-browsing`, or the appropriate CDP skill. Do not silently copy cookies between incompatible fingerprints.
6. **Visual/manual fallback** — reserve screenshots and manual takeover for challenges or data that cannot be extracted reliably through the previous layers.

## Universal JSON-first network extraction

For a dynamic page, create an `ExtractionSpec` containing expected aliases, required fields, invariants, and output limits. The recorder must not depend on endpoint names. Score each JSON response by field coverage and repeated-record structure, reject large payloads that miss required fields, preserve source paths, aggregate valid responses, and report evidence before conclusions.

This is a universal transport and orchestration pattern, not a universal semantic parser. Require deterministic joins when prices or metadata live in sibling/context objects; a payload-level match is not proof that a value belongs to a record. Add request replay, versioned mapping cache, adaptive per-domain throttling, and explicit GraphQL/protobuf/WebSocket/DOM adapters before declaring production completeness.

### Learned profile index

For repeated site journeys, add a small versioned profile registry keyed by normalized host/path/query shape plus the extraction-schema fingerprint. A fresh profile may move its last validated backend to the front, but it remains only a hint: the shared semantic gate still decides success and every failure must fall through to the generic chain. Persist bounded route/mapping evidence rather than payloads or credentials; use TTL, failure-streak degradation, manual invalidation, atomic locked writes, and a profile cap so the registry stays safe and compact. The complete data contract, storage rules, and verification matrix are in `references/learned-profile-index.md`.

### Walter Browse backend fallback contract

For a known URL that needs structured, endpoint-agnostic extraction, call
`walter_browse` in `mode=auto` and let the façade select Scrapling, Camoufox
Max, or Webtop. Use the stable CLI below only for backend diagnostics,
explicit mode tests, or when the façade is unavailable.
```bash
/root/.hermes/bin/universal-scraper --url 'https://example.com/api/results' \\
  --expected-fields '{"title":["title","headline"],"url":["url","link"]}' \\
  --required-field title --required-field url --mode auto --pretty
```

The router accepts a backend only when a candidate satisfies the requested semantic contract and yields normalized records; HTTP 200, a non-empty JSON body, or a matching field in isolation is not enough. It tries persistent Scrapling capture first, then Camoufox Max only after Scrapling is unusable. Camoufox Max should expose bounded native Playwright response capture through `POST /tab/network-captures`; an injected `add-init-script` fetch/XHR collector is a compatibility fallback for older workers, not the primary interception mechanism. If both routes fail semantically, attempt a real bounded Webtop CDP extraction when a persistent session is configured; only emit a Webtop/CDP recommendation when that connection or extraction is unavailable. Never claim that Webtop succeeded without a real CDP extraction.

The exact response-capture contract, privacy bounds, compatibility behavior, and verification recipe are in `references/universal-router-camoufox-capture.md`.

### Tool selection versus backend selection

When a first-class extraction façade such as ``walter_browse`` is available,
keep two decisions separate:

1. Before invocation, select the façade for a known URL plus a request for
   structured, verifiable data (products, prices, flights, hotels, listings,
   availability, or JSON records). Use the search branch when the URL is
   unknown, and the interactive browser branch for clicking, login, CAPTCHA,
   or visual inspection.
2. After invocation, leave the backend order and escalation to the façade in
   automatic mode. The model should provide the semantic field contract, not
   choose Scrapling, Camoufox, or Webtop directly.

The tool schema should describe trigger conditions, exclusions, parameters,
normal mode, and the meaning of a valid result. Keep backend implementation
details concise; the skill carries the routing policy, while the schema carries
the callable JSON contract. Tool descriptions improve relevance but do not
create hard priority, especially when Hermes defers plugin tools behind
progressive Tool Search. Do not imply that a free-text objective changes
routing unless the implementation actually consumes it.


After one failed or stale browser-tool exchange, move to a single process:

- navigate with a bounded timeout and avoid `networkidle` on streaming/WebSocket pages;
- register response listeners before navigation;
- wait for a meaningful payload or explicit DOM condition, not an arbitrary long sleep;
- extract text, structured state, links, cards, and a screenshot in the same process;
- write a compact local evidence report and inspect the screenshot only after structured extraction;
- close the browser in `finally` and surface errors with URL, stage, and timing.

For ordinary SPAs, plain Playwright is lighter. Use Camoufox or another anti-detection route only when the protection level justifies it.

## Persistent-session rules

- Scope a warm session to a domain and a consistent fingerprint.
- Bound concurrent pages per domain; do not equate “more tabs” with more throughput.
- Keep browser lifetime explicit and close sessions idempotently.
- Capture request method, response path, status, timing, body size, and a request-body hash for diagnostics.
- Never write cookies, authorization headers, or complete sensitive payloads to reports.
- If the persistent-session API differs by library version, inspect the installed API before coding; do not trust a stale skill snippet blindly.

## Evidence and validation gate

A successful navigation is not a successful extraction. Accept a result only when it has:

- a selected payload or a documented DOM fallback;
- required-field satisfaction at the record level where possible;
- extracted records with source paths/provenance;
- deduplication and aggregation rules appropriate to the response stream;
- timing, status, and error information;
- a clear distinction between observed data and inferred context.

When comparing approaches, use identical URLs, query constraints, concurrency, and output contracts. Report wall time and per-request times separately; do not generalize one domain's benchmark to the entire web.

## Travel and accommodation pricing

For live flight or hotel pricing, use `live-flight-search` for the constraint ledger, airport perimeter, date-window scanning, and evidence-backed presentation. Heavy OTA SPAs may expose cleaner data through a network payload or a lighter aggregator; never treat a nearby airport, broad amenity label, or calendar price as the requested itinerary without validating the underlying record.

## Service-update monitoring

For changelogs and provider announcements, distinguish task-generation callbacks from service-update feeds. Inspect the rendered page and its bundle for the data endpoint, verify pagination and timestamps, check standard RSS/Atom paths, and use cursor-based polling only when no push mechanism exists. A provider's internal JSON endpoint is not automatically a documented public API.

## Common pitfalls

- Repeating `browser_navigate`/snapshot calls after the session is demonstrably stale.
- Parsing only rendered DOM when the useful JSON is already in XHR responses.
- Selecting the largest payload or the first field match instead of validating required fields and record co-occurrence.
- Attaching a global price/currency to a record without a deterministic join key.
- Starting one stealth browser per URL when a warm per-domain session is available.
- Waiting for `networkidle` on a page with long-polling, analytics, or WebSockets.
- Claiming completeness from one provider or one successful site probe.
- Reporting conclusions without showing the raw evidence or provenance paths.
- Saving cookies, authorization headers, full request bodies, or credentials in extraction reports.

## Related skills

- `anti-bot-navigation` — choose Camoufox, Brave CDP, or Webtop by protection level.
- `webtop-authenticated-browsing` — authenticated browsing and controlled cookie injection.
- `headless-screenshot-qa` — visual QA for local HTML artifacts.
- `live-flight-search` — live flight constraints, date windows, and price evidence.
- `web-table-extraction` — complete tabular extraction and validation.

## Reference files

- `references/universal-network-extraction.md` — network-first architecture, verified persistent Scrapling session contract, Trip.com probe, benchmark, and production gaps.
- `references/trip-hotel-dom-projection.md` — verified Webtop DOM projection, hydration guard, semantic price/availability normalization, and validation commands.
- `references/google-hotels-travel-pricing.md` — Google Hotels pricing workflow.
- `references/camoufox-max-kie-extraction.md` — Camoufox Max extraction contract.
- `references/known-url-completeness-and-auth.md` — URL preflight and authenticated fallback.
- `references/web-search-rate-limit-fallback.md` — search/extraction fallback patterns.
- `references/changelog-monitoring.md` — endpoint discovery and cursor-based monitoring.
