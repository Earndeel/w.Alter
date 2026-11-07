---
name: smmflare-integration
description: SMMFlare API integration — order social media services (views, likes, followers) via their REST API.
version: 1.0.0
author: W.Alter
tags: [smm, tiktok, social-media, api, marketing]
---

# SMMFlare Integration

SMM Panel for buying social media engagement (views, likes, followers, comments).

## API Key

Vault: `smmflare/api_key`
API URL: `https://smmflare.com/api/v2` (POST only)

## Endpoints

| Action | Params | Description |
|--------|--------|-------------|
| `balance` | key | Check account balance |
| `services` | key | List all services with IDs, prices, min/max |
| `add` | key, service, link, quantity | Place an order |
| `status` | key, order | Check order status |
| `refill` | key, order | Request refill |
| `cancel` | key, orders | Cancel orders |

## TikTok Services (as of 2026-05-30)

| Service ID | Name | Rate/1K |
|------------|------|---------|
| 9556 | Video Views [Instant] [Non-Drop] | $0.17 |
| 9579-9586 | Views (various quality/refill) | $0.01-0.05 |
| 9587-9595 | Likes (hidden, various refill) | $0.29-0.59 |
| 9574-9603 | Followers (various refill) | $2.40-3.99 |

## Usage

1. Get API key from vault: `vault get smmflare/api_key`
2. All calls are POST to `https://smmflare.com/api/v2`
3. Pass `key`, `action`, and action-specific params as form data

## Account Page Access (Cookie Extraction)

For actions requiring login (generate API key, add funds, check account details), follow the cookie extraction pipeline in `webtop-authenticated-browsing` skill → "Step 1: Extract Cookies from Mac Brave". Key steps specific to SMMFlare:

1. Copy Cookies DB from Mac: `ssh mac "cp ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies.db"`
2. Export SMMFlare cookies: `sqlite3 /tmp/brave-cookies.db "SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies WHERE host_key LIKE '%smmflare%'"`
3. Decrypt with vault key `macos/brave_keychain_key` — STRING (not decoded bytes) + PBKDF2(saltysalt, 1003, 16) + AES-128-CBC, skip first 16 bytes, extract ASCII
4. Required cookies: `PHPSESSID`, `hash`, `_identity_user`, `_usid`
5. Generate API key: GET account page → extract CSRF → POST `/account/newkey` with `_csrf` param
6. API key appears in response alert: `API key has been generated:<br>KEY_HERE`

See `references/smmflare-cookie-workflow.md` for the exact curl/python commands and decryption code.

## Pitfalls

- **Account needs credits** — balance starts at $0, add funds via smmflare.com/account before ordering
- **Service IDs change** — always call `services` first to get current IDs, don't hardcode
- **Rate is per 1K** — quantity=10000 with rate $0.17/1K costs $1.70
- **Link format** — use full TikTok URL (https://www.tiktok.com/@user/video/123...)
- **Refill policies vary** — some services have no refill, check `refill` field in services list
- **Cookie extraction for account page** — decrypt Brave cookies with vault key `macos/brave_keychain_key`, PBKDF2(saltysalt, 1003), AES-128-CBC, skip first 16 bytes of decrypted value
- **CSRF validation requires matching session** — the `_csrf` token must come from the SAME session (PHPSESSID) that submits the form. Fresh GET → extract CSRF → POST with same cookies. Stale CSRF → "Unable to verify your domain submission" (400)
- **POST `/account/newkey` returns 302 redirect** — success is a redirect to `/account`, not a JSON response. The API key appears in the HTML alert div, not in a field value (field shows `***` masked)
- **API key input field is masked** — `<input id="api_key" value="***">` — the actual key is in the alert message, not the input. Parse `API key has been generated:<br>([a-f0-9]+)` from the response HTML
- **Do NOT launch a second Brave instance on Mac** — it crashes the main Brave. Use cookie extraction + curl instead. See `webtop-authenticated-browsing` skill pitfall #21
- **AppleScript `do javascript` is disabled by default in Brave** — View > Developer > Allow JavaScript from Apple Events. Don't waste attempts — use curl with extracted cookies instead
