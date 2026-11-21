# Lot 3 — Web Memory / Site Capabilities / Virtual APIs

Implemented and validated 2026-08-11. Walter Browse learns how each site
works (KNOWLEDGE) and what it can do there (CAPABILITIES), separates that
from fetched data (CACHE), and reuses proven journeys as local virtual APIs —
zero LLM added to routing or execution.

## Knowledge vs Data (separation)

- KNOWLEDGE → `profiles.json` (ProfileIndex v4): routes, endpoints, replay
  templates, schema drift, capabilities, recipes, domain aggregates.
- DATA → `result_cache.json` (ResultCache): fetched records, source URL,
  timestamp, content hash, TTL, request params, capability used.
Physically separate files. Knowledge outlives data; dynamic data (prices,
stock, availability, flights, sport) gets a short TTL (60 s default for
dynamic capabilities, 300 s otherwise).

## Architecture

```
request
  → CapabilityEngine.execute(host, capability, inputs)
     1. lookup_capability()              (ProfileIndex, no LLM)
     2. cache.get() → fresh?             → records, 0 network (DATA reuse)
     3. router_url_from_implementation() → {{key}} slots rendered from inputs
     4. router.extract_one(...)          → learned recipe (API replay / route)
     5. observe_capability()             → confidence, latency, success/fail
     6. success → cache.put()            → next call instant
     7. failure → generic Walter Browse  → rediscovery
     8. generic success → bump_capability_version() → recipe repaired (v+1)
```

Auto-learning (zero LLM): every successful extraction calls
`_learn_capability_on_success()`; a capability is created only when the
journey is an identifiable operation (`capability_name_from_spec`: spec name
or path token matching search/find/list/lookup/detail/availability/
invoice/transaction/products/flight/hotel/price/status) AND the profile has
≥2 successes. Plain page fetches never become capabilities (by design).

`parameterize_url_slots()` converts dynamic query values (`q`, `limit`,
dates, ids...) into `{{key}}` slots at learning time; execution drops
unfilled slots (missing input → fall back to generic rather than corrupting
the request). Sensitive query keys are never stored.

## Files

- `profile_index.py` — INDEX_VERSION 4: `domains` (aggregate per host:
  successes/failures, preferred route, confidence, endpoints sightings,
  requires_js/challenge flags), `capabilities` (per host+name: inputs,
  outputs, implementation recipe, version history ≤3, confidence,
  success/failure counts, latency).
- `result_cache.py` — ResultCache: file-locked data cache with TTL,
  freshness verdict, content hash, param-scoped entries.
- `capability_engine.py` — CapabilityEngine + CapabilityResult:
  fast-path execution, fallback, auto-repair.
- `universal_router.py` — `_learn_capability_on_success()` hook on success
  (probe-http, static-html, and ladder backends), `observe_domain()`
  aggregation; CLI `--capability host/name`, `--capability-inputs JSON`,
  `--no-cache`.
- `test_web_memory.py` — 17 tests: naming, domain aggregation, registry,
  confidence growth/decay/age, version bump, cache round-trip/expiry,
  separation, fast-path/cache, recipe execution, full break→repair cycle.

## Confidence model

`confidence = base + 0.06·min(successes,20) − 0.10·min(failures,10)`,
clamped [0.05, 0.99], decaying with age past 14 days. Status transitions:
`proposed → active (first success) → degraded (2 failures)`; repair resets
failures to 0 and bumps the version. Routing: high confidence → direct
execution; medium → normal probe; low/stale → rediscovery.

## API (CLI)

```bash
# learn (automatic, happens on any 2nd successful visit to an operation URL)
universal-scraper --url "https://site.com/products?q=x" --expected-fields '{"title":["title"]}' ...

# execute a learned capability — virtual API
universal-scraper --capability "site.com/products" --capability-inputs '{"q":"x"}' \
  --expected-fields '{"title":["title"]}' --required-field title --min-records 1

# force fresh (skip cache)
... --capability "site.com/products" --no-cache
```

Python:

```python
engine = CapabilityEngine(router, index=ProfileIndex(), cache=ResultCache())
result = await engine.execute("site.com", "products", {"q": "x"}, spec=spec)
# result.to_dict(): capability/source/route/fresh/cached/elapsed_s/records
```

## Proven behaviour (real runs, 2026-08-11)

Discovery (first visit, JSON API): 0.65–0.68 s / 1 network probe.
Known capability, cold cache: 0.24 s (one replay) .
Known capability, warm cache: 0.0 s network (cached records returned).
Break→repair: capability v1 pointed to a dead endpoint → generic browse
recovered 5 records in 0.24 s → version bumped to v2 (active, history kept).
Cache expiry: expired entry → recipe reused, data re-fetched, cache refilled.
HTML static (books.toscrape): route static-html, 20 records in 0.04 s.
SPA: route replay learned, no capability (plain fetch — by design).

No LLM call participates in lookup, execution, observation, or repair.

## Known limits (by design, for later lots)

- Capability inputs are typed as strings; type coercion is the caller's job.
- Repair keeps only the last 3 versions (regression history, capped).
- Geo-sensitive / session-dependent capabilities are tracked in the domain
  profile but not yet routed on (Lot 2 sessions exist; wiring them into
  capability routing is the next step).
- result cache entries are param-scoped; same inputs ⇒ same bucket.