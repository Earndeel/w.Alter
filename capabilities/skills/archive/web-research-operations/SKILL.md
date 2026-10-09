---
name: web-research-operations
description: Use for web extraction, evidence, and profile research.
version: 1.0.0
author: Hermes Curator
license: MIT
metadata:
  hermes:
    tags: [web, extraction, research, evidence, osint, citations]
---

# Web Research Operations

Use this class-level skill for public-web navigation, extraction, evidence-backed research, corpus analysis, and public-profile investigation. Choose the least invasive access path and keep claims tied to independently retrievable evidence.

## Always-on rules

- Separate navigation, extraction, interpretation, and citation; a page load is not evidence for a claim.
- Prefer the canonical source and the smallest useful fetch, preserve the retrieval date/context, and report unavailable or blocked content instead of filling gaps.
- Treat anti-bot, paywall, rate-limit, geo, login, and malformed-content failures as different classes with different recovery paths; do not repeat an unchanged request.
- Keep public facts, inference, and uncertainty separate; do not convert correlation, profile resemblance, or search ranking into identity or causation.
- Avoid credentialed or invasive access unless explicitly authorized and supported by the relevant consent/safety gate.

## Navigation and blocked pages

1. Classify the target as public static content, a dynamic browser page, an authenticated service, or a blocked/geo-restricted surface.
2. Try the canonical low-cost retrieval first, then the documented browser or alternate extraction path; preserve the same target URL and query intent.
3. On 403/429/WAF/paywall/geo failures, read the actual response and choose a different permitted path, wait for a stated rate limit, or report the blocker. Never claim extraction from a page not actually read.
4. Validate that returned content belongs to the requested URL and is not an interstitial, cached shell, login page, or unrelated search result.
5. For dynamic pages, wait for the relevant state, extract the semantic content, and capture enough provenance to reproduce the claim.

## Extraction and evidence

- Define the question and evidence requirements before crawling; use a small representative sample before scaling.
- Preserve source URL, title/author/date when available, quoted or structured evidence, and the boundary between source text and analyst synthesis.
- Reconcile multiple sources, flag contradictions, and prefer primary records for dates, prices, metrics, legal status, and technical specifications.
- Re-fetch material facts when freshness matters; do not use a stale snippet as current evidence.
- Cite every consequential claim to the exact source and state what remains unverified.

## Research and monitoring

For company/news monitoring, define named entities, material-event categories, time window, and deduplication rules. Report only events meeting the materiality threshold, with source and publication date; do not turn every mention into a “news” item.

For public-profile OSINT, distinguish account discovery from identity confirmation. Use only public profile signals, keep candidate matches probabilistic, avoid sensitive trait inference, and report conflicting or missing evidence.

## Conversation corpus analysis

- Inventory the corpus, paginate completely, and record the retrieval boundary before judging patterns.
- Include negatives, missing replies, edits/deletions, time gaps, thread boundaries, and sampling bias; selected positive examples are not a corpus.
- Normalize only for analysis while preserving raw text and message identifiers; separate observed wording from interpretation.
- State uncertainty and avoid diagnosing people or intent from text alone.

## Completion contract

A finished research task contains the requested output, citations/provenance, freshness or retrieval boundary, explicit uncertainty, and a blocker for every unverified constraint. Never invent counts, pages, prices, dates, or evidence.
