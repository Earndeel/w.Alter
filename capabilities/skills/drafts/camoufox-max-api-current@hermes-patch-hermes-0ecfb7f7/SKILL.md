---
name: camoufox-max-api-current
description: Verified contract and smoke test for the active Camoufox Max HTTP server on localhost:9377.
---

# Camoufox Max current API

Use this skill when testing or calling the active host-side Camoufox Max server.

## Verified runtime

- Server file: `/root/.hermes/camoufox-max/server-max.js`
- Base URL: `http://127.0.0.1:9377`
- Health: `GET /health`
- The primary contract uses singular `/tab` and `/session` routes.
- Compatibility aliases for legacy `/tabs` and `/sessions/...` are enabled in
  `server-max.js` so already-loaded Hermes workers do not fail with `404`.
- Hermes' maintained adapter is `/root/.hermes/hermes-agent/tools/browser_camofox.py`;
  it should use the singular routes and only fall back to legacy responses while
  a worker is being reloaded.

## Endpoints

All action endpoints are JSON `POST` requests:

- `/tab/new` — payload `{userId, listItemId}`; returns `tabId`
- `/tab/navigate` — payload `{userId, tabId, url}`
- `/tab/snapshot` — payload `{userId, tabId}`
- `/tab/screenshot` — payload `{userId, tabId}`; returns base64 PNG in `buffer`
- `/tab/click` — payload `{userId, tabId, ref}`
- `/tab/type` — payload `{userId, tabId, ref, text}`
- `/tab/scroll` — payload `{userId, tabId, direction}`
- `/tab/evaluate` — payload `{userId, tabId, expression}`
- `/tab/close` — payload `{userId, tabId}`
- `/session/cookies` — payload `{userId, cookies}`

## Smoke test

1. `GET /health`; require HTTP 200 and JSON `ok: true`.
2. `POST /tab/new` with a unique test `userId` and `listItemId`; retain returned `tabId`.
3. `POST /tab/navigate` to `https://example.com`; require HTTP 200 and `ok: true`.
4. `POST /tab/screenshot`; require HTTP 200, `ok: true`, and a PNG base64 buffer.
5. Always `POST /tab/close` in cleanup, including after failures.

A successful lifecycle must also verify a usable `snapshot` and non-empty
`refs` when the target page contains semantic or interactive elements.

## Scoped network and authenticated-state checks

- If a dedicated VPN exit refuses to start because the Mac already owns its key, do not disconnect or force the Mac tunnel. Check the existing session-scoped Mac proxy and the Mac's public country first; an already-working French exit can satisfy the task without any global routing change. Verify the country again from inside the exact browser session before account navigation.
- Use the official `browser_session`/`walter-browser login` broker for cookie transfer, with server-side site scoping and metadata-only results. When a tenant subdomain has no cookies, inspect cookie host/name metadata for the necessary parent-domain session cookie before declaring authentication impossible; never export cookie values into the agent context or include unrelated tenants.
- A broker's `authenticated: false` based on a UI selector is not definitive. Read the live account menu and enrollment UI; a placeholder display name can coexist with a valid authenticated account. Distinguish actual enrollment data from an anonymous SPA shell, and do not launch assessments while verifying access.

## Snapshot compatibility

Camoufox/Playwright Firefox in this runtime does not expose
`page.accessibility.snapshot()`. `server-max.js` therefore falls back to a DOM
snapshot that emits visible semantic/interactive elements and assigns
`data-ref` references for click/type operations. Do not classify
`[no accessibility tree available]` as an acceptable final result.

## Dynamic-page extraction workflow

For a public, content-heavy page, separate UI verification from content extraction:

1. Navigate with `browser_navigate`, then capture `browser_snapshot(full=true)` to verify the live route and visible controls.
2. Use the snapshot to inventory navigation, model selectors, tabs, pricing, and footer content; use `browser_click` on the current refs before assuming a tab is inactive.
3. For complete editorial content, retrieve the page HTML as a secondary source and parse semantic sections, headings, tables, hidden accordion answers, structured data, links, images, and video sources. Dynamic pages often SSR the README and JSON-LD even when the active UI tab remains Playground.
4. Preserve discrepancies instead of normalizing them: for example, a `model=...-sol` URL can still initialize the Playground with Luna. Report both the URL-selected model and the UI default.
5. Treat marketing claims, official-provider benchmark/pricing tables, and platform pricing as separate categories. Label the source of each figure in the extraction.
6. Deliver a durable Markdown extraction when the page is long; include the source URL, UI state, full text, tables, API example, FAQ/JSON-LD, links, and images.

A reusable extraction checklist and the Kie.ai smoke-test observations are in
`references/dynamic-page-extraction.md`.

For approved Google Flow video generation, reference-conditioned clips, current lazy media tiles, signed exports and final QA, see `references/flow-omni-current-ui.md`.
