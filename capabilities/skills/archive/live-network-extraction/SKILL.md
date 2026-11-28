---
name: live-network-extraction
description: "Use for real JSON-first web extractor validation."
version: 1.0.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [web-data, scraping, network-interception, json, validation, e2e]
    related_skills: [scrapling, web-extraction-fallbacks, anti-bot-navigation, web-table-extraction]
---

# Live Network Extraction

## Trigger
Use when Monsieur wants to prove that a generic web extractor works against real websites, replace fixture-only validation, compare heterogeneous payload shapes, or harden a network-interception pipeline before production.

## Core contract
A fixture proves parser behavior only. A LIVE run proves compatibility with a real target, a real response shape, and the semantic gate. Never report fixture success as website compatibility.

The primary path is:

```text
real target → browser/session network capture → JSON candidate collection
→ relevance scoring → semantic minimum-field gate → normalized records
→ evidence report
```

DOM extraction is a fallback for a genuinely useful target when no suitable JSON payload is exposed; it is not a substitute for testing the network path.

## Workflow

1. **Define a cross-shape matrix.** Choose public, unauthenticated targets covering the actual need classes rather than six URLs from one site. A useful baseline spans travel search, accommodation, commerce, social, editorial/content search, and a directory or public API.
2. **Use a persistent browser/session pool.** Reuse sessions where possible, bound concurrency, set an explicit timeout, and close the pool in a `finally` block. Record per-target latency; do not hide slow or timed-out targets behind a global average.
3. **Capture all useful JSON response types.** Include `xhr` and `fetch`, but also accept a `document` response when the navigation itself returns JSON. Direct public JSON endpoints are legitimate LIVE targets and expose an important path that page-only tests miss.
4. **Score before projecting.** A HTTP 200, a large payload, or a URL containing `/api/` is not semantic success. Select candidates by signal density, expected record shape, minimum record count, and required fields.
5. **Tune contracts from observed payloads.** When a real candidate scores well but fails the gate, inspect the actual keys and add evidence-backed aliases. Relax only fields that are genuinely optional on that target. Do not copy fixture field names into a live contract without seeing them in the payload.
6. **Classify outcomes honestly.** Keep `accepted`, `rejected_or_blocked`, `timeout`, and `error` distinct. A blocked target is useful evidence for a fallback/adaptor; it is not an empty successful dataset.
7. **Save an evidence report.** Store target URL, profile, endpoint path, HTTP method/status, response size, matched fields, score, record count, latency, error state, and the normalized records or a safe preview. Keep credentials and sensitive payloads out of the report.
8. **Expose LIVE explicitly in the test lab.** Make real runs the obvious path for real profiles; retain fixtures as a separate regression control. A global LIVE button must run only profiles with a declared public target and must surface each run independently.
9. **Verify the integration surface.** Run the real matrix, then run the panel/API path, check that active runs return to zero, inspect the UI for accepted/rejected status, and check browser console errors. Unit tests alone are insufficient for network interception.

## Contract design

- Required fields are the semantic minimum needed to identify a useful record, not every desirable enrichment field.
- Keep useful enrichments such as rating, stock, engagement, currency, and category optional when public endpoints omit them.
- Use aliases for naming variation (`created_at`/`createdAt`, `content`/`text`, etc.) only after inspecting real payloads.
- Preserve the source endpoint and matched signal fields so a future adapter can be built from evidence rather than guesswork.

## Anti-bot and fallback rules

- Start with the least invasive public route and respect site terms, rate limits, and robots guidance where applicable.
- Use a stealthy browser/session only when the target requires JavaScript or browser behavior; do not route every simple JSON endpoint through an expensive browser unnecessarily.
- If a target returns a candidate but the schema is wrong, fix the contract before escalating anti-bot tooling.
- If the target is genuinely blocked, preserve the failure and route to the documented fallback tier; never turn a block page or telemetry payload into records.
- Avoid repeated probes against the same host while debugging; inspect one captured payload, patch the contract, then rerun.

## Verification checklist

- [ ] Every claimed profile ran against a real public target
- [ ] The captured candidate has a real HTTP method and status
- [ ] Required fields and minimum records passed the semantic gate
- [ ] Direct JSON document responses are supported where applicable
- [ ] Per-target records, endpoint paths, scores, and latency are persisted
- [ ] Blocked, rejected, and accepted states remain distinguishable
- [ ] Fixture tests still pass as regression coverage
- [ ] The panel/API path has been exercised, not only the Python runner
- [ ] Browser console and server health are clean after the run

## References

- `references/live-matrix-validation.md` — reusable matrix shape, report schema, and the real public-target pattern validated during the initial end-to-end pass.

## Relationship to neighboring skills

`scrapling` remains the user-owned implementation skill for fetchers, sessions, and parsing. This umbrella governs the higher-level validation contract and evidence discipline around a generic JSON-first extractor; it deliberately does not replace Scrapling's API instructions.
