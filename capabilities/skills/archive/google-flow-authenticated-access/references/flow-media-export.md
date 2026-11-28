# Flow authenticated media export — operational reference

## Scope

Use this reference after the account check has proved that the active tab shows
`PRO`. It documents the verified recovery/export path; it is not a place to
store cookie values, tokens, balances, or media IDs.

## Fresh Brave cookie recovery

1. Copy the Mac Brave `Default/Cookies` SQLite file immediately before use.
2. Query only Google-related domains and fields needed for injection:
   `host_key`, `name`, `hex(encrypted_value)`, `path`, `is_secure`,
   `is_httponly`, `expires_utc`.
3. Use a shell-safe separator such as `|` in the remote `sqlite3` command and
   split on that separator locally. A command written with `-separator '\\t'`
   can deliver a literal backslash-plus-t over SSH and make the parser silently
   discard every row.
4. Derive the AES key from the vault-held Brave key with PBKDF2-HMAC-SHA1,
   salt `saltysalt`, 1003 iterations, 16-byte output.
5. For the verified Mac profile, cookie ciphertext starts with `v10`/`v11`.
   Strip that three-byte prefix; use the next 16 bytes as the IV and decrypt the
   remainder with AES-CBC. Remove valid PKCS#7 padding, discard the first
   garbage block, and keep only the printable cookie value. Do not log the
   decrypted value or derived key. Exclude analytics/telemetry cookies before
   injection.
6. Inject into a unique temporary Camoufox `userId`. A successful injection
   count is not an authentication proof: navigate Flow and require `PRO`; a
   page containing `header_sign_in` is still anonymous.

## Flow media export

After authentication, inspect the project and every `/edit/` page. Count actual
`<video>` elements and read their `currentSrc`; do not treat the number of edit
links as the number of generated videos. An image/reference edit page can be
listed beside a video edit page.

For each actual Flow video:

```text
POST /tab/fetch-binary
{
  "userId": AUTHENTICATED_USER,
  "tabId": LIVE_AUTHENTICATED_TAB,
  "url": "https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name=MEDIA_NAME"
}
```

The route must fetch through `page.context().request`, so the Playwright
context follows the redirect with its Google cookies. Restrict the route to
`labs.google` and `*.googleusercontent.com`; do not create a generic proxy.
Reject non-200 responses and unexpected content types before writing the file.

Verify a saved video with `ffprobe`, at minimum:

- duration
- width and height
- frame rate
- video/audio codecs
- byte size

Only then report the asset as locally delivered. Flow's `READY` marker, play
icon, or a DOM `<video>` with `readyState: 0` is not enough by itself.

## Service lifecycle warning

Camoufox authentication may live only in the browser context. Restarting the
systemd service can destroy the authenticated tab even when the Brave
`storage-state.json` file is empty. If a restart is unavoidable, plan a fresh
cookie extraction/injection immediately afterward and re-check `PRO` before
requesting media.
