# LocalStorage Extraction from Brave/Chrome (SPA Auth)

## Why
Modern SPA dashboards (One-API, New-API, aiprimetech.io, etc.) store auth in **LocalStorage**, not cookies. The SQLite `Cookies` table will be empty or contain only tracking cookies (e.g. `__stripe_mid`). Session tokens, JWTs, `auth_user` JSON, and `refresh_token` values live in the LevelDB-backed Local Storage.

## When to suspect LocalStorage auth
- SQLite cookies table has 0-1 entries for the domain (only trackers)
- The site is a Vue/React/Next.js SPA
- The domain uses patterns like `auth_user`, `refresh_token`, `access_token` in its JS

## Extraction via SSH (no LevelDB parser needed)

The LevelDB `.log` files contain recent writes in plaintext. Use `strings` to extract:

```bash
ssh mac '
BASE="$HOME/Library/Application Support/BraveSoftware/Brave-Browser/Default/Local Storage/leveldb"
cd "$BASE"
strings *.log *.ldb 2>/dev/null | grep -B 1 -A 1 -iE "TARGET_DOMAIN" | head -100
'
```

### Targeted extraction (get auth_user JSON):
```bash
ssh mac '
BASE="$HOME/Library/Application Support/BraveSoftware/Brave-Browser/Default/Local Storage/leveldb"
cd "$BASE"
strings *.log 2>/dev/null | grep -B 1 -A 1 -iE "TARGET_DOMAIN" | head -100
'
```

The output format is:
```
"_https://TARGET_DOMAIN
KEY_NAME
{"id":1234,"email":"user@example.com","balance":17.83,...}
META:https://TARGET_DOMAIN
```

Key = second line after the `_https://DOMAIN` marker. Value = third line (often JSON).

## Multiple snapshots = timeline

LevelDB `.ldb` files are compacted snapshots. Multiple entries for the same key show **historical values** — useful for tracking balance changes over time (e.g. aiprimetech `auth_user.balance` decreasing with each API call).

## Pitfalls

1. **`.log` files are volatile** — Brave may compact them to `.ldb` at any time. Copy immediately.
2. **`.ldb` files are binary** — `strings` works but may miss some entries. For full extraction, use `plyvel` (Python LevelDB bindings) — but it requires `libleveldb-dev` which may not be on the Mac.
3. **Brave buffers LocalStorage in RAM** — recent writes may not be on disk yet. The user must have the page open/loaded for the data to be written.
4. **Don't try to install plyvel on the VPS to read Mac LevelDB** — the build requires `libleveldb-dev` headers which may be missing. `strings` on the raw files is sufficient for most extraction tasks.
5. **This is NOT a substitute for cookies** — some sites use both. Check cookies first (faster), fall back to LocalStorage if cookies are empty.

## Real-world example: aiprimetech.io / Sub2API (One-API style)

- Domain: `aiprimetech.io`
- Auth mechanism: `auth_token` (JWT) + `refresh_token` + `auth_user` JSON in LocalStorage
- **`_token` key** (`rt_...` prefix) = refresh token, NOT the access token
- **`auth_token` key** = actual JWT used for API calls (`Bearer eyJhbG...`)
- After login via browser, SPA stores all three. The old `_token` may persist alongside the new `auth_token` — always read `auth_token` for API calls.
- API key (`sk-...`): separate from dashboard auth — only for LLM calls, NOT for usage/billing endpoints
- Dashboard API: `/api/v1/keys` returns masked keys (`«secret:vault»`). Full keys only shown in "Use Key" modal.
- Cost monitoring: read `auth_user.balance` from successive LevelDB snapshots to track spend over time without browser access.

## Injecting auth into Camoufox (SPA login pattern)

When you have credentials (email/password) or extracted tokens:

```python
# 1. Navigate to site first (domain context required for localStorage)
camoufox("POST", f"/tab/navigate", {"tabId": TAB, "url": "https://site.com"})
time.sleep(3)

# 2. Inject localStorage values
for key, value in [("auth_token", jwt), ("refresh_token", rt), ("auth_user", json_str)]:
    camoufox("POST", f"/tab/evaluate", {"tabId": TAB,
        "expression": f"localStorage.setItem('{key}', '{value}')"})
    time.sleep(0.3)

# 3. Reload to trigger SPA re-auth
camoufox("POST", f"/tab/navigate", {"tabId": TAB, "url": "https://site.com/dashboard"})
time.sleep(5)
```

**Pitfall**: If the API backend returns 502, the SPA will redirect to login regardless of valid tokens. Check API health first: `curl -s https://site.com/api/user/self -H "Authorization: Bearer <jwt>"`.

## Extracting masked API keys from dashboards

SPA dashboards (One-API, Sub2API, AIPrimeTech) mask API keys in both DOM and API responses. The "Use Key" / "Configure" modal typically shows the full key in a code block for copy-paste.

1. Navigate to API Keys page in Camoufox
2. Click "Use Key" or equivalent button for the target key
3. Take a **screenshot** of the modal (`GET /tab/screenshot`)
4. Use `vision_analyze` to read the full key from the screenshot — vision models read the full unmasked string even when the DOM serves `«secret:vault»`

```python
# Take screenshot of the "Use Key" modal
screenshot_b64 = camoufox("GET", f"/tab/screenshot?tabId={TAB}")
with open("/tmp/api-key-modal.png", "wb") as f:
    f.write(base64.b64decode(screenshot_b64["screenshot"]))
# Then: vision_analyze("/tmp/api-key-modal.png", "Read the EXACT full API key strings")
```

**Pitfall**: The DOM `<code>` blocks and API `/api/v1/keys` response both return masked keys. Only the visual rendering in the modal shows full keys. Don't waste time trying to extract from DOM or API — go straight to screenshot + vision.
