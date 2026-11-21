---
name: web-research
description: "Use for evidence-backed web research and browser recovery."
version: 1.0.0
author: Hermes Curator
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [web, research, extraction, browser, evidence, citations, monitoring, osint]
---

# Web Research

Use this class-level umbrella for public-web discovery, extraction, interactive navigation, blocked-page recovery, evidence-backed synthesis, monitoring, and public-profile research. Choose the least invasive path that can actually verify the requested claim.

## Always-on rules

- Define the question, freshness boundary, sources, fields, sampling scope, and allowed access before fetching; a page load or search result is not evidence by itself.
- Separate discovery, extraction, interaction, interpretation, and citation; preserve raw source identifiers, URLs, timestamps, and retrieval boundaries.
- Keep observed facts, analyst inference, and uncertainty distinct; never infer identity, intent, causation, price, availability, or materiality from a weak signal alone.
- Prefer canonical and primary sources, use the smallest useful fetch, and report missing, blocked, truncated, stale, or contradictory evidence instead of filling gaps.
- Do not expose credentials or personal cookies to generic proxy/unblocking services; use authenticated or anti-detection sessions only when authorized and necessary.
- Register sources when retrieved, cite while drafting, attach verbatim evidence for high-stakes claims, and verify that every citation resolves to the exact source artifact.

## Routing and browser escalation

1. For an unknown target, use search only to discover candidate sources and deduplicate domains.
2. For a known URL and structured fields, use the approved public-web extraction front door first.
3. Use Playwright/CDP or another real browser when the task requires clicks, forms, filters, login, downloads, JavaScript state, or visual inspection.
4. Escalate by domain from deterministic extraction to an approved authenticated anti-detection session only when the lower-cost path cannot express or retrieve the required state.
5. Treat browser version, context creation, session liveness, page state, and final-result extraction as separate checks; HTTP 200 and a health flag do not prove success.
6. For live comparisons, run a bounded structured preflight, normalize and rank locally, then browser-verify shortlisted candidates. Preserve query, locale, parser version, raw artifact, and collection time; recheck prices, availability, taxes, and booking conditions at the final step.

## Blocked-page recovery

On a 403, 429, WAF, paywall, geo block, login wall, or bot interstitial, stop repeating the unchanged request. Choose a permitted route such as a timestamped archive snapshot, archive.today, an authenticated server-side reader when configured, a same-host API/GraphQL/JSON/RSS/sitemap pivot, a real browser, or an explicit blocker report.

Validate the body, not only status or byte count: reject redirects, rate-limit pages, login shells, fake cache pages, and unrelated interstitials. Mark archive results as `snapshot` with their date, keep live results as `live`, and never present a stale snapshot as current price, availability, or breaking news.

## Extraction, citations, and synthesis

- Start with a representative sample before scaling; preserve source title, author, publication date, URL, quoted/structured evidence, and coverage gaps.
- Reconcile sources and expose contradictions; prefer primary records for dates, prices, legal status, metrics, and specifications.
- Use a citation ledger or equivalent stable source IDs, cite consequential claims inline, render the source list mechanically, and run a final citation/evidence check.
- For high-stakes work, attach exact quotes copied from retrieved text and label genuinely unsourced claims as unverified rather than inventing support.
- For conversation corpora, paginate completely and include negatives, missing replies, edits/deletions, time gaps, thread boundaries, and sampling bias; normalize only in a derived view.

## Monitoring and public-profile research

- Freeze a company watch contract: canonical entities, aliases, domains, event categories, cadence, cutoff, materiality threshold, source coverage, and deduplication key.
- Collect incrementally with overlap for late indexing; a failed source creates an explicit coverage gap and must not advance the cutoff or become “no news.”
- Collapse syndicated stories and rewrites into one underlying event while retaining independent corroboration, then report event, date, source, change, significance, confidence, and follow-up.
- Distinguish account discovery from identity confirmation; use public signals only, keep matches probabilistic, avoid sensitive-trait inference, and report conflicts.

## Verification contract

A finished task contains the requested output, source provenance, freshness/retrieval boundary, coverage and uncertainty, explicit blockers for unverified constraints, and no invented counts, pages, prices, dates, or evidence. A successful fetch without claim-level support is incomplete.
