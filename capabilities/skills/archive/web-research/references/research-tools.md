# Research tools and operational branches

## Blocked-page recovery

Run `scripts/recover_page.py <url> --json` after a blocked fetch when archive or reader recovery is permitted. It tries timestamped Wayback, archive.today domain rotation, and keyed Jina Reader in that order, validates bodies against interstitial and redirect-stub false positives, and reports `snapshot` versus `live` provenance. If no copy is recovered, pivot to a same-host API/feed/JSON/sitemap or a real browser instead of repeating the unchanged request.

## Citation ledger

Run `scripts/sources.py reset` for a new grounded task, `add` or `ingest` at retrieval time, `quote` for verbatim evidence, `render` for the source block, and `verify` before delivery. The ledger owns URL identity and citation numbering; prose emits only IDs supplied by it.

## Monitoring

Freeze canonical entities, aliases, domains, event categories, cadence, cutoff, materiality threshold, source coverage, and the event deduplication key. Collect with overlap for late indexing, keep source failures as coverage gaps, collapse syndicated reports into one underlying event, and report change, significance, confidence, and follow-up separately.
