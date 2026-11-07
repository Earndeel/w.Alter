---
name: live-data-payload-drift
description: Use when a live-data cron silently returns stale data.
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [scraping, cron, rsc, payload, staleness, artificial-analysis]
    related_skills: [aa-pareto-model-optimizer, live-network-extraction, universal-web-extraction-router]
---

# Live-Data Payload Drift

## Purpose

Detect and repair a deterministic live-data collector that keeps "succeeding"
while returning stale or empty data because the upstream site changed the shape
of its payload. This bit the AA Pareto pipeline twice in 2026: the cron did not
die — it silently generated the same stale snapshot for days.

The dominant cause on Next.js sites is a change in the **inline flight-payload
prefix** (observed: `c:` → `d:`) or in the container key/field names of the
embedded data. The fix is a *generic* parser, never a re-pin to today's exact
shape.

## When to Use

- A scheduled `no_agent=True` refresh script reports success but `generated_at`
  in the output artifact is frozen for more than 1 cycle.
- `cronjob list` shows `last_status: error` on a refresh job whose wrapper is
  not obviously broken, or shows `ok` while the artifact is visibly stale.
- A playwright/selenium inline-payload extractor raises
  `<label> RSC payload did not contain a models array` or returns far fewer
  rows than the previous known baseline.

## Procedure

1. **Confirm staleness, not breakage.** Read the latest artifact and compare
   `generated_at` with now. Check `cronjob list` → `last_status`. A frozen
   `generated_at` for days plus `error` status = payload drift, not a transient
   network blip (the wrapper has its own retries).
2. **Re-run the collector once manually.** If it fails on the live fetch, you
   have a repro. Do not guess the new shape — dissect it (see
   `references/rsc-payload-debugging.md` for a proven dissection script).
3. **Fix the parser generically.**
   - Strip *any* single-letter flight prefix (e.g. `strip_rsc_prefix` handling
     `x:` where x is one alpha char), NOT just the current literal (`c:`).
   - Match rows by a **field-presence predicate** (`"headlineValue" in item`),
     not by an exact known container name, so future key renames are absorbed.
   - Apply the fix in ALL parse paths sharing the decode routine (agentic +
     intelligence were both affected once), not just the one that threw first.
4. **Validate before trusting.** Assert row-count baselines (e.g. Agentic ≈ 139
   rows, ~132 with cost; Intelligence ≈ 580+ merged). A silently small universe
   means the extraction is still broken.
5. **Exercise the cron wrapper, not just refresh.py.** Run the
   `scripts/*_daily_refresh.py` wrapper under the interpreter the cron uses
   (`/usr/bin/python3`), then confirm the artifact's `generated_at` advances.
6. **Document the rupture in the owning skill's "Common failures"** with the
   old→new values observed, so the next drift is a 5-minute fix, not a new hunt.

## Multi-stage artifact verification

When a refresh wrapper produces several derived artifacts, validate the whole
chain rather than trusting the wrapper exit code:

1. Confirm the primary snapshot's `generated_at` advances during this run.
2. Confirm every downstream artifact exists and records the same primary
   snapshot timestamp (for example, a derived file's `aa_generated_at` matches
   the primary `latest.json.generated_at`).
3. Reconcile counts across artifacts: primary row counts must match the declared
   counts; registry-match flags must match profile metadata; joins may include
   matched identities with no populated category record and that is not a parser
   failure.
4. Check derived frontiers for positive costs and monotonic score/cost ordering;
   never publish a partial frontier because the wrapper happened to exit 0.
5. Run the owning skill's tests and syntax checks after a parser or schema
   change. Record the checks with the live timestamp and source URLs.

A successful multi-stage run is therefore `exit 0` **plus** fresh timestamps,
complete artifacts, reconciled counts, and schema/frontier assertions.

## Pitfalls

- **Silent staleness is the trap**: `no_agent=True` jobs only surface errors on
  non-zero exit. A collector that raises inside the fetch→parse chain and is
  caught/short-circuited can produce a "successful" run with an old footprint.
  Always eyeball `generated_at` on the artifact, never just the exit code.
- **Never re-pin to the observed shape.** The prefix letter and container key
  WILL change again. Genericity is the fix; a `c:` literal is a ticking test.
- **The `__next_f.push` script text is NOT JSON.** It is escaped strings inside
  push calls; decode each push with `json.loads(f'"{enc}"')` then strip the
  leading `x:` prefix before `json.loads` the whole payload.
- **Do not scrape the visible comparison chart** as primary source — it holds a
  page-dependent subset and silently omits valid frontier models; use the full
  model-context RSC payload.

## Verification

- [ ] `generated_at` in the artifact advanced after the fix
- [ ] The cron wrapper exits 0 under the cron interpreter
- [ ] Row counts match the known baseline (not a small subset)
- [ ] Both parse paths (agentic + intelligence) exercise the generic decoder
- [ ] Owning skill's Common-failures section documents the old→new shape

## References

- `references/rsc-payload-debugging.md` — dissection procedure and scripts for
  Next.js inline RSC payloads (flight-prefix letters, container keys, decode
  recipe, current AA row schema).
