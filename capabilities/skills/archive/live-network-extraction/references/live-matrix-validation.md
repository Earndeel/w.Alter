# Live Matrix Validation Reference

## Reusable matrix shape

Use six public targets with different response behavior, not six pages from one domain:

| Need class | Example public target | What it exercises |
|---|---|---|
| Flight search | Trip.com fare page | JS page plus nested flight JSON/XHR |
| Hotel availability | Trip.com hotel list | Dynamic refresh payload and sparse room data |
| Product monitor | IKEA search | Commerce catalog JSON with optional stock/rating |
| Social monitoring | Mastodon public tag timeline API | Direct JSON navigation and nested account/status fields |
| Article discovery | Hacker News Algolia search | Search XHR with `created_at`, story URL, author |
| Lead/directory | OpenStreetMap Nominatim search API | Direct JSON navigation and place/address records |

These are examples, not a permanent allowlist. Re-check public availability and terms before rerunning.

## Report contract

Persist one row per target with:

```json
{
  "profile": "social-monitoring",
  "url": "https://example.invalid/target",
  "state": "accepted",
  "error": null,
  "elapsed_s": 7.95,
  "valid_candidate_count": 1,
  "record_count": 20,
  "best_path": "/api/v1/timelines/tag/travel",
  "best_method": "GET",
  "best_status": 200,
  "best_score": 115,
  "matched_fields": ["author", "engagement", "published_at", "text"]
}
```

Keep the full normalized records only when they are safe to retain. Otherwise store a bounded preview plus the endpoint metadata.

## Observed first-pass pattern

The validated live pass accepted all six classes: flight 5 records, hotel 1, product 21, social 20, articles 30, and directory 10 (87 total). The hotel response was sparse, and the product response exposed title/price/currency but not a reliable stock field; both are valid reasons to keep those enrichments optional rather than falsify completeness.

The key implementation detail was accepting JSON `document` responses alongside `xhr`/`fetch`. That enabled the public Mastodon and Nominatim API targets. The semantic gate still required the profile's minimum fields, so HTTP 200 alone never counted as success.

## Debug sequence

1. Run the matrix with bounded concurrency and an explicit per-target timeout.
2. For every rejected candidate, record status, path, score, and matched fields.
3. Inspect the actual payload keys once; add only evidence-backed aliases.
4. Rerun the affected profile, then rerun the complete matrix.
5. Exercise the panel's global LIVE path separately from the Python runner.
6. Confirm active runs return to zero, the UI shows terminal states, and the browser console is clean.

Do not replace a rejected live run with a fixture result in the same report. That destroys the distinction the matrix exists to measure.
