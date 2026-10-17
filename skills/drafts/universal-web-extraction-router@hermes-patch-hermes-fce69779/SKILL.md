---
name: universal-web-extraction-router
category: research
description: 'Use for all public web requests; call walter_browse first for any web need, search to extraction.'
---

# Universal Web Extraction Router

Use this skill for public web requests. It is the sole model-facing routing
policy for web search, known-URL extraction, monitoring, and scraping.

Classify the request before selecting a tool:

- **Known URL + structured fields**: call `walter_browse` with the semantic
  contract.
- **No known URL or open-ended freshness**: use `web_search` first; when a
  result must be extracted structurally, pass its URL to `walter_browse`.
- **Multiple URLs or a crawl**: use Scrapling bulk/spider operations directly.
- **Interaction, authentication, CAPTCHA, or visual inspection**: use the
  browser/Camoufox/Webtop branch directly.

The tool-facing extraction path is Walter Browse; backend selection remains
internal to the tool. This skill is not a second scraper implementation.

## Routing contract

1. **Walter Browse first**: for a known URL and a structured extraction request,
   call `walter_browse` with the semantic field contract. Do not select
   Scrapling, Camoufox, or Webtop manually for normal single-URL extraction.
2. **Signal-aware probe (Lot 1)**: in `auto` mode the router first issues a
   cheap GET probe (`http_probe`) that reads up to 256 KiB — enough to judge
   the page body, not just its `<head>`. It derives technical signals with
   zero LLM calls: HTTP status, content type, JSON-vs-HTML, script presence,
   visible-text ratio, challenge detection (403/429/503, Cloudflare markers),
   and `content_present` (the requested field aliases actually occur in the
   static body).

   The probe body is then used directly when possible (no second request):
   - **direct JSON** (`content-type: application/json` or body starts like
     JSON): scored straight from the probe body. If the ExtractionSpec is
     satisfied → `route=probe-http`, trace `HTTP_DIRECT_SUCCESS`.
   - **static HTML with recoverable content**: the `static_html` extractor
     (BeautifulSoup/lxml, no LLM) parses repeated product-like blocks from the
     probe body. If the semantic contract passes →
     `route=static-html`, trace `HTML_STATIC_DIRECT`. This is the absolute
     fast path: books.toscrape went from ~45.6 s (browser escalation) to
     ~1.3 s (single HTTP GET, no browser, 20 records).
   - **content_present disables the SPA label** for the routing decision: a
     page whose requested data is already in the HTML must never escalate to
     a browser on a SPA heuristic.

3. **Internal lightest-path selection**: if the probe body cannot satisfy the
   contract, Walter Browse tries a validated learned replay when available,
   then the Scrapling network/XHR capture path. If that result is empty or
   fails the semantic field contract, it escalates to the Camoufox Max HTTP
   API at `http://127.0.0.1:9377`, whose bounded fetch/XHR collector feeds the
   same scorer.
4. **API discovery + validated HTTP replay downgrade (Lot 1)**: after a
   successful browser backend (camoufox-max, webtop-cdp), the router inspects
   the captured candidates for same-site XHR/network JSON endpoints whose URL
   differs from the page (`_discover_api_endpoints`). The best endpoint is
   replayed over plain HTTP through `scrapling.replay_one`, then validated by
   the same ExtractionSpec scorer:
   - `API_REPLAY_VALIDATED` → `DOWNGRADE_HTTP`, `route=api-replay`; the result
     is returned directly and the endpoint contract is persisted.
   - `API_REPLAY_FAILED` → `FALLBACK_BROWSER`; the original browser result is
     kept (reversible downgrade, no task breakage). The browser/context stays
     warm (persistent Camoufox Max server) while the replay is validated.
5. **Webtop CDP fallback**: if the lighter paths fail semantically, Walter Browse
   connects to the persistent Webtop Chromium session (normally port 9223,
   with a host-local 9222 fallback), captures JSON responses, and uses a bounded
   DOM projection only for an explicit site profile. A route is marked
   successful only when the shared field/record contract passes.
