# LocalStorage Auth Extraction for SPA Sites

Modern SPA dashboards (One-API, New-API, Sub2API, aiprimetech.io, etc.) store auth in **LocalStorage**, not cookies. The SQLite Cookies table will be empty or contain only tracking cookies (Stripe, analytics).

## When to Use This

Trigger: cookie extraction returns only `__stripe_mid`, `_ga`, `_cf` — no auth cookies. The site is a SPA that stores JWT/token in localStorage.

## LevelDB Location (Mac Brave)

```
~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Local Storage/leveldb/
```

Files: `*.ldb` (data) + `*.log` (WAL). Both contain localStorage entries.

## Key Format

LevelDB stores localStorage as:
```
[0x00] [length_byte] [_https://DOMAIN] [0x00] [KEY_NAME] [0x00] [VALUE]
```

The `_https://` prefix is the origin. The `0x00` separates key from value.

## Extraction Script

```python
import os, re

leveldb_dir = "/tmp/brave-leveldb/"  # scp'd from Mac
domain = "aiprimetech.io"

for f in sorted(os.listdir(leveldb_dir)):
    if not f.endswith('.ldb') and not f.endswith('.log'):
        continue
    data = open(os.path.join(leveldb_dir, f), 'rb').read()
    
    pattern = f'_https://{domain}\x00'.encode()
    idx = 0
    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break
        key_start = idx + len(pattern)
        key_end = data.find(b'\x00', key_start)
        if key_end == -1 or key_end - key_start > 100:
            idx += len(pattern)
            continue
        key = data[key_start:key_end]
        
        val_start = key_end + 1
        val_end = val_start
        for i in range(val_start, min(val_start + 5000, len(data))):
            if data[i] == 0:
                val_end = i
                break
        val = data[val_start:val_end]
        
        try:
            key_str = key.decode('utf-8', errors='replace').strip('\x00\x01')
            val_str = val.decode('utf-8', errors='replace')
            if key_str and val_str:
                print(f"{key_str} = {val_str[:200]}")
        except:
            pass
        idx += len(pattern)
```

## Common SPA Auth Keys

| Key | Format | Description |
|---|---|---|
| `_token` | `rt_...` or `eyJ...` | JWT or refresh token |
| `auth_user` | JSON string | Full user object (id, email, role, balance) |
| `token_expires_at` | Unix timestamp (ms) | Token expiry |
| `session` | JSON or string | Session data |
| `access_token` | `eyJ...` | JWT access token |

## Injection into Camoufox

```python
import http.client, json, time

TAB = "<tab-id>"

def camoufox_eval(expression):
    conn = http.client.HTTPConnection("localhost", 9378, timeout=30)
    conn.request("POST", "/tab/evaluate", json.dumps({
        "tabId": TAB, "expression": expression
    }), {"Content-Type": "application/json"})
    return json.loads(conn.getresponse().read().decode())

# 1. Navigate to domain first (sets origin context)
# 2. Inject each key via localStorage.setItem
# 3. Reload page to trigger SPA auth check
# 4. Screenshot to verify logged-in state
```

## Pitfalls

- **SPA redirects to login despite valid token**: Backend API is likely down (502). Test: `curl -s https://domain/api/user/self -H "Authorization: Bearer TOKEN"`. If 502, server is broken — not a cookie issue.
- **`rt_` prefix tokens**: Refresh tokens, not access tokens. SPA exchanges them via API call. If API is down, refresh flow fails.
- **Token expiry**: Check `token_expires_at` (milliseconds). Expired = redirect to login.
- **Domain context**: Navigate to the domain BEFORE setting localStorage — `setItem` operates on the current origin.
- **LevelDB binary format**: Keys may have `\x01` prefix bytes (LevelDB internal). Strip non-printable characters.
- **Multiple `.ldb` files**: Entries can be spread across files. Search ALL of them.
