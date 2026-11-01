## Step 1: Extract Cookies from Mac Brave

**Preferred: Keychain decryption** (works when main Brave has no CDP — which is the normal case).

```python
import hashlib, json, subprocess
from Crypto.Cipher import AES

# 1. Copy cookies DB from Mac
subprocess.run(["ssh", "mac", "cp ~/Library/Application\\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies-main.db"], check=True)

# 2. Export encrypted cookies for target domain
result = subprocess.run(["ssh", "mac", 'sqlite3 /tmp/brave-cookies-main.db "SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies WHERE host_key LIKE \'%target_domain%\'"'], capture_output=True, text=True)

# 3. Get Keychain key from vault
key = subprocess.run(["vault", "get", "macos/brave_keychain_key"], capture_output=True, text=True).stdout.strip().encode()
derived_key = hashlib.pbkdf2_hmac('sha1', key, b'saltysalt', 1003, dklen=16)

def decrypt(hex_str):
    enc = bytes.fromhex(hex_str)
    if enc[:3] == b'v10': enc = enc[3:]
    elif enc[:4] == b'v11': enc = enc[4:]
    iv, data = enc[:16], enc[16:]
    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
    dec = cipher.decrypt(data)
    pad = dec[-1]
    if 1 <= pad <= 16 and all(b == pad for b in dec[-pad:]): dec = dec[:-pad]
    clean = dec[16:] if len(dec) > 16 else dec
    return bytes(b for b in clean if 32 <= b <= 126).decode('ascii', errors='replace')

# 4. Decrypt and convert to Playwright format
cookies = []
for line in result.stdout.strip().split('\n'):
    parts = line.split('|')
    if len(parts) < 7: continue
    host, name, enc_hex, path, secure, httponly, expires = parts
    val = decrypt(enc_hex)
    c = {"name": name, "value": val, "domain": host, "path": path, "secure": secure=='1', "httpOnly": httponly=='1'}
    if expires and int(expires) > 0: c["expires"] = (int(expires)/1000000) - 11644473600
    cookies.append(c)

# 5. Save ALL cookies and AUTH-ONLY cookies separately
with open("/tmp/brave-cookies-all.json", "w") as f: json.dump(cookies, f)

# Filter auth cookies (exclude Cloudflare, analytics)
EXCLUDE = {'cf_clearance', '__cf_bm', '_cfuvid', '_ga', '_gcl_au'}
auth_cookies = [c for c in cookies if not any(c['name'].startswith(p) for p in ['_ga', '_gcl', '_cf', '__cf']) and c['name'] not in EXCLUDE]
with open("/tmp/brave-auth-cookies.json", "w") as f: json.dump(auth_cookies, f)
```

**See**: `references/macos-cookie-decryption.md` for full decryption analysis and Keychain access methods.
**See**: `references/northwest-registered-agent.md` for NWRA-specific Keycloak auth flow, SPA behavior, and document download patterns.

**Fallback: CDP extraction** (only when main Brave has `--remote-debugging-port` enabled — rare):

```python
import asyncio, json, subprocess, time, http.client
proc = subprocess.Popen(["ssh", "-o", "StrictHostKeyChecking=no", "-L", "19222:localhost:9222", "-N", "mac"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
async def extract():
    import websockets
    conn = http.client.HTTPConnection("localhost", 19222)
    conn.request("GET", "/json/version")
    ws_url = json.loads(conn.getresponse().read())["webSocketDebuggerUrl"].replace("ws://localhost:9222", "ws://localhost:19222")
    async with websockets.connect(ws_url, max_size=50*1024*1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        return json.loads(await ws.recv())["result"]["cookies"]
cookies = asyncio.run(extract())
proc.terminate()
```

**localStorage tokens** (Tinder, etc.): attach to specific tab via `Target.attachToTarget` → `Runtime.evaluate("localStorage.getItem('key')")`.

## Pitfalls

### Cookie Expires Format (Chrome Epoch)
Chrome/Brave stores cookie expires as **microseconds since 1601-01-01** (Chrome epoch).
Camoufox/Playwright expects **Unix seconds** or `-1` for session cookies.

**Conversion**:
```python
for c in cookies:
    exp = c.get("expires")
    if exp is not None and isinstance(exp, (int, float)):
        if exp > 0:
            c["expires"] = int((exp / 1000000) - 11644473600)
        else:
            del c["expires"]  # session cookie
```

Without conversion: `browserContext.addCookies: Cookie should have a valid expires`.

### Cloudflare Cookie Injection Rule

**NEVER inject `cf_clearance` from one browser into another.**

**Correct approach**: Inject ONLY auth cookies (session tokens, Keycloak, PHPSESSID), then let the target browser navigate to the site and obtain its OWN `cf_clearance` automatically. If the site still blocks, use `solve_cloudflare=True` on the target browser.

## Cookie Extraction Fallback (SQLite)