6. **Final escalation**: if Webtop also fails, return
   `escalation.recommended_backend=brave-mac-cdp` rather than fabricating data.

Before the normal chain, consult the persistent learned profile index when one
exists. It is keyed by the value-free URL scope plus the extraction schema
signature. A fresh validated route may be tried first, but it is only a hint:
the shared semantic gate remains authoritative and failures fall through to the
normal chain. Entries older than seven days are diagnostic only; two
consecutive failures degrade an entry until a later valid extraction repairs
it. The index lives at
`$HERMES_HOME/cache/universal-web-extraction/profiles.json` and stores route
metadata, not payloads, cookies, authorization headers, or raw request bodies.

A HTTP 200 is not success. A route is usable only when at least one candidate
contains all required fields and produces one or more normalized records.
For article reading, verify that the returned content is the article body, not
an `/api/comments` response: matching a generic `content` field can falsely
pass the contract. Retry another extraction path when the semantic target is
wrong even if the tool reports success. Check official article images when
specifications may be in graphics; text-only extraction does not see them.
A 256 KiB probe may truncate a long comparison page before its final rows;
verify the full response before treating an absent feature as a negative fact.

## First-class Hermes tool

When the ``walter_browse`` tool is available, use it as the primary entrypoint
for a known URL and a structured extraction request. The model supplies the
URL and the semantic contract; the tool's backend chooses the cheapest valid
route and escalates automatically. Do not manually choose Camoufox or Webtop
for normal extraction.

Hermes may defer plugin tools behind progressive Tool Search to protect prompt
cache and context budget. If ``walter_browse`` is not in the visible tool list,
search for ``walter_browse`` with ``tool_search``, inspect its schema with
``tool_describe``, then invoke it through ``tool_call``. This is still the
first-class Walter tool path; do not fall back to ``terminal`` merely because
the plugin is deferred.

Recommended call contract:

- ``url``: the public http(s) target;
- ``objective``: a short description of the requested result;
- ``profile``: a known site profile, **or** ``expected_fields`` mapping canonical
  names to aliases;
- ``required_fields``: fields that must be present;
- ``min_records``: minimum acceptable record count;
- ``mode``: ``auto`` in normal operation.

The tool returns the normalized ``records`` plus ``route``, ``attempts``,
``profile``, ``best_candidate``, and source paths. Treat ``success=false`` or
an empty ``records`` list as a failed extraction and do not fabricate missing
values. Use ``terminal`` with the stable CLI only for backend diagnostics,
explicit mode testing, or when the plugin is unavailable.

## Stable CLI

The installed entrypoint is:

```bash
/root/.hermes/bin/universal-scraper \
  --url 'https://example.com/api/results' \
  --expected-fields '{"title":["title","headline"],"url":["url","link"]}' \
  --required-field title \
  --required-field url \
  --mode auto \
  --pretty
```

The validated test-lab profiles can be used with `--profile`, for example:

```bash
/root/.hermes/bin/universal-scraper \
  --url 'https://www.trip.com/flights/showfarefirst?...' \
  --profile flight-search \
  --mode auto \
  --pretty
```

Use `--mode scrapling`, `--mode camoufox`, or `--mode webtop` only for
backend diagnostics. Normal operation is `--mode auto`, which executes the
full bounded chain.

## Output contract

The JSON result includes:

- `route`: `probe-http`, `static-html`, `api-replay`, `scrapling`,
  `camoufox-max`, or `webtop-cdp`;
- `attempts`: backend, latency, candidate count, record count, and errors;
- `trace`: ordered technical decision events (`API_JSON_DIRECT`, `HTML_STATIC`,
  `SPA_DETECTED`, `CHALLENGE_DETECTED`, `HTTP_ATTEMPT`, `HTTP_DIRECT_SUCCESS`,
  `HTML_STATIC_DIRECT`, `API_REPLAY_VALIDATED`, `API_REPLAY_FAILED`,
  `DOWNGRADE_HTTP`, `FALLBACK_BROWSER`);
