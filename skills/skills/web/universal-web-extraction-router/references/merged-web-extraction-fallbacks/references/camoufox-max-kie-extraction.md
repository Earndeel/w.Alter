# Camoufox Max API — dynamic public-page extraction

## Trigger

Use this variant when the standard browser facade fails after one attempt and `GET http://127.0.0.1:9377/health` reports `"flavor":"max"` with `browserConnected:true`.

## Contract observed

The Max server uses JSON `POST` routes, not the legacy `/tabs` API:

1. `POST /session/new` — body `{"userId":"walter"}`
2. `POST /tab/new` — body `{"userId":"walter","listItemId":"<stable-session-key>"}` → `tabId`
3. `POST /tab/navigate` — body `{"userId":"walter","tabId":"<id>","url":"<url>"}`
4. `POST /tab/snapshot` — body `{"userId":"walter","tabId":"<id>"}`
5. `POST /tab/evaluate` — body `{"userId":"walter","tabId":"<id>","expression":"..."}`
6. `POST /tab/screenshot` — body `{"userId":"walter","tabId":"<id>"}`; decode returned `buffer` from base64
7. `POST /tab/close` — same `userId` and `tabId`, in `finally`

## Extraction recipe

- Navigate with `domcontentloaded`; let the server readiness wait complete, then add a short delay for SPA hydration.
- Extract in one tab/session: final URL, title, `document.body.innerText`, headings, non-empty links, buttons, inputs, and script URLs via `/tab/evaluate`.
- Save the JSON and screenshot locally before analyzing. Use DOM text as evidence for exact labels/prices/URLs; use the screenshot only to validate layout and visible state.
- Always close the tab in `finally`; do not leave disposable extraction tabs alive.
- If the page is public but shows an incidental login popup, report it separately; do not infer that the main page requires authentication merely from the popup.

## Kie.ai validation example

For `https://kie.ai/gpt-5-6?model=gpt-5-6-sol`, the Max route returned HTTP 200, preserved the requested URL, and exposed hydrated page text plus a screenshot. The accessibility snapshot was empty, so DOM evaluation was the reliable extraction channel for this SPA.
