# Discord Authenticated Read-Only Browsing via Camoufox

Use this flow when the user's authenticated Discord session lives in Mac Brave but all navigation must happen on the remote Camoufox host.

## Hard boundary

- Never connect Playwright/Scrapling to the user's main Mac Brave for navigation.
- Never launch a second Brave/Chromium window with a copied Mac profile. A copied profile can still create visible tabs and disturb the live session.
- Treat Mac Brave as a passive source only: read the SQLite `Cookies` database and, if needed, the Discord Local Storage LevelDB over SSH.
- Keep cookie/token values in memory only. Do not print them, write plaintext token files, or include them in logs.
- Keep the workflow read-only. Do not send Discord messages, react, join servers, or change settings.

## Why cookies alone may fail

Discord commonly stores the web authentication value in Chromium Local Storage rather than in an auth cookie. The Cookies table may contain only `__dcfduid`, `__sdcfduid`, and related session/anti-bot cookies. The actual value is commonly stored under the Local Storage key `token` for the origin marker `_https://discord.com`.

## Extraction pattern

1. Over SSH, read the Mac profile's `Default/Local Storage/leveldb/` files (`*.ldb` and `*.log`) without opening the browser.
2. Locate the Discord origin marker and the `token` key. A current user-token-shaped candidate is the three-segment ASCII value immediately associated with that key; do not print it. If multiple candidates exist, select only the one directly adjacent to the Discord `token` record and retain a short hash/length for diagnostics.
3. Separately extract and decrypt only Discord cookies if the Brave Safe Storage key is already available through the approved vault path. Exclude `cf_clearance`, `__cf_bm`, and `_cfuvid`; those are fingerprint-bound and should not cross browsers.
4. Pass the values directly from the SSH subprocess into the Camoufox API client. Do not save a cookie JSON or token file on the VPS.

## Camoufox-Max API sequence

Always call `/health` first. The live Max server may be on 9377 even when older documentation says 9378. Use the port that reports `flavor: max`.

1. Optional cookie import for Max uses the Max route, not the old browser-server route:
   `POST /session/cookies` with `{"userId":"<user>","cookies":[...]}`.
2. Create a tab:
   `POST /tab/new` with `{"userId":"<user>","listItemId":"discord-readonly"}`.
3. Navigate to Discord:
   `POST /tab/navigate` with `{"userId":"<user>","tabId":"<tab>","url":"https://discord.com/app"}`.
4. After the Discord origin has loaded, inject the token in the page context using the JSON-string form Discord expects:
   `localStorage.setItem('token', JSON.stringify(<token-string>))`
   Do not store the raw token value without `JSON.stringify`; Discord may remain on the login page.
5. Navigate/reload Discord again, then verify with `/tab/snapshot` or `/tab/evaluate` that the login form is absent and the authenticated app/server UI is present.

## Discord SPA navigation

- `/tab/evaluate` is useful for bounded DOM reads such as `document.body.innerText` and for extracting channel links.
- For channel links, prefer a fresh `/tab/snapshot`, identify the current `eN` ref for the target link, then use the compatible click route `POST /tabs/<tabId>/click` with `{"userId":"<user>","ref":"eN"}`. Refs expire after every navigation; never reuse an old ref.
- Direct `/tab/navigate` can exceed the client timeout on Discord's heavy SPA even when the browser remains healthy. After a timeout, query `/health`, then request a fresh snapshot/body from the same tab before retrying; do not blindly create another tab or launch another browser.
- `document.body.innerText` is often more complete than the accessibility snapshot for long announcement cards. Restrict extraction to the requested channel and bound the returned text.

## Verification and cleanup

- Verify the exact channel title and announcement author/date before reporting content.
- Treat `general` as a separate channel; it may contain only join messages while a private support/announcement channel contains product announcements.
- After the read-only task, close the isolated Camoufox session with `DELETE /sessions/<userId>` and verify `/health` reports zero active sessions. This removes the in-memory browser context containing the injected token and cookies.
- Report the remote method and cleanup status briefly; never report the token, cookie values, or personal session identifiers.
