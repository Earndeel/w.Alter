# Safe Learned Replay, Schema Drift, and Trip.com Detail Normalization

This reference records the production pattern validated in the Universal Web
Extraction Router hardening session. It complements `learned-profile-index.md`;
keep the rules here at the adapter/index boundary rather than in a generic
scraper.

## Replay contract

A learned replay template is eligible only when all of the following are true:

- the captured method is `GET`;
- the captured content type is JSON;
- the endpoint host is the same site as the source URL, allowing a legitimate
  first-party API subdomain but not an unrelated host;
- the endpoint path has no unsubstitutable dynamic segment;
- every query parameter is either an explicit source-query binding or a bounded,
  non-sensitive static literal.

Reject the complete template if any query key/value looks like a token, secret,
password, cookie, session, CSRF value, signature, API key, credential, or opaque
long random string. Do not persist POST bodies, cookies, authorization headers,
or response payloads. A value matching by accident is not proof of a dynamic
binding: prefer an exact source-query key or a profile-declared
`replay_query_keys`; only use value matching for clearly dynamic key names.

Render the template with the current source URL, not with the historical
capture. Fail closed if a required source key is absent. The replay transport
must reject non-2xx responses and non-JSON responses before semantic scoring.
Then run the exact same required-field, minimum-record, and record-projection
contract used by the normal extractor. A valid HTTP response is not a valid
extraction.

## Shape-drift state machine

Persist a shape fingerprint derived from matched semantic fields and their
source paths, not from response values. On each usable observation:

1. first observation establishes a stable baseline;
2. a new fingerprint is `suspected`, disables replay, and falls through to the
   ordinary backend chain;
3. the same new fingerprint twice confirms `drifted`, records the previous
   fingerprint/count/timestamp, and replaces the baseline;
4. two successful non-replay observations of the new baseline re-enable replay.

Expose `schema_status`, drift streak/count, and `replay_available` in profile
summaries and health diagnostics. Do not silently continue a replay whose shape
no longer matches the learned baseline.

## Trip.com detail adapter

Use a separate explicit `trip-hotel-detail` profile; do not overload the hotel
list projection. Let the browser expression return a small `{hotel, rooms}`
shape, then normalize in Python so the semantics are unit-testable:

- emit one output record per room;
- propagate hotel name, ID, URL, rating, and address/location into each room
  record;
- parse currency-bearing strings without losing decimal/comma conventions;
- keep `nightlyPrice`, `totalPrice`, and canonical `price` separate;
- set `priceBasis` to `total` or `nightly` (or preserve an explicit basis);
- map boolean/status/sold-out text to `available=True/False`, otherwise retain
  an explicit unknown rather than guessing;
- preserve room count/rooms-left and status fields when present.

The detail fixture should contain both available and sold-out rooms and must
pass the same semantic scorer used by live extraction. A real detail URL should
be supplied for live runs; fixtures are for deterministic normalization tests.

## Vertical verification recipe

Use one RED→GREEN slice for each behavior. The validated slices were:

1. safe template creation/rendering and secret rejection;
2. router tries replay before browser routes and falls back after replay failure;
3. two repeated new shapes disable replay;
4. direct replay projects a fake 2xx JSON response with current parameters;
5. Trip.com detail normalization expands shared hotel context into room rows.

For the reference implementation, the focused suite was run with:

```bash
cd /root/.hermes/skills/research/universal-web-extraction-router/scripts
/root/.venv/scrapling/bin/python -m unittest discover -v -p 'test_*.py'
/root/.venv/scrapling/bin/python -m py_compile \
  universal_extractor.py profile_index.py universal_router.py \
  webtop_client.py panel_server.py
```

The local panel must be restarted after module changes. Verify `/api/health`,
`/api/scenarios`, and a fixture POST; the detail fixture should report two
records and a valid semantic result. Confirm that only the intended panel PID
was restarted and that no stale test ports remain listening.

## Known boundary

This pattern handles query-based GET JSON replay. It intentionally does not
claim support for POST replay, GraphQL mutations, WebSockets, protobuf, or
cross-site API authentication. Those require separate request contracts and
security review.
