# Universal Web Extractor — Hermes Web Intelligence Router

JSON-first, endpoint-agnostic extraction for dynamic pages.

## What it does

- records `fetch`/`XHR` JSON responses without knowing the endpoint name;
- scores payloads against the requested fields and required invariants;
- finds repeated lists of objects recursively;
- projects generic records and preserves source paths;
- captures request method/body hash without persisting cookies or authorization headers;
- runs multiple requests concurrently with a bounded semaphore;
- falls back to a bounded Webtop CDP navigation when JSON remains unusable;
- projects known visible hotel cards from Trip.com when its network payloads
  expose only configuration/telemetry rather than the actual results.
- indexes successful site/route/schema combinations so the next compatible
  request can try the validated backend first.
- replays safe GET/JSON endpoint templates with current query parameters before
  opening a browser;
- detects repeated response-shape drift and temporarily disables replay until
  the new schema is relearned;
- normalizes Trip.com hotel detail pages into one record per room, including
  price basis, availability and hotel identity.

## Run unit tests

```bash
cd ~/.hermes/skills/research/universal-web-extraction-router/scripts
~/.venv/scrapling/bin/python -m unittest -v
```

## Run the live Trip.com probe

```bash
cd ~/.hermes/skills/research/universal-web-extraction-router/scripts
~/.venv/scrapling/bin/python run_live_trip.py
```

The live report is written to `/tmp/universal-trip-extraction-report.json`. It stores response metadata and extracted fields, not cookies or complete response bodies.

## Run the Test Lab

The local panel exposes reproducible fixtures for several needs and a real
network mode for the validated flight scenario:

```bash
cd ~/.hermes/skills/research/universal-web-extraction-router/scripts
~/.venv/scrapling/bin/python panel_server.py
```

Open `http://127.0.0.1:8766` and choose a profile:

- flight search;
- hotel availability;
- product monitoring;
- social monitoring;
- article discovery;
- lead directory;
- noise rejection / false-positive gate.

Fixtures execute the real scorer and projector without external traffic. LIVE
runs use the integrated Scrapling → Camoufox Max router for every profile that
declares live support. The panel is local-only and blocks private-network live
URLs.

## Integrated routing

`universal_router.py` exposes one contract for the live stack:

1. Scrapling's persistent `AsyncStealthySession` captures and scores JSON first.
2. If no semantically valid records survive, the router calls Camoufox Max at
   `http://127.0.0.1:9377`, injects a bounded fetch/XHR collector before
   navigation, and sends those payloads through the same scorer/projector.
3. If JSON remains semantically invalid, the router connects to the persistent
   Webtop Chromium CDP session (9223, with a host-local 9222 fallback), captures
   JSON responses, then applies a bounded DOM projection for named profiles.
4. If all three routes fail, the result includes
   `escalation.recommended_backend=brave-mac-cdp`.

The stable Hermes entrypoint is:

```bash
~/.hermes/bin/universal-scraper --url 'https://example.com/api' \
  --expected-fields '{"title":["title","headline"]}' \
  --required-field title --mode auto --pretty
```

For the Trip.com hotel profile, the live URL can be tested directly:

```bash
~/.hermes/bin/universal-scraper \
  --url 'https://www.trip.com/hotels/list?city=359&searchWord=Bangkok' \
  --profile hotel-availability --mode auto --pretty
```

For a detail page, pass the actual hotel URL supplied by Trip.com:

```bash
~/.hermes/bin/universal-scraper \
  --url 'https://www.trip.com/hotels/detail/?cityId=...&hotelId=...' \
  --profile hotel-detail --mode auto --pretty
```

The JSON output includes the chosen `route`, every backend `attempt`, bounded
candidate metadata, and normalized `records`. It never stores cookies,
authorization headers, or complete request bodies.

## Learned profile index

The router writes validated route knowledge to:

```text
$HERMES_HOME/cache/universal-web-extraction/profiles.json
```

The key combines a value-free URL scope (host, normalized path and query
parameter names) with the extraction schema signature. Dates, search terms and
pagination values therefore reuse one mapping instead of creating one entry per
request. A successful observation records the winning backend, candidate shape,
matched fields, source paths and route reliability; it never records response
payloads, cookies, authorization headers or raw request bodies.

On a fresh hit, a safe learned GET/JSON template is tried first, followed by the
learned browser backend. Templates are value-free except for bounded static
parameters: sensitive keys, credentials, opaque long tokens, dynamic paths and
POST bodies are rejected. The rendered response still passes the shared
semantic gate and the learned shape fingerprint; any failure falls through to
the normal Scrapling → Camoufox Max → Webtop chain. Profiles older than seven
days are visible in diagnostics but are not used as a shortcut; two consecutive
failures degrade a profile until a later success repairs it. A new response
shape is first marked `suspected`; two consecutive observations confirm drift,
disable replay, and require two successful non-replay observations before
re-enabling it. The panel exposes the same state at `/api/profiles` and under
the `profile_index` health field.

## Current boundary

Record-level semantic joins, and adapters for WebSocket, protobuf, and other
non-JSON transports remain production follow-ups. The router is intentionally
an extraction layer, not a CAPTCHA solver or a booking engine. DOM profiles are
explicit per-site adapters; the generic fallback does not pretend arbitrary
page text is structured data.
