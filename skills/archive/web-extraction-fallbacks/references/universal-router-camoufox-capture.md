# Universal Router + Native Camoufox Capture

## When to use

Use this reference for a known URL requiring endpoint-agnostic structured extraction. The stable entrypoint is `/root/.hermes/bin/universal-scraper`; normal mode is `--mode auto`.

## Routing contract

1. Run persistent Scrapling capture first.
2. Accept it only if a candidate satisfies the requested required fields, score threshold, minimum records, and normalized-record projection.
3. If Scrapling is empty, errored, or semantically invalid, call Camoufox Max and apply the same scorer/projector.
4. If both are semantically invalid, return an explicit `recommended_backend=webtop-cdp` escalation. This is a recommendation, not evidence that Webtop ran.

A 200 response, a non-empty JSON body, or one matching field is not extraction success. Preserve source paths and report backend attempts, timing, candidate counts, and errors.

## Camoufox Max response-capture contract

The reliable interception path is native Playwright response observation in `~/.hermes/camoufox-max/server-max.js`:

- attach `page.on('response', ...)` when `/tab/new` or `/tabs` creates the tab, before navigation;
- retain only bounded JSON-like `xhr`, `fetch`, or `document` payloads;
- expose them through `POST /tab/network-captures` with `{userId, tabId}`;
- return URL, method, status, content type, response byte count, request byte count, and parsed payload;
- cap the capture buffer and body size (the validated implementation uses 80 items and 1.2M characters per body);
- never return cookies, authorization headers, or complete request bodies.

The client should close the tab in `finally`. If the endpoint is unavailable on an older worker, fall back to the injected `add-init-script` fetch/XHR collector and mark that compatibility path internally.

### Important interception pitfall

An `add-init-script` hook can be visible in later `evaluate()` calls while still missing the page's first fetch because of browser execution-world/timing behavior. Do not treat a successfully installed hook as proof of capture; verify the captured item or use native response events.

## Verification recipe

```bash
curl -sS http://127.0.0.1:9377/health
/root/.hermes/bin/universal-scraper \
  --url 'https://example.com/api/results' \
  --expected-fields '{"title":["title"],"url":["url"]}' \
  --required-field title --required-field url \
  --mode auto --pretty
```

Inspect `route`, `attempts`, `records`, and `escalation`. For code changes, run the router unit suite, `node --check` on `server-max.js`, and a real target or fixture where a page fetches JSON after navigation. The fixture must prove that Camoufox returns the captured response through `/tab/network-captures`, not merely that the page loaded.

## Privacy and scope

Keep the response collector bounded and local. Do not write credentials, cookies, authorization headers, or full request bodies into reports. The router is an extraction layer, not a CAPTCHA solver, visual browser, or automatic Webtop executor; route those cases to the appropriate anti-bot/CDP skill.
