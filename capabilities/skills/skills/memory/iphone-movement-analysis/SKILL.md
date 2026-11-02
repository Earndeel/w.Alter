---
name: iphone-movement-analysis
description: Use when Monsieur asks to reconstruct recent movements, stops or journeys from iPhone location samples stored in Walter Memory.
---

## Establish the period and available evidence

Load `memory_context` or `memory_recall`, then query `memory_events` for location events within the requested period. Resolve dates in the relevant local timezone; distinguish three calendar days from a rolling 72-hour window. The observed event type is `location.sample`.

Check the earliest and latest samples before promising coverage. Report missing periods explicitly; absence of samples does not establish absence of movement.

## Inspect the local source when MCP results are insufficient

Use read-only queries. The observed container is `hindsight-pg`, database `hindsight`, role `hindsight`. `-U postgres` failed because that role did not exist. Verify live configuration rather than assuming the role remains unchanged:

```bash
docker exec hindsight-pg sh -c 'env | grep -E "^POSTGRES_(USER|DB)="'
docker exec hindsight-pg psql -U hindsight -d hindsight -At -c '\d core.events'
docker exec hindsight-pg psql -U hindsight -d hindsight -At -c "SELECT privacy_class, count(*), min(occurred_at), max(occurred_at) FROM core.events WHERE event_type = 'location.sample' GROUP BY privacy_class"
```

Never print passwords or inspect the complete container environment. Respect event privacy classes: process restricted coordinates locally and do not expose local_only payloads to a cloud model.

## Extract and process samples locally

The observed payload fields are `lat`, `lng`, `accuracy_m`, and nested `raw.properties.wifi`. Inspect the current schema locally before relying on optional fields.

Use explicit start and end timestamps with offsets and a half-open interval. For example, to inspect coverage for three Bangkok calendar days:

```bash
docker exec hindsight-pg psql -U hindsight -d hindsight -At -c "SELECT count(*), min(occurred_at), max(occurred_at) FROM core.events WHERE event_type = 'location.sample' AND occurred_at >= TIMESTAMPTZ '2026-10-30 00:00:00+07' AND occurred_at < TIMESTAMPTZ '2026-11-02 00:00:00+07'"
```

Replace the example bounds with the requested period. Keep timestamps timezone-aware. Bangkok reports used `Asia/Bangkok`; do not assume this timezone for every request.

Create a private per-session scratch directory with `mktemp -d`. Export through PostgreSQL CSV output rather than joining fields with commas manually: Wi-Fi names and other text can contain delimiters.

Filter samples with missing or invalid coordinates. The observed analysis retained samples with `accuracy_m <= 100`; report the chosen threshold and retained count. Sort by timestamp, inspect sampling gaps, and compute geodesic distances locally using Haversine or an equivalent method.

Group sustained nearby samples into candidate stops, then inspect movement between stops. State the stop radius and minimum duration used. Check sensitivity to GPS jitter and accuracy before treating a short excursion as a journey. Do not sum every consecutive GPS displacement as a reliable travelled distance, and do not bridge long sampling gaps as a known route.

## Identify places and present findings

Use previously confirmed place labels or reports when available. Treat Wi-Fi observations as supporting evidence for a recurring location, not independent proof of a venue. Keep unfamiliar places as unnamed stops until confirmed; nearby businesses are only candidates.

Present local dates, stop intervals, approximate durations, and observed movement intervals. Distinguish straight-line displacement from route distance. Treat isolated speed peaks cautiously and avoid asserting transport mode from a single peak.

Include actual coverage, filtering criteria, gaps and uncertainty. Do not create persistent place labels or memory entries merely because a movement analysis was requested.
