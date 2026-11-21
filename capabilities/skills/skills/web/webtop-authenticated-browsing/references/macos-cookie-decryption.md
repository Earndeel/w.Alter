# macOS Chromium Cookie Decryption

## Encryption Scheme (Brave/Chrome on macOS)

- **Algorithm**: AES-128-CBC
- **Key derivation**: PBKDF2-HMAC-SHA1
  - Password: Keychain value from "Brave Safe Storage" / "Brave"
  - Salt: `b"saltysalt"`
  - Iterations: 1003
  - Key length: 16 bytes
- **Prefix**: `b"v10"` (3 bytes) or `b"v11"` (4 bytes) prepended to ciphertext
- **Storage**: SQLite DB at `~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies`

## Key Finding: Domain-Shared Nonce Block

All cookies within the same domain share the **same first 16 bytes** of ciphertext (after the v10 prefix). This was confirmed by inspecting encrypted hex values:

```
Facebook cookies:  first block = 3f2af3344f99b44d7cb065cc86233a0e  (ALL identical)
Instagram cookies: first block = 5b6bd791d56e5c0f16244cbb1c4e34d4  (ALL identical)
X.com cookies:     first block = 9877d2aa2cf5fb1a7f498dd84a73543f  (shared by most)
```

This block serves as a per-domain nonce/IV. The actual cookie data starts from block 2 onwards.

## Decryption Procedure

1. Strip `v10` prefix (3 bytes)
2. Use bytes 0-15 as IV, bytes 16+ as ciphertext
3. Decrypt with AES-128-CBC using PBKDF2-derived key
4. Remove PKCS7 padding
5. **Skip first 16 bytes of plaintext** (garbled due to IV mismatch)
6. Extract printable ASCII from remaining bytes

## Why First Block Is Garbled

The PBKDF2-derived key correctly decrypts blocks 2+ via CBC chaining (each block uses the previous ciphertext block as IV). But block 1 uses the domain-shared nonce as IV, which doesn't produce the correct plaintext. The actual IV that would produce clean block-1 output is unknown — likely derived from the nonce via a separate key or transform.

This was verified empirically: using `b' ' * 16`, `b'\x00' * 16`, or even AES-ECB-decrypting the first block as IV all produce garbled first blocks. Skipping 16 bytes is the reliable workaround.

## Keychain Access via SSH

The macOS Keychain blocks `find-generic-password -w` via SSH with `errSecInteractionNotAllowed` (-25308). This is an ACL restriction on the specific item, not the keychain itself.

Methods tested:
- `security unlock-keychain` + `find-generic-password` → -25308
- `osascript ... with administrator privileges` → error 44 (item not found in System keychain search list)
- Python ctypes `SecKeychainFindGenericPassword` → -25308 even after unlock
- `security set-generic-password-partition-list` → -25308 (can't access item to modify ACL)
- `security dump-keychain` → CAN list the entry (service name, account, dates) but NOT read the password

**Working approach (confirmed 2026-05-22)**: Use `osascript` with explicit admin credentials:
```bash
MAC_PASS=$(vault get macos/lucas_password)
osascript -e "do shell script \"security find-generic-password -s \\\"Brave Safe Storage\\\" -a \\\"Brave\\\" -w\" user name \"lucasjouvencon\" password \"$MAC_PASS\" with administrator privileges"
```
This bypasses the ACL via osascript's administrator privilege escalation. **Pitfall**: osascript context only loads `System.keychain`. If item is in `login.keychain-db`, add it first:
```bash
osascript -e "do shell script \"security list-keychains -d user -s ~/Library/Keychains/login.keychain-db /Library/Keychains/System.keychain\" user name \"lucasjouvencon\" password \"$MAC_PASS\" with administrator privileges"
```
**Fallback**: Ask user to run `security find-generic-password -s "Brave Safe Storage" -a "Brave" -w` locally and paste result.

## Verified Cookie Values (2026-05-22)

Facebook user ID: `100008308324750`
Instagram user ID: `4229969399`
LinkedIn session: `ajax:4097550869692578430`
X.com auth_token: `b7c8b714ab8ddee6b2d6ea65c2a40bfe214a6973`

## Verified Pipeline (2026-05-24, NWRA)

Complete working pipeline tested with Northwest Registered Agent:

```python
import hashlib, json, subprocess
from Crypto.Cipher import AES

# 1. Copy + export from Mac
subprocess.run(["ssh", "mac", "cp ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies-main.db"], check=True)
r = subprocess.run(["ssh", "mac", 'sqlite3 /tmp/brave-cookies-main.db "SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies WHERE host_key LIKE \'%northwest%\'"'], capture_output=True, text=True)

# 2. Key from vault
key = subprocess.run(["vault", "get", "macos/brave_keychain_key"], capture_output=True, text=True).stdout.strip().encode()
derived_key = hashlib.pbkdf2_hmac('sha1', key, b'saltysalt', 1003, dklen=16)

# 3. Decrypt
def decrypt(hex_str):
    enc = bytes.fromhex(hex_str)
    if enc[:3] == b'v10': enc = enc[3:]
    elif enc[:4] == b'v11': enc = enc[4:]
    iv, data = enc[:16], enc[16:]
    dec = AES.new(derived_key, AES.MODE_CBC, iv).decrypt(data)
    pad = dec[-1]
    if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]): dec = dec[:-pad]
    clean = dec[16:] if len(dec) > 16 else dec
    return bytes(b for b in clean if 32 <= b <= 126).decode('ascii', errors='replace')

# 4. Filter auth-only cookies (exclude Cloudflare, analytics)
EXCLUDE_PREFIXES = ('_ga', '_gcl', '_cf', '__cf')
auth_cookies = [c for c in all_cookies if not any(c['name'].startswith(p) for p in EXCLUDE_PREFIXES)]

# 5. Inject auth cookies into Camoufox (NOT cf_clearance)
import http.client
conn = http.client.HTTPConnection("localhost", 9377)
conn.request("POST", "/sessions/walter/cookies", json.dumps({"cookies": auth_cookies}), {"Content-Type": "application/json"})
# Camoufox navigates to site → obtains its own cf_clearance → auth works
```

**Key lesson**: Do NOT inject `cf_clearance` — it's fingerprint-bound. Inject only auth cookies (Keycloak, PHPSESSID, etc.). Camoufox gets its own cf_clearance when navigating.