- `signals`: the probe-derived technical signals used for routing;
- `probe`: bounded probe metadata (status, content type, flags, `probe_ms`) —
  the probe body itself is never exposed in the result payload;
- `downgrade`: non-null only on a validated API downgrade (`from`, `to`,
  `validated`, endpoint contract);
- `records`: normalized fields with source paths;
- `best_candidate` and `json_candidates`: bounded metadata and scores (the
  `method` may be `DOM` for an explicit Webtop projection);
- `escalation`: a `brave-mac-cdp` recommendation only when all structured
  routes failed.
- `profile`: learned-index status (`hit`, freshness, route used, route learned,
  preferred route and reliability state), or a cache key with `hit=false` on
  first observation.

Cookies, authorization headers, and complete request bodies must not be logged
or included in the result. Request body metadata is limited to byte counts.
The probe body and any replay template are internal execution state only and
never appear in the JSON output.

## Routing boundaries

- Known URL + structured data: call `walter_browse`; use `mode=auto` and let the
  backend choose the cheapest validated route.
- No known URL: use `web_search`; do not use Scrapling to discover the web.
- Search result requiring structured extraction: call `walter_browse` on the
  selected URL with `expected_fields` and `required_fields`.
- Multiple URLs or a crawl: use Scrapling bulk/spider operations rather than
  launching one Walter process per URL.
- Complex authenticated interaction, CAPTCHA, or visual verification: use
  Camoufox Max or Webtop directly; Walter Browse is an extractor, not an
  interactive browser or CAPTCHA solver.
- Need a visual answer: capture the page and inspect it with the visual browser
  tools after extraction.

## Verification

For a new target, call `walter_browse` with explicit field aliases and inspect
`success`, `route`, `attempts`, and `records`. Use the stable CLI only for
backend diagnostics or explicit mode tests. Never report a successful
extraction from the HTTP status alone. For an explicit DOM profile, verify the
returned records contain the required semantic fields and that price units or
availability flags are not conflated.

## Lot 1 reference

Signal-aware routing, API discovery + validated replay downgrade, profile
index v3, static HTML fast path, the `_resolve_json` fix and endpoint-secret
rules are documented in
`references/lot1-signal-routing-api-downgrade.md`.

## Lot 2 — Session Manager

First-class `BrowseSession` abstraction (`browse_session.py`): identity
(anonymous/personal/temporary/account:x), session-scoped network
(`local` DEFAULT, vpn/proxy opt-in), temporary vs persistent lifecycle,
cookie/storage scoping for HTTP replay, and strict isolation. Camoufox MAX
serves as the warm browser pool (one context per session userId) with
per-session proxy support and a `/session/state` export endpoint. CLI flags:
`--session-id`, `--identity`, `--persistent`, `--network`, `--country`,
`--session-save`. Overhead when no session is requested: ≈ 0 ms.
Full doc + proofs: `references/lot2-session-manager.md`.

## Lot 3 — Web Memory

Capabilities/domain profiles (profile_index v4), result cache (data plane),
CapabilityEngine fast path, the full discover → learn → reuse → break →
rediscover → repair cycle. Zero LLM in routing/execution.
Full doc: `references/lot3-web-memory-capabilities.md`.

## Lot 4 — Integration & upgrade resilience

Tool contract élargi (read/search/extract/capability/session, expected_fields
optionnel, content_only), adapter Hermes unique (`hermes_adapter.py`),
startup self-test + `WALTER_BROWSE_DEGRADED`, trace
`WALTER_BROWSE_INVOCATION`, `walter-browse doctor`,
`check-hermes-upgrade.sh`, contract tests + upgrade simulation (16 tests),
preuve d'appel réelle via harness (3/3 web, 0/3 non-web).
Full doc: `references/lot4-integration-robustness.md`.
