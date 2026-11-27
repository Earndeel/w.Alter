---
name: universal-web-extraction-router
category: research
description: "Walter Browse internals for diagnosis: how walter_browse routes a request (probe, static HTML, learned replay, Scrapling, Camoufox Max, Webtop), how to read its result (route, attempts, trace, records), its CLI for backend tests, and the fallbacks when an extraction is empty, wrong or blocked. Not needed to make a normal walter_browse call."
---

# Universal Web Extraction Router

What happens inside `walter_browse`, to understand and repair an extraction — not a step before calling it. The
model-facing contract stays `walter_browse` (see its description, and `walter-browse-orchestrator` for which
parameters fit which need).

## Routing chain (inside walter_browse, `mode=auto`, zero LLM call)

1. **Learned profile first**: the persistent index (value-free URL scope + extraction schema) may propose a validated
   route; it is a hint only — the semantic gate decides, failures fall through. Entries older than 7 days are
   diagnostic only; two consecutive failures degrade an entry until a later valid extraction repairs it. Index:
   `$HERMES_HOME/cache/universal-web-extraction/profiles.json` (route metadata only, never payloads, cookies,
   authorization headers or request bodies).
2. **Signal-aware probe**: one GET reading up to 256 KiB → status, content type, JSON vs HTML, scripts, visible-text
   ratio, challenge markers (403/429/503, Cloudflare), `content_present` (the requested field aliases occur in the
   static body). Direct JSON satisfying the spec → `route=probe-http`; static HTML with recoverable blocks →
   `route=static-html` (no browser). `content_present` forbids escalating on a SPA heuristic.
3. **Lightest valid path**: validated learned replay, then Scrapling network/XHR capture, then Camoufox Max
   (`http://127.0.0.1:9377`, bounded fetch/XHR collector), then the persistent Webtop Chromium (CDP 9223, host 9222
   fallback; DOM projection only for an explicit site profile).
4. **API discovery + downgrade**: after a browser success, same-site JSON endpoints are replayed over HTTP and
   validated by the same scorer → `API_REPLAY_VALIDATED` / `DOWNGRADE_HTTP` (`route=api-replay`, contract persisted)
   or `API_REPLAY_FAILED` / `FALLBACK_BROWSER` (browser result kept).
5. **Final escalation**: `escalation.recommended_backend=brave-mac-cdp` rather than invented data.

## Reading a result

- `route`: `probe-http`, `static-html`, `api-replay`, `scrapling`, `camoufox-max` or `webtop-cdp`.
- `attempts`: backend, latency, candidates, records, errors. `trace`: ordered decisions (`API_JSON_DIRECT`,
  `HTML_STATIC`, `SPA_DETECTED`, `CHALLENGE_DETECTED`, `HTTP_DIRECT_SUCCESS`, `HTML_STATIC_DIRECT`,
  `API_REPLAY_VALIDATED`, `API_REPLAY_FAILED`, `DOWNGRADE_HTTP`, `FALLBACK_BROWSER`). `signals` / `probe`: what the
  routing saw (the probe body itself is never returned).
- `records`: normalized fields with source paths; `best_candidate`, `json_candidates`: scores; `profile`: learned
  index status; `downgrade`: only on a validated API downgrade.
- Cookies, authorization headers and full request bodies never appear (byte counts only).

## Verification rules

- A HTTP 200 is not success: usable only when a candidate holds every required field and yields ≥ 1 normalized
  record. `success=false` or empty `records` = failed extraction; never fill the gap.
- Article reading: check the content is the article body, not an `/api/comments` response (a generic `content`
  field can falsely pass). Retry another path when the semantic target is wrong even if the tool reports success.
- Specifications may live in images: text extraction does not see them.
- The 256 KiB probe may truncate a long comparison page: check the full response before treating an absent feature
  as a negative fact.
- DOM profiles: check price units and availability flags are not conflated.

## Boundaries

- Many URLs or a crawl: Scrapling bulk/spider (`scrapling` skill), not one walter_browse per URL in a loop of
  hundreds.
- Complex authenticated interaction, CAPTCHA, visual verification: the signed-in browser path
  (`browser_session` + `walter-browser`, see `walter-browse-orchestrator`); Walter Browse is an extractor, not a
  CAPTCHA solver.

## CLI (backend diagnostics only)

```bash
/opt/walter-browse/bin/universal-scraper --url 'https://example.com/api/results' \
  --expected-fields '{"title":["title","headline"],"url":["url","link"]}' \
  --required-field title --required-field url --mode auto --pretty
```

`--profile <name>` uses a validated profile (e.g. `flight-search`); `--mode scrapling|camoufox|webtop` forces one
backend for a test. Session flags: `--session-id`, `--identity`, `--persistent`, `--network`, `--country`,
`--session-save`.

## References

- Signal routing, API downgrade, profile index, static fast path: `references/lot1-signal-routing-api-downgrade.md`.
- Session manager (identities, per-session network, isolation, Camoufox pool): `references/lot2-session-manager.md`.
- Web memory (capabilities, result cache, discover → learn → reuse → repair): `references/lot3-web-memory-capabilities.md`.
- Integration, self-test, `walter-browse doctor`, upgrade resilience: `references/lot4-integration-robustness.md`,
  `references/lot4b-universal-front-door.md`.
- Backend fallbacks and evidence validation when the first backend fails (merged 2026-11-01, full original text):
  `references/merged-web-extraction-fallbacks/universal-web-extraction-router.md` (+ its supporting files).
