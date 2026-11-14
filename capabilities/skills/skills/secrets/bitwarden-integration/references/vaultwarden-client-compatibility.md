# Vaultwarden / Bitwarden Client Compatibility

## Reproduction pattern

A Vaultwarden-backed account can authenticate and complete synchronization while the Bitwarden UI remains blank or stuck on loading placeholders. The desktop log may show:

```text
[CipherService]: decrypt complete ... [ [ 'Items', 1018 ] ]
Unhandled error in angular Error: Error: invalid type: JsValue(Object(...))
```

The failure is client-side during post-sync decryption/rendering, not evidence that the server deleted the vault.

## Confirmed session evidence (2026-08-05)

- Fresh `bw-unlock --sync` succeeded and `bw list items` returned 990 visible items.
- The Mac Bitwarden Desktop local store had over 1,000 cipher records and a current `..._sync_lastSync` value.
- Bitwarden Desktop and the Brave Chromium extension were both version `2026.7.0`.
- The server `/api/config` identified `server.name` as `Vaultwarden` and reported web-vault version `2025.12.0`.
- The Mac `app.log` showed successful decrypt passes followed by the `invalid type: JsValue(Object(...))` Angular error.

Do not dump `data.json` or full logs: they can contain access tokens, encrypted keys, and encrypted vault payloads. Inspect counts, URLs, versions, timestamps, and sanitized error signatures only.

## Upstream evidence

- Vaultwarden issue #7495 documents the same `invalid type: JsValue(Object(...)), expected a string` blank-vault failure with Bitwarden browser extension `2026.7.0`: https://github.com/dani-garcia/vaultwarden/issues/7495
- The Vaultwarden release notes explicitly state that the update to v1.37.0 is required for support with Bitwarden clients v2026.7.0 and newer: https://github.com/dani-garcia/vaultwarden/releases

## Remediation order

1. Preserve an encrypted `encrypted_json` export with restrictive permissions.
2. Update Vaultwarden to v1.37.0 or newer, then restart/sync clients.
3. If the server cannot be updated immediately, use a compatible client version such as Bitwarden `2026.6.1` temporarily.
4. Logout/login or reinstall only as a secondary client-side experiment; reports are mixed, and it must not replace the server update.
5. Recheck every client against the exact same server URL and account email, then keep the backup until the vault renders normally.
