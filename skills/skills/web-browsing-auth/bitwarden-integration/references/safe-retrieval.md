# Safe Bitwarden credential retrieval

Use this procedure when a keyword can match more than one Bitwarden item.

## Procedure

1. Unlock and sync first. The local cache is not authoritative:
   ```bash
   BW_SESSION="$(~/.hermes/bin/bw-unlock --sync)"
   ```
2. Search `bw list items` by item name, username, and URI.
3. Emit metadata only: `id`, `name`, `username`, `uris`, `type`, and optionally `revisionDate`.
4. If there are multiple candidates, ask the user to select the exact account or item. Do not retrieve, compare, or display all candidate passwords.
5. Retrieve the selected field by stable item ID:
   ```bash
   bw get password "<selected_item_id>" --session "$BW_SESSION"
   ```
6. Return only the explicitly requested field, labelled with its account/domain. Never send the complete `bw get item` JSON to the chat; it may include passwords, TOTP URLs, notes, and custom fields.

## Why item IDs matter

Names and domains are not unique. A vault can contain duplicate logins, legacy entries, password-reset records, or separate accounts for the same service. Fuzzy retrieval by name can therefore return the wrong secret even when the command succeeds.

## Minimal metadata extractor

This pattern keeps secret fields out of diagnostic output:

```bash
bw list items --session "$BW_SESSION" | python3 -c '
import json, sys
needle = "<search_term>".lower()
for item in json.load(sys.stdin):
    login = item.get("login") or {}
    uris = " ".join((u.get("uri") or "") for u in login.get("uris", []))
    haystack = " ".join((item.get("name") or "", login.get("username") or "", uris)).lower()
    if needle in haystack:
        print({
            "id": item.get("id"),
            "name": item.get("name"),
            "username": login.get("username"),
            "uris": uris,
            "type": item.get("type"),
        })
'
```

Do not add passwords, master passwords, TOTP secrets, or session tokens to skills, logs, shell history, or diagnostic files.
