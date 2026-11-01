# Lot 1 — Signal-aware routing, API discovery, validated downgrade

Implemented and validated 2026-08-11. Zero LLM calls added anywhere in this
layer: every decision is a technical signal, a persisted observation, or the
shared ExtractionSpec scorer.

## Pipeline

```
walter_browse(url, expected_fields, ...)
  │
  ├─ http_probe(url, content_hints=<field aliases>)   ~200ms..1.5s, 0 LLM
  │     reads up to 256KiB (page BODY, not just the head)
  │     signals: status, content_type, is_json, has_scripts, html_ratio,
  │              looks_spa, content_present, challenge, probe_ms, body
  │
  ├─ probe body usable? (no second request, no browser)
  │     • JSON body + meets_spec            → route=probe-http   HTTP_DIRECT_SUCCESS
  │     • HTML body + static_html extraction→ route=static-html  HTML_STATIC_DIRECT
  │        (BeautifulSoup + lxml, repeated-block parsing, field aliases,
  │         currency-anchored price detection; 0 LLM)
  │
  ├─ else normal ladder (cheapest valid first)
  │     replay (learned) → scrapling → camoufox-max → webtop-cdp
  │     ordering is signal-aware:
  │       is_json      → scrapling only
  │       challenge    → camoufox-max first (skip bare HTTP)
  │       looks_spa    → scrapling then camoufox (cheap negative first)
  │       content_present → never label SPA (no browser escalation)
  │
  └─ browser success (camoufox-max / webtop-cdp)
        _discover_api_endpoints: same-site XHR/network JSON candidates whose
        URL differs from the page (top 3 by score)
        → build_replay_template → scrapling.replay_one → scorer
        validated → DOWNGRADE_HTTP, route=api-replay (browser result kept
                    as fallback while validating; warm server context)
        failed    → FALLBACK_BROWSER (original browser result returned)
```

## Traces (observability)

`API_JSON_DIRECT`, `HTTP_DIRECT_SUCCESS`, `HTML_STATIC`, `HTML_STATIC_DIRECT`,
`SPA_DETECTED`, `CHALLENGE_DETECTED`, `HTTP_ATTEMPT`, `XHR_DISCOVERED` (via
candidate provenance), `API_REPLAY_ATTEMPT`, `API_REPLAY_VALIDATED`,
`API_REPLAY_FAILED`, `DOWNGRADE_HTTP`, `FALLBACK_BROWSER`. The probe body is
never serialized in results; only status/content-type/flags/probe_ms.

## profile_index v3

- Routes extended: `replay`, `scrapling`, `camoufox-max`, `webtop-cdp`,
  `api-replay`, `static-html`.
- `observe()` now accepts `api_discovered`, `api_replay_validated`,
  `endpoint_contract`.
- Entries gain `api_discoveries` (up to 8, deduplicated by url+method,
  with `discovered_at` and `validated`) and `api_replay_validated`.
- `preferred_route` returns `api-replay` when a replay template exists AND
  the API discovery was validated → next visit starts directly at the
  learned JSON endpoint (install/upgrade test: 2nd call to a SPA site served
  by a JSON API takes the api-replay/replay path).
- `_ROUTE_NAMES` + `_escalation` mapping updated for all new routes.

## Endpoint memory safety (no secrets in profiles/logs)

- `build_replay_template` refuses credential-like query keys
  (`token|secret|password|...|api_key|access_key|private`), unsafe long
  static values, dynamic path segments, cross-site hosts, non-GET, non-JSON.
- `_endpoint_contract` persists only structural context: url (capped),
  method, content_type, status, matched fields, record count, score, and a
  capped query string for JSON endpoints. No cookies, headers, bodies,
  response content, or authorization material.
- Probe body, replay templates, and raw candidates are internal execution
  state; RoutedResult.summary() never contains them.

## Benchmark (2026-08-11, after fixes)

| Case | Cold | Warm | Route / trace |
|---|---|---|---|
| books.toscrape (static HTML) | ~1.3 s total (probe 1.25 s + extract 0.04 s), 20 records | same, profile hit | `static-html` / HTML_STATIC_DIRECT — was ~45.6 s before (no browser now) |
| dummyjson (direct JSON) | probe 220 ms → 5 records | profile hit | `probe-http` / HTTP_DIRECT_SUCCESS — one request only |
| SPA open (XHR data) | ~0.9 s via learned replay | replay 0.9 s, 5 records | `replay` / learned template |
| SPA cookie-protected | scrapling fallback 0.39 s, 5 records | same | scrapling (replay 401 → FALLBACK_BROWSER) |

## Pitfalls found while building Lot 1

1. **Probe sampling bug**: `http_probe` used to read 2048 bytes — only the
   `<head>` of a static page — which produced `has_scripts=true` +
   `html_ratio=0.05` → false `SPA_DETECTED` on books.toscrape. Fixed by
   reading up to 256 KiB and by `content_present` (field aliases present in
   the body) overriding the SPA label.
2. **Currency regex false positive**: `[A-Z]{3}` matched "ING" inside
   "showing 1" (books.toscrape nav text), polluting price detection. Fixed
   with lookbehind/lookahead: `(?<![A-Za-z0-9])` prefix and `(?![A-Za-z])`
   suffix.
3. **Scrapling `Response.json()` is synchronous** (requests-like) while
   Playwright's is async. `replay_one` awaited a dict → `TypeError: object
   dict can't be used in 'await'`. Added `_resolve_json()` which normalizes
   both shapes. This broke the *existing* replay path (never exercised with
   this Scrapling version) and would have broken the Lot 1 API replay too.
4. **Container ranking in static_html**: sorting containers by a score
   heuristic chose tiny blocks (h3) over product blocks; now the extractor
   anchors on currency values, climbs to the innermost ancestor that also
   holds a title, and dedups by subtree — 20/20 records on books.toscrape.
5. **Body size**: probe stores up to 256 KiB in memory briefly for scoring;
   it is never logged or serialized. Do not raise `_PROBE_BODY_BYTES`
   without checking memory and output hygiene.

## Tests

- `test_api_downgrade.py` (8 tests): signal probe (JSON, HTML), API discovery
  isolation, same-URL exclusion, validated downgrade → api-replay, failed
  downgrade → FALLBACK_BROWSER, JSON shortcut, and the non-regression test
  `test_static_html_never_escalates_to_browser` (static HTML satisfies the
  contract from the probe body; camoufox/webtop/scrapling spies must not be
  called and `SPA_DETECTED` must not appear).
- Full suite: 35 tests green + walter-browse plugin 4/4 green.