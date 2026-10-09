# Brave Cookie Extraction & Decryption

## Why
Mac Brave has logged-in sessions for Facebook, Instagram, LinkedIn, etc. The main Brave instance (PID with cookies) has NO remote debugging. The W.Alter instance (port 9226) has NO cookies. Solution: extract cookies from SQLite DB, decrypt, inject into Camoufox.

## Extraction (via SSH)
```bash
# Copy cookies DB (read-only)
ssh mac "cp ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies.db && chmod 644 /tmp/brave-cookies.db"

# Query target domains
ssh mac "sqlite3 /tmp/brave-cookies.db \"SELECT host_key, name, hex(encrypted_value), path, is_secure, expires_utc FROM cookies WHERE host_key LIKE '%facebook%' OR host_key LIKE '%instagram%' OR host_key LIKE '%linkedin%'\""
```

## Keychain Password
The encryption key is stored in macOS Keychain under "Brave Safe Storage" / account "Brave".
Direct `security find-generic-password -w` fails via SSH (errSecInteractionNotAllowed / -25308).

**Most reliable method (2026-05 tested):** Ask Monsieur to run directly on his Mac terminal:
```bash
security find-generic-password -s "Brave Safe Storage" -a "Brave" -w
```
He sends the result (e.g., `«secret:vault»`). This is the **PBKDF2 password** for decryption.

**Automated method (unreliable):** `osascript` with administrator privileges:
```bash
ssh mac "osascript -e 'do shell script \"security find-generic-password -s \\\"Brave Safe Storage\\\" -a \\\"Brave\\\" -w\" user name \"lucasjouvencon\" password \"$MAC_PASS\" with administrator privileges'"
```
Get `$MAC_PASS` from vault: `vault get macos/lucas_password`

**Known issue:** `osascript` with `with administrator privileges` runs with only System.keychain in the search list. Adding login keychain explicitly sometimes helps:
```bash
osascript -e 'do shell script "security list-keychains -d user -s ~/Library/Keychains/login.keychain-db /Library/Keychains/System.keychain && security find-generic-password -d user -s \"Brave Safe Storage\" -a \"Brave\" -w" user name "lucasjouvencon" password "$MAC_PASS" with administrator privileges'
```
**Reality (2026-05-22):** This often returns `errSecAuthFailed` (exit 36) or `-25308`. The direct-on-Mac method is 100% reliable — use it as the primary approach. Don't burn 15+ attempts trying osascript variants.

The returned value (e.g., `«secret:vault»`) is the **PBKDF2 password**, not the raw AES key.

## Decryption (AES-128-CBC)
```python
import hashlib
from Crypto.Cipher import AES

kdf_password = b'<keychain_value>'  # UTF-8 bytes of the keychain string
derived_key = hashlib.pbkdf2_hmac('sha1', kdf_password, b'saltysalt', 1003, dklen=16)
iv = b' ' * 16  # 16 space characters

# Strip "v10" prefix (3 bytes), then decrypt
encrypted = bytes.fromhex(hex_value)
data = encrypted[3:]  # remove v10 prefix
cipher = AES.new(derived_key, AES.MODE_CBC, iv)
decrypted = cipher.decrypt(data)
# Remove PKCS7 padding
pad_len = decrypted[-1]
decrypted = decrypted[:-pad_len]
```

## The First-Block Bug
The first 16 bytes of decrypted output are ALWAYS garbled. The actual cookie value starts at byte 16+.

**Root cause:** All cookies in the same domain share the same first ciphertext block (deterministic encryption). The IV (16 spaces) doesn't correctly XOR with the intermediate value for block 1. After block 1, CBC self-corrects.

**Fix:** Strip the first 16 bytes, then extract clean ASCII:
```python
import re
clean_bytes = decrypted[16:]
clean_value = re.sub(rb'[^\x20-\x7e]+', b'', clean_bytes).decode('utf-8', errors='ignore')
```

## Injection into Camoufox
```python
cookies = []
for host, name, value, path, secure, expires in decoded_cookies:
    cookies.append({
        "name": name,
        "value": value,
        "domain": host,
        "path": path,
        "secure": bool(secure),
        "httpOnly": True,
        "sameSite": "Lax"
    })

conn = http.client.HTTPConnection("localhost", 9377)
conn.request("POST", "/tabs/<tab_id>/set_cookies",
    json.dumps({"userId": "walter", "sessionKey": "osint", "cookies": cookies}),
    {"Content-Type": "application/json"})
```

## Verification
After injection, navigate to each platform and check login state:
- Facebook: `https://www.facebook.com/` — look for feed, not login form
- Instagram: `https://www.instagram.com/` — look for stories/feed
- LinkedIn: often session-expired, cookies may be stale

## Pitfalls
- **NEVER open tabs on Mac Brave CDP** — it creates visible pop-ups that disturb Monsieur
- Instagram and LinkedIn sessions expire faster than Facebook
- `strict=False` needed when parsing cookie-related JSON (control chars in values)
- The Keychain password may change if Monsieur changes his Mac password
