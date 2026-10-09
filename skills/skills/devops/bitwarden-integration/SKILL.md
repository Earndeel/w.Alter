---
name: bitwarden-integration
description: Bitwarden self-hosted integration with W.Alter — vault registration, bw CLI workflow, credential search, and authenticated browsing via cookie injection.
version: 1.1.0
author: W.Alter
license: MIT
metadata:
  hermes:
    tags: [credentials, bitwarden, vault, security, browsing]
---

# Bitwarden Integration

Self-hosted Bitwarden (Personal Vault / bw CLI) integrated with W.Alter's credential chain.

## Architecture

```
W.Alter Vault (vault.json.age)
  └─ bitwarden/master_password  →  bw-unlock --sync
  └─ bitwarden/server_url       →  bw config server
  └─ bitwarden/email            →  bw login
       ↓
  Bitwarden Vault (986 items)
       ↓
  Credential search / retrieval
       ↓
  Use: API calls, browser injection, service config
```

## Vault Registration

Bitwarden credentials MUST be in the Hermes vault, not hardcoded or session-only.

```bash
# Register Bitwarden in vault (one-time setup)
vault add bitwarden master_password "<master_password>"
vault add bitwarden server_url "https://lucas-bitwarden.duckdns.org"
vault add bitwarden email "lucas.jouvencon@gmail.com"
```

**Pitfall**: If the master password only exists in session memory or Hindsight, it's fragile and non-transferable. Always register in the vault.

## Unlock Workflow

```bash
# Preferred: unlock + sync (pulls latest items from server)
BW_SESSION=$(~/.hermes/bin/bw-unlock --sync)

# Or manual:
BW_PASS=$(vault get bitwarden/master_password)
BW_SERVER=$(vault get bitwarden/server_url)
bw config server "$BW_SERVER"
export BW_SESSION=$(bw unlock --raw "$BW_PASS")
bw sync --session "$BW_SESSION" >/dev/null 2>&1  # REQUIRED before search
```

Helper: `~/.hermes/bin/bw-unlock` supports `--print` (unlock only), `--sync` (unlock + sync), `--check` (status).

## Encrypted Backup

Create a portable encrypted JSON export after syncing. Store it with restrictive permissions and never create a plaintext CSV/JSON backup:

```bash
umask 077
mkdir -p "$HOME/.hermes/backups/bitwarden"
BW_SESSION=$(~/.hermes/bin/bw-unlock --sync)
BW_PASS=$(vault get bitwarden/master_password)
out="$HOME/.hermes/backups/bitwarden/bitwarden-$(date -u +%Y%m%dT%H%M%SZ).json"
export BW_SESSION
bw export --password "$BW_PASS" --format encrypted_json --output "$out"
unset BW_SESSION BW_PASS
chmod 600 "$out"
```

The export is protected by the password supplied to `--password` (here, the Bitwarden master password). Verify the file is valid JSON, has `passwordProtected: true` and `encrypted: true`, and is mode `0600` before reporting success.

**CLI version pitfall**: on current CLI versions, `bw export <password>` fails with `too many arguments`; use the explicit `--password <password>` option even though some `bw export --help` examples show a positional password.

## Diagnosing a Blank Vault Across Clients

When the iPhone, browser extension, and desktop app all appear empty, first prove whether the server vault is empty. Do not delete local app data or reinstall anything before making an encrypted export.

1. **Establish server truth.** Run `bw-unlock --sync`, then count/list only non-secret metadata through `bw list items`; a successful fresh sync with items proves the vault was not silently deleted. Compare the account email and server URL from `bw status` with the clients.
2. **Inspect the Mac client without dumping secrets.** For Bitwarden Desktop, inspect only metadata from `~/Library/Application Support/Bitwarden/data.json`: active account ID, `global_config_byServer`, `global_account_accounts`, the matching `..._ciphers_ciphers` count, and `..._sync_lastSync`. Never print this file: it contains access tokens, encrypted keys, and encrypted vault data. Review `app.log` for `decrypt complete`, `invalid type: JsValue`, `Unhandled error in angular`, or repeated sync failures.
3. **Compare versions.** Record the desktop/extension version and `/api/config` `server.name`/`version`. A current client can authenticate and sync successfully while the UI fails during decryption when paired with an older Vaultwarden/web-vault release. The known 2026.7.0 regression is documented in `references/vaultwarden-client-compatibility.md`.
4. **Prefer the non-destructive fix.** Update Vaultwarden to a release compatible with the installed clients (Vaultwarden v1.37.0+ is required for Bitwarden clients v2026.7.0+), then relaunch and sync. If the server cannot be updated immediately, use a compatible client version such as 2026.6.1 as a temporary workaround. Logout/login or reinstall may help some clients but is inconsistent; do not present it as the primary fix.
5. **Verify all clients after the fix.** Confirm the same server URL/account on each client, force sync, and verify item counts. Keep the encrypted export until every client displays the vault normally.

See `references/vaultwarden-client-compatibility.md` for the concrete error signature, version matrix, and upstream references.

## Self-hosted Vaultwarden Server Recovery

Use `references/vaultwarden-recovery.md` when a self-hosted Vaultwarden server needs a client-compatibility update but host SSH access is blocked. The verified class-level workflow is: establish server truth and make an encrypted export; identify the exact GCP instance and zone; snapshot the boot disk with a lowercase name; recover access with a dedicated temporary key/user while preserving existing metadata; fall back to a temporary startup script plus controlled reset when metadata SSH is ignored; update only the Vaultwarden Compose service while preserving its data mount; verify `/api/config`, `/alive` HTTP 200, Docker health, and the image's OCI version; then restore metadata and remove every temporary credential.

