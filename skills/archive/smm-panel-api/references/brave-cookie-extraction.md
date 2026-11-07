# Brave Cookie Extraction & Decryption (macOS)

Extract and decrypt cookies from Brave Browser on macOS for programmatic authentication to web services.

## Architecture

Brave (Chromium-based) encrypts cookies using:
- **Key:** macOS Keychain → `Brave Safe Storage` → PBKDF2(saltysalt, 1003, 16) → AES-128-CBC key
- **Prefix:** `v10` (3 bytes) before ciphertext
- **IV:** 16 spaces (`b' ' * 16`)
- **Database:** `~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies`

## Step 1: Get Encryption Key from Vault

The vault stores the raw Keychain password as a string (base64-encoded). Use it as the PBKDF2 password directly — do NOT base64-decode it first.

```python
import base64, hashlib, binascii
from Crypto.Cipher import AES

key_b64 = vault.get("macos/brave_keychain_key")  # e.g. "{{bw:W.Alter · macos:field:brave_keychain_key}}"
password = key_b64.encode('utf-8')  # STRING, not decoded bytes
salt = b'saltysalt'
dk = hashlib.pbkdf2_hmac('sha1', password, salt, 1003, dklen=16)
iv = b' ' * 16
```

## Step 2: Extract Encrypted Cookies

```bash
ssh mac "sqlite3 ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies \
  \"SELECT name, hex(encrypted_value) FROM cookies WHERE host_key LIKE '%example.com%'\""
```

## Step 3: Decrypt

```python
for name, hex_val in cookies:
    enc = binascii.unhexlify(hex_val)
    assert enc[:3] == b'v10', "Unexpected prefix"
    ct = enc[3:]  # skip v10
    cipher = AES.new(dk, AES.MODE_CBC, iv)
    pt = cipher.decrypt(ct)
    # Strip PKCS7 padding
    pad = pt[-1]
    if 1 <= pad <= 16 and all(b == pad for b in pt[-pad:]):
        pt = pt[:-pad]
    # Skip first 16 bytes — IV mismatch produces garbage in block 0
    value = pt[16:].decode('utf-8', errors='replace')
```

## Pitfalls

- **Key must be used as STRING, not decoded bytes.** `key_b64.encode('utf-8')` is correct. `base64.b64decode(key_b64)` produces wrong key.
- **First 16 bytes are always garbage.** The IV (16 spaces) doesn't match the original encryption IV, so block 0 decrypts to junk. Skip it with `pt[16:]`.
- **PHPSESSID values** look like `io7efp1ftqg9uqjos8tq0qq4f2` (alphanumeric, ~26 chars).
- **Yii2 framework cookies** (used by SMM panels) are serialized: `hash%3A2%3A%7Bi%3A0%3Bs%3A4%3A%22_csrf%22%3B...`. URL-decode to read.
- **Session cookies expire.** PHPSESSID is ephemeral — if Brave was restarted, the old session may be invalid. Always test with a GET request before using cookies for POST.
- **Copy DB while Brave is running:** `cp ~/.../Cookies /tmp/cookies_copy.db` — SQLite locks the DB, so copy first.
- **User ID in cookies:** `_identity_user` contains `[USER_ID, "", EXPIRY]`. Extract user ID for API calls.

## CSRF Token Handling (Yii2/SMM Panels)

SMM panels use Yii2 framework which validates CSRF tokens strictly:

1. **GET the page first** to get a fresh CSRF token from the HTML
2. **POST with proper headers:** `Referer: https://site.com/page`, `Origin: https://site.com`
3. **Include all session cookies**, not just PHPSESSID
4. CSRF tokens are one-use — each POST invalidates the current token

```bash
# Correct pattern
curl -s -c jar.txt -b "PHPSESSID=xxx; hash=yyy; _identity_user=zzz" \
  "https://site.com/account" | grep -oE 'name="_csrf" value="[^"]+"' | tail -1

curl -s -b jar.txt -b "PHPSESSID=xxx; hash=yyy; _identity_user=zzz" \
  -H "Referer: https://site.com/account" \
  -H "Origin: https://site.com" \
  -X POST "https://site.com/account/newkey" \
  --data-urlencode "_csrf=TOKEN"
```

## Tested With

- SMMFlare (smmflare.com) — Yii2 PHP framework
- Brave Browser 148.x on macOS
