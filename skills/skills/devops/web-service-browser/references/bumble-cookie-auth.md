# Bumble Cookie Auth & Access

## Cookie Requirements

Bumble uses session-cookie-based auth. Key cookies from Mac Brave:

| Cookie | Domain | Secure | HttpOnly | Purpose |
|--------|--------|--------|----------|---------|
| session | .bumble.com | yes | yes | Main auth token (format: `s2:456:...`) |
| HDR-X-User-id | .bumble.com | yes | no | User ID header |
| aid | .bumble.com | no | no | Account ID (numeric) |
| device_id | .bumble.com | no | no | UUID device identifier |
| has_secure_session | .bumble.com | no | no | Session flag |
| session_cookie_name | .bumble.com | yes | no | Cookie name reference |
| buzz_lang_code | .bumble.com | no | no | Language preference |
| cpc | .bumble.com | no | no | Campaign tracking (URL-encoded JSON) |

## Camoufox Does NOT Work

Bumble's SPA JS bundles (manifest, vendor, main) load via HTTP 200 but never execute in Camoufox. The page stays on `.app-loading` spinner. `window.Bumble` remains `undefined`, `typeof React` returns `undefined`.

Root cause: Camoufox's Firefox-based engine with anti-detection patches breaks Bumble's JS runtime. Not a webdriver check (`navigator.webdriver === false`). Not a cookie issue (cookies are present and correct).

## Brave-in-Webtop Works

Launch Brave in webtop container (CDP 9224), inject cookies via Playwright `connect_over_cdp`, navigate to `https://bumble.com/app`. Page loads fully within 5-10s.

## Post-Login State

- Encounters/swipe screen with profile cards
- Left sidebar: match queue, conversations
- "End of the line" = daily profile limit (normal, not an error)
- Tailscale exit node to Mac IP recommended for residential IP

## Auth Flow

1. Extract cookies from Mac Brave SQLite (host_key LIKE '%bumble%')
2. Decrypt with AES-128-CBC (vault key: `macos/brave_keychain_key`)
3. Inject into Brave-in-webtop via Playwright `context.add_cookies()`
4. Navigate to `https://bumble.com/app`
5. No Cloudflare on Bumble (no cf_clearance needed)