Operational guardrails: prefer CLI/API over GUI automation; if TCC or screen capture makes automation unreliable, switch to one short manual command at a time. Never use `set -e` in an interactive Cloud Shell block, never paste browser `@url:` metadata into the shell, and never report success from a GCP `Updated` line without a real SSH login and service-level checks.

## TOTP / MFA Retrieval

```bash
# Get current TOTP code for an item (by ID)
bw get totp "<item_id>" --session "$BW_SESSION"

# Get the TOTP secret (base32) from an item's otpauth:// URL
bw get item "<item_id>" --session "$BW_SESSION" | python3 -c "
import json, sys, re
item = json.load(sys.stdin)
totp_url = item.get('login', {}).get('totp', '')
m = re.search(r'secret=([A-Z0-9]+)', totp_url)
print(m.group(1) if m else 'NO TOTP')
"
```

**Helper: `~/.hermes/bin/aws-mfa`** — returns current 6-digit MFA code for AWS earndeel@gmail.com. Uses `bw-unlock --sync` + `bw get totp`. Item ID: `e790ded6-19e5-47a1-9998-25c7692131bf`.

**Pitfall**: TOTP codes rotate every 30s. Always call `bw get totp` at the moment you need the code, not ahead of time.

## Credential Search

**CRITICAL: `bw sync` is REQUIRED before any search.** The local cache does NOT auto-update. Items added on other devices (or via the web vault) are invisible until `bw sync` is run. Use `bw-unlock --sync` which combines unlock + sync in one step.

### List all items (names + usernames)
```bash
bw list items --session "$BW_SESSION" | python3 -c "
import json, sys
items = json.loads(sys.stdin.read())
for item in items:
    login = item.get('login', {})
    username = login.get('username', '') if login else ''
    print(f'{item[\"name\"]:40s} {username}')
"
```

### Search by keyword (name, domain, URI)
```bash
bw list items --session "$BW_SESSION" | python3 -c "
import json, sys
items = json.loads(sys.stdin.read())
keyword = '<search_term>'.lower()
for item in items:
    name = item.get('name', '').lower()
    login = item.get('login', {})
    uris = login.get('uris', []) if login else []
    uri_str = ' '.join([u.get('uri','') for u in uris]).lower()
    if keyword in name or keyword in uri_str:
        print(f'{item[\"name\"]:40s} {login.get(\"username\",\"\")}')
"
```

### Get specific credential
```bash
bw get username "<item_name>" --session "$BW_SESSION"
bw get password "<item_name>" --session "$BW_SESSION"
```

### Safe retrieval when several items match
Searches may return duplicate domains, old entries, reset-password entries, or multiple accounts. Never choose the first match and never print the full `bw get item` JSON: it can contain passwords, notes, TOTP secrets, and custom fields.

1. After syncing, show only non-secret metadata: item ID, name, username, URI, type, and (if useful) revision date.
2. If more than one candidate remains, ask Monsieur to select the exact account/entry before retrieving a secret. Do not compare or reveal passwords for all candidates.
3. Retrieve only the selected item by stable item ID, not by a fuzzy name:
   ```bash
   bw get password "<selected_item_id>" --session "$BW_SESSION"
   ```
4. Return only the requested field, and mention the associated username/domain so the credential is not confused with a duplicate. A direct password request is sufficient authorization to retrieve that password; do not expose unrelated fields.

A concise, reusable version of the metadata-first workflow is in `references/safe-retrieval.md`.

## Creating Items

```bash
bw get template item --session "$BW_SESSION" | python3 -c "
import sys, json, base64
item = json.load(sys.stdin)
item['name'] = 'Service Name'
item['login'] = {
    'username': 'user@example.com',
    'password': 'the_secret',
    'uris': [{'match': None, 'uri': 'https://service.com'}],
    'totp': None
}
item['fields'] = [{'name': 'extra_field', 'value': 'extra_value', 'type': 0}]
print(base64.b64encode(json.dumps(item).encode()).decode())
" | bw create item --session "$BW_SESSION" --raw
```

## Authenticated Browsing via Cookie Injection

When a site requires authentication and you have Brave cookies on a remote Mac:

1. **Extract cookies** via SSH: `sqlite3 ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Cookies "SELECT ..."`
2. **Decrypt** with AES key from Keychain: `vault get macos/brave_keychain_key`
3. **Inject into Camoufox**: `context.add_cookies(pw_cookies)`
4. **Navigate**: authenticated session ready

See `references/cookie-injection-patterns.md` in `vault-lookup` skill for the full AES decryption workflow.

## Pitfalls

- **`bw sync` REQUIRED before search**: The local SQLite cache does NOT auto-sync. Items created/updated on other devices are invisible until `bw sync` runs. ALWAYS use `bw-unlock --sync` or call `bw sync` explicitly before `bw list items` or `bw get item`. This bit us: AWS MFA entry existed in Bitwarden but was invisible without sync.
- **Session expiry**: `bw unlock --raw` sessions expire. If `bw list` hangs or returns auth error, re-unlock.
- **Interactive hang**: `bw unlock` without `--raw` and without piped input hangs. Always use `--raw`.
- **JSON parsing error**: `bw create item` expects base64-encoded stdin, NOT raw JSON.
- **Template required**: Use `bw get template item` before creating items.
- **Type mapping**: 1=Login, 2=Secure Note, 3=Card, 4=Identity. Fields: 0=Text, 1=Hidden, 2=Boolean.
- **No Xiaomi entry**: As of 2026-06-09, no Xiaomi/MiMo entry exists in Bitwarden. Xiaomi auth was via browser cookies.
- **vault-lookup overlap**: This skill covers Bitwarden-specific workflows. For the full credential search chain (vault → env → bw → project files), see `vault-lookup`.
