# SMMFlare Cookie Extraction → API Key Generation

Exact workflow tested 2026-05-30.

## Step 1: Extract Encrypted Cookies from Mac

```bash
ssh lucasjouvencon@100.127.150.1 \
  "cp ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies.db && \
   sqlite3 /tmp/brave-cookies.db \"SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies WHERE host_key LIKE '%smmflare%'\""
```

Expected cookies: `_ppref`, `_usid`, `PHPSESSID`, `_csrf`, `g_state`, `hash`, `_identity_user`

## Step 2: Decrypt Cookies (Python)

```python
import hashlib, binascii
from Crypto.Cipher import AES

# Key from vault: vault get macos/brave_keychain_key
# USE THE STRING AS-IS (not base64-decoded)
keychain_str = "«secret:vault»"  # example
derived_key = hashlib.pbkdf2_hmac('sha1', keychain_str.encode('utf-8'), b'saltysalt', 1003, dklen=16)

def decrypt(hex_val):
    enc = binascii.unhexlify(hex_val)
    if enc[:3] == b'v10': enc = enc[3:]
    elif enc[:4] == b'v11': enc = enc[4:]
    iv = b' ' * 16
    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
    pt = cipher.decrypt(enc)
    pad = pt[-1]
    if 1 <= pad <= 16 and all(b == pad for b in pt[-pad:]):
        pt = pt[:-pad]
    # Skip first 16 bytes (domain-shared garbled block)
    clean = pt[16:] if len(pt) > 16 else pt
    return bytes(b for b in clean if 32 <= b <= 126).decode('ascii')
```

## Step 3: Build Cookie String

Required cookies for SMMFlare auth:
- `PHPSESSID` — session ID (e.g., `io7efp1ftqg9uqjos8tq0qq4f2`)
- `hash` — serialized PHP hash (URL-encoded)
- `_identity_user` — serialized PHP user ID (URL-encoded)
- `_usid` — serialized PHP UUID (URL-encoded)

```python
import urllib.parse
cookies = f"PHPSESSID={phpsessid}; hash={urllib.parse.unquote(hash_raw)}; _identity_user={urllib.parse.unquote(identity_raw)}; _usid={urllib.parse.unquote(usid_raw)}"
```

## Step 4: Generate API Key

```bash
# GET account page → extract CSRF
curl -s -c /tmp/sj.txt -b "$COOKIES" "https://smmflare.com/account" > /tmp/sp.html
CSRF=$(grep -oE 'name="_csrf" value="[^"]+"' /tmp/sp.html | tail -1 | sed 's/.*value="//;s/"//')

# POST to generate key (must use same cookies + CSRF from same session)
curl -s -b /tmp/sj.txt -b "$COOKIES" \
  -H "Referer: https://smmflare.com/account?account-main=timezone-api-tab" \
  -H "Origin: https://smmflare.com" \
  -X POST "https://smmflare.com/account/newkey" \
  --data-urlencode "_csrf=$CSRF" -L
```

Success = 302 redirect to `/account`. API key appears in HTML alert:
```
API key has been generated:<br>«secret:vault»
```

Extract with: `grep -oE "API key has been generated:<br>[a-f0-9]+" | grep -oE "[a-f0-9]+$"`

## Common Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `Unable to verify your domain submission` (400) | CSRF mismatch or stale session | Fresh GET + extract CSRF + POST with same cookie jar |
| API key field shows `***` | Masked in HTML input | Parse the alert div, not the input field |
| Empty response | Session expired | Re-extract cookies from Brave DB |
| Second Brave crashes main | Two instances conflict | Never launch brave-walter while main Brave is running |
