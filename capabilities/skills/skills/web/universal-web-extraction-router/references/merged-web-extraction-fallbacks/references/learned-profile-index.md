# Learned Profile Index for Resilient Extraction

## When to use it

Add a learned profile index when a universal extractor serves the same site or
journey repeatedly and route discovery is materially more expensive than the
actual extraction. Keep it as a hint layer beside the generic router, not inside
a site adapter and not as a raw response cache.

## Profile identity

Use a stable identity composed of:

- normalized host, with `www.` and default ports normalized;
- normalized path, replacing clearly dynamic numeric/UUID-like segments with an
  `{id}` marker;
- sorted query parameter names, while discarding query values such as dates,
  search terms, prices, and pagination;
- a schema fingerprint containing the scenario name, aliases, required fields,
  minimum records, score threshold, and any explicit DOM profile.

The schema fingerprint is essential: the same URL must be allowed to have
separate profiles for hotel cards, flight fares, article feeds, and detail
pages. If optional query parameters vary, match a same host/path/schema entry
and update it rather than creating one profile per query shape.

## Safe learning loop

1. Look up the profile before choosing the automatic route.
2. Reorder the normal backend chain only for a fresh, active profile whose
   previous success passed the semantic record gate.
3. Run the chosen backend through the same extractor and field/record validator
   used for an unprofiled request.
4. After a usable result, persist route and bounded evidence: candidate method,
   content type, normalized path/query names, matched fields, source paths,
   score, record count, latency, and per-route success/failure counters.
5. If the hint fails, continue through the ordinary fallback chain. If another
   route succeeds, make that route preferred and report both `route_used` and
   `route_learned`, including a `relearned` flag.
6. Never create a profile from an HTTP 200, a non-empty payload, or a failed
   request. A profile requires normalized records satisfying the requested
   contract.

A stale profile should remain observable but must not shortcut the chain. A
small failure streak (for example, two consecutive failed observations) should
demote it; a later valid observation should reactivate and repair it. Provide
manual invalidation for known site changes and make invalidation use the same
path/query-shape matching rules as lookup.

## Storage contract

Store the registry under the active application home, for example:

`$HERMES_HOME/cache/universal-web-extraction/profiles.json`

Use a versioned JSON file for a small registry (a few hundred profiles). Use
atomic temp-file replacement, `fsync`, a thread lock, and an interprocess file
lock. Set the parent directory to `700` and the file to `600`. Cap the number of
profiles and prune the oldest successful entries to prevent unbounded growth.

Persist no cookies, authorization headers, raw request bodies, complete response
payloads, or unredacted query values. Body diagnostics should be limited to byte
count and, if necessary, a hash. Corrupt storage should fail open to the generic
router, expose a load diagnostic, and be repairable by the next valid write.

## Verification matrix

Unit-test at least:

- dynamic query values produce one key;
- optional query-shape changes can reuse one entry;
- fresh profiles reorder the backend chain;
- stale/degraded/invalidated profiles never shortcut the chain;
- a failed preferred route falls through and re-learns the successful route;
- corrupt JSON does not break extraction and is repaired by a valid observation;
- persisted JSON contains metadata but no payload, cookie, or authorization data.

Then run a real public URL twice with the same schema and changed query value.
Verify that the first run creates a profile, the second reports a hit with the
same key, the result still passes the semantic gate, and the diagnostics expose
the selected and learned routes. Fixture runs should not write learned profiles.
Restart long-lived panel/server processes after code changes so they load the
new router module before judging live behavior.

## Boundaries and follow-ups

A routing profile accelerates backend selection and preserves mapping evidence;
it does not automatically create arbitrary DOM adapters and does not imply
request replay. Direct endpoint-template replay, date/traveler parameter
interpolation, schema-drift scoring, WebSocket/protobuf handling, and
record-level joins require separate explicit contracts. Keep these concerns out
of the registry until their security and validation rules are defined.