When Mac Brave has no `--remote-debugging-port` (main session never started with CDP), the Step 1 websocket approach fails. Fallback: read cookies directly from the SQLite DB on Mac.

```bash
# Copy Cookies DB from Brave profile
ssh lucasjouvencon@100.127.150.1 "cp ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Cookies /tmp/brave-cookies.db"

# Export encrypted cookie metadata (host, name, path, flags)
ssh lucasjouvencon@100.127.150.1 "sqlite3 /tmp/brave-cookies.db \"SELECT host_key, name, hex(encrypted_value), path, is_secure, is_httponly, expires_utc FROM cookies\""
```

### Keychain Decryption Blocker

Cookie values are AES-128-CBC encrypted. The key is stored in macOS Keychain under `"Brave Safe Storage"` / account `"Brave"`. **The Keychain blocks non-GUI access via SSH** — `errSecInteractionNotAllowed` (-25308) even with correct password. This is an ACL on the specific item, not the keychain itself.

**Error codes decoded** (2026-05-24 tested):
- **Error 36** (errSecInteractionNotAllowed): ACL blocks non-interactive access. This is the persistent failure mode via SSH, even with `osascript ... with administrator privileges`. The `set-key-partition-list` workaround does NOT resolve this for Brave Safe Storage items.
- **Error 44** (errSecItemNotFound): The search list doesn't include `login.keychain-db`. Fix: `security list-keychains -d user -s ~/Library/Keychains/login.keychain-db /Library/Keychains/System.keychain` — but this only helps if error 36 is also resolved.

**Workaround options (in order of preference)**:
1. Ask Monsieur to run `security find-generic-password -s "Brave Safe Storage" -a "Brave" -w` in a local Terminal and paste the result — **only reliable method, use this first**
2. If vault already has `macos/brave_keychain_key` from a previous session, skip extraction entirely
3. Read unencrypted metadata only (host, name, path, flags) — enough for some OSINT but not for authenticated browsing

**Note**: `security dump-keychain` CAN list the entry without the password (shows service name, account, dates), but `find-generic-password -w` CANNOT read the secret value. The `-g` flag does not help via SSH.

### Getting the Keychain Password (2026-05 tested)

**Most reliable (100% success):** Ask Monsieur to run on his Mac terminal:
```bash
security find-generic-password -s "Brave Safe Storage" -a "Brave" -w
```
He pastes the result (e.g., `«secret:vault»`). Store in vault as `macos/brave_keychain_key`.

**Automated via osascript with credentials (UNRELIABLE — 2026-05-24 tested, consistent failure):**
```bash
MAC_PASS=$(vault get macos/lucas_password 2>/dev/null)
osascript -e "do shell script \"security find-generic-password -s \\\"Brave Safe Storage\\\" -a \\\"Brave\\\" -w\" user name \"lucasjouvencon\" password \"$MAC_PASS\" with administrator privileges"
```
This approach returns error 36 (errSecInteractionNotAllowed) consistently. The `set-key-partition-list` workaround does NOT fix the ACL for this item. Do NOT spend more than 2-3 attempts — go directly to asking the user to run the command locally.

### Decrypt Formula (once you have the key)

```python
import hashlib, json
from Crypto.Cipher import AES

# The keychain value is the PBKDF2 password (NOT the raw AES key)
keychain_value = b'<from keychain>'  # e.g. b'«secret:vault»'
derived_key = hashlib.pbkdf2_hmac('sha1', keychain_value, b'saltysalt', 1003, dklen=16)

def decrypt_cookie(encrypted_hex):
    enc = bytes.fromhex(encrypted_hex)
    # Strip v10 (3 bytes) or v11 (4 bytes) prefix
    if enc[:3] == b'v10': enc = enc[3:]
    elif enc[:4] == b'v11': enc = enc[4:]

    # First 16 bytes = IV (domain-shared nonce), remaining = ciphertext
    iv = enc[:16]
    data = enc[16:]

    cipher = AES.new(derived_key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(data)

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16 and all(b == pad_len for b in decrypted[-pad_len:]):
        decrypted = decrypted[:-pad_len]

    # CRITICAL: first 16 bytes are always garbled (wrong IV derivation).
    # All cookies in the same domain share the same first ciphertext block,
    # producing the same garbled prefix. The actual value starts at byte 16.
    if len(decrypted) > 16:
        clean = decrypted[16:]
    else:
        clean = decrypted  # very short cookie, value may be in first block

    # Extract only printable ASCII
    return bytes(b for b in clean if 32 <= b <= 126).decode('ascii')
```

**Why the first 16 bytes are garbled**: Brave/Chrome on macOS stores a per-domain nonce as the first 16 bytes of encrypted data (all cookies in the same domain share this block). The PBKDF2-derived key decrypts blocks 2+ correctly via CBC chaining, but the first block requires the correct IV which is not the standard `b' ' * 16`. Skipping the first 16 bytes of decrypted output reliably extracts the clean cookie value.

See `references/macos-cookie-decryption.md` for the full analysis of the encryption scheme.
