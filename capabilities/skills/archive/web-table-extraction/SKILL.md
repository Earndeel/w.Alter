---
name: web-table-extraction
category: research
description: Extract, validate, normalize, and present complete tabular datasets from public web pages when browser snapshots or page previews are incomplete.
---

# Web Table Extraction

## Trigger
Use when a public webpage contains a ranking, comparison table, time series, country list, pricing grid, or other structured dataset that must be reproduced completely and accurately.

## Workflow
1. Confirm the requested metric before extraction: total versus per-capita, nominal versus PPP, current value versus forecast, and requested year.
2. Identify the primary source and record its publication date, data vintage, units, and whether figures are estimates or observations.
3. If a browser snapshot truncates rows, fetch the same page as ordinary HTML before escalating to browser automation.
4. Enumerate all tables and inspect each table's headers and row count. Pages often contain parallel tables for different years, sources, or metrics.
5. Parse body rows structurally rather than copying visible text.
6. Prefer full numeric values over abbreviated display values. Normalize units only after parsing.
7. Validate ordering, row count, duplicates, missing states, and whether territories are mixed with sovereign countries.
8. Translate labels only after preserving the original source names for verification.
9. Present the answer with the metric, year, units, source, and scope stated explicitly.

## Dynamic model and pricing pages
When the page is a model detail page rather than a literal HTML table, treat availability and pricing as separate facts:

1. Normalize the source slug and inspect the direct model page before labeling a row `not_found`.
2. Record the source URL even when the page exists but exposes no usable price; use `unverified` for a present page with missing or placeholder rates, not `not_found`.
3. Keep exact input/output rates, the page's marketing discount claim, the provider's official-price basis, and the external benchmark reference as separate fields. A conflict between them is evidence to report, not a value to average away.
4. Validate the extraction against the rendered page and any embedded data; model catalogs often contain variants whose slugs do not match page URLs exactly.
5. When a page is JavaScript-backed, identify and query its structured catalog endpoint before concluding that a model has no price. Paginate through the endpoint, group one-row-per-direction records, and distinguish parser failure from genuine absence.
6. For dynamic pricing, include the retrieval timestamp and do not carry a static discount table into a live benchmark.

See `references/dynamic-pricing-pages.md` for a concise verification pattern and evidence example. For the verified Kie.ai pricing-table contract, normalization rules, and audit fixtures, see `references/kie-pricing-table-api.md`.

## Accuracy rules
- Never infer unseen rows from a truncated preview.
- Never silently switch from total GDP to GDP per capita, nominal to PPP, or one year to another.
- Do not treat a geographic filter as self-explanatory: regional datasets may include territories or exclude transcontinental states.
- If removing territories or rows without comparable data, renumber the delivered ranking and disclose the exclusions.
- Keep source URLs as plain text or inline code for this user, never Markdown-labelled links.
- For French financial formatting, use spaces as thousands separators and commas as decimal separators; state whether values are millions, milliards, or dollars internationaux.

## Lightweight extraction pattern
For server-rendered HTML, use a direct HTTP fetch with a normal browser user agent and parse the returned tables with an HTML parser. Print table index, headers, and row count first; select the correct table only after inspection. Escalate to Scrapling or an interactive browser only when direct HTML is blocked or the table is generated exclusively by JavaScript.

## Verification checklist
- [ ] Metric and year match the request
- [ ] Source vintage and forecast/actual status disclosed
- [ ] Correct table selected among all page tables
- [ ] Full row count extracted
- [ ] Numeric values parsed from full-value fields
- [ ] Ranking remains sorted after filtering
- [ ] Territories and geographic edge cases disclosed
- [ ] Output units and locale formatting are unambiguous

## Relationship to other skills
This is the narrow execution companion to `universal-web-extraction-router`: that skill chooses the web route; this skill governs complete and accurate extraction once a tabular source has been found.

## References
- `references/economic-ranking-case.md` — condensed lessons from extracting and validating a regional economic ranking with parallel tables and geographic edge cases.
