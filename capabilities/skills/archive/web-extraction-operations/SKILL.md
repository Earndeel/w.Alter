---
name: web-extraction-operations
description: Use for web extraction and semantic evidence validation.
tags: [web, extraction, scraping, fallback, json, tables, drift]
metadata:
  hermes:
    tags: [web, extraction, scraping, fallback, json, tables, drift]
---

# Web Extraction Operations

Use this umbrella for public-web extraction, structured tables, network-first capture, browser fallbacks, and live-data freshness checks. A navigation or HTTP success is only transport evidence; accept a result only after semantic validation.

## Routing and evidence

Choose the cheapest reliable transport, then escalate from direct/static HTTP to structured extraction, persistent browser/network capture, anti-bot browser, or authenticated browser only when symptoms justify it. Keep one controlled session per target where possible, close disposable tabs, and preserve route, method, status, timing, source paths, candidate score, record count, and errors without credentials or cookies.

A candidate must satisfy required fields, minimum records, correct record-level co-occurrence, and the requested projection. Keep accepted, rejected, blocked, timeout, and error states distinct. A fixture validates parser behavior; a live target validates compatibility with a real response.

## Tables and dynamic catalogs

Freeze metric, year, units, scope, source vintage, and forecast/actual status before extraction. Enumerate every table, parse structural rows and full numeric values, validate row counts/order/duplicates/geographic scope, and disclose exclusions. On dynamic pricing pages, separate page existence, exact rates, marketing discount, provider basis, and external benchmark; paginate structured catalog endpoints completely and mark missing rates unverified, never zero or not-found.

## Network and fallback rules

Prefer JSON/XHR/fetch/document payloads when they contain the semantic records, but use the rendered DOM only after network candidates fail the same scorer. Learn a route only after a valid normalized result; learned replay must be same-site, GET/JSON, parameter-bound, secret-free, schema-fingerprinted, and disabled after shape drift. Do not repeat a browser pattern that already lost state.

## Drift and freshness

For scheduled collectors, verify artifact `generated_at`, downstream timestamp agreement, row-count baselines, joins, and derived ordering—not merely exit code. Decode Next.js inline RSC strings generically, strip any one-letter prefix, find records by field presence, and update every shared parse path. Never repin a parser to the current prefix/container or publish a silently small/stale universe.

## Verification

Run the real target matrix and panel/API path, inspect blocked/rejected states, ensure active runs return to zero, and check console/server health. Keep fixture regression separate from live evidence and report retrieval timestamps.

Exact fallback, table, live-network, and payload-drift recipes are routed in `references/curator-web-extraction-archive-routes.md`.
