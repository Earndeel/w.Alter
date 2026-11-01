# LocalStorage Extraction from Brave LevelDB

Some services (notably **aiprimetech.io**) use LocalStorage for auth/state instead of cookies. The cookie injection pipeline does NOT work for these. Instead, read the cached state directly from LevelDB.

## When to use

- Service uses LocalStorage auth (no session cookies to inject)
- You only need to READ account state (balance, profile) without interacting
- Faster than launching a full browser session (~5s vs ~30s)

## Technique: Direct LevelDB string extraction

LevelDB stores data as append-only records. `strings` extracts readable JSON blobs.

```bash
# 1. Extract all entries for a domain
ssh lucasjouvencon@100.127.150.1 "cd ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Local\ Storage/leveldb && strings *.ldb *.log 2>/dev/null | grep -i 'DOMAIN'"

# 2. Parse JSON objects with Python (on Mac via SSH)
ssh lucasjouvencon@100.127.150.1 "cd ~/Library/Application\ Support/BraveSoftware/Brave-Browser/Default/Local\ Storage/leveldb && python3 -c \"
import os, re
data = b''
for f in sorted(os.listdir('.'), key=os.path.getmtime):
    if f.endswith('.ldb') or f.endswith('.log'):
        data += open(f, 'rb').read()

# Find JSON blobs for the domain
for m in re.finditer(rb'_https://DOMAIN\.TLD.*?({\\\"id\\\".*?})', data):
    print(m.group(1).decode('utf-8', errors='replace')[:500])
\""
```

## aiprimetech.io specifics

- **Auth key in localStorage**: `auth_user` (JSON object with full account state)
- **Access token**: `auth_token` key (JWT `eyJhbG...`) — this is what the API uses for `Bearer` auth
- **Refresh token**: `refresh_token` key (`rt_...` prefix) — NOT the access token
- **Legacy key**: `_token` may also contain a refresh token (old format, may coexist with `auth_token`)
- **Also stores**: `sub2api_login_agreement_consent`, `channel-status-auto-refresh`
- **JSON fields**: id, email, username, role, balance, concurrency, status, allowed_groups, last_active_at, created_at, updated_at, balance_notify_enabled, balance_notify_threshold_type, total_recharged, rpm_limit, identities
- **Multiple snapshots exist** in LevelDB (append-only) — use the LAST match for most recent state, or sort by `updated_at` field
- **Account**: earndeel@gmail.com, ID 3401
- **API endpoints**: `/api/v1/keys` (masked keys), `/api/v1/user/self` (profile). All use Bearer JWT from `auth_token`.
- **API key masking**: Dashboard masks keys in DOM (`{{bw:W.Alter · ANTHROPIC_AUTH_TOKEN:field:ANTHROPIC_AUTH_TOKEN}}`) and API responses. Full keys only visible in "Use Key" modal → use **screenshot + vision_analyze** to extract. See `references/api-key-extraction.md` in `camoufox-social-scrape`. **Full API key extraction & usage details**: See `references/aiprimetech-api.md`.

## Gotchas

1. **LevelDB is binary** — `strings` output contains garbage around JSON. Parse with regex, don't assume clean lines.
2. **Multiple historical values** — LevelDB keeps old values until compaction. The LAST occurrence is most recent.
3. **No need to authenticate** — if you just need to read cached state (balance, profile), LevelDB extraction is sufficient without opening a browser.
4. **Brave must have visited recently** — stale LevelDB may have outdated balance. Check `updated_at` timestamp.
5. **This does NOT work for interaction** — if you need to click buttons, submit forms, or navigate authenticated pages, you still need a full browser session with proper auth.

## Known LocalStorage-auth services

| Service | Domain | Key(s) | Notes |
|---------|--------|---------|-------|
| aiprimetech | aiprimetech.io | `auth_user`, `auth_token`, `refresh_token` | Sub2API gateway. `auth_token` = JWT for API. `refresh_token` = `rt_...` prefix. |

## Injecting auth into Camoufox (SPA login with email/password)

When localStorage extraction fails or tokens are expired, log in via the browser:

```python
# 1. Navigate to login page
camoufox("POST", "/tab/navigate", {"tabId": TAB, "url": "https://site.com/login"})
time.sleep(3)

# 2. Fill form via JS evaluate (snapshot may return no accessibility tree for some SPAs)
camoufox("POST", "/tab/evaluate", {"tabId": TAB,
    "expression": """
        const inputs = document.querySelectorAll('input');
        inputs[0].focus(); inputs[0].value = 'email@example.com';
        inputs[0].dispatchEvent(new Event('input', {bubbles: true}));
        inputs[1].focus(); inputs[1].value = 'password';
        inputs[1].dispatchEvent(new Event('input', {bubbles: true}));
        inputs[2].click(); // consent checkbox
    """})
time.sleep(1)

# 3. Submit via Playwright locator (NOT CSS :has-text — that's Playwright only)
camoufox("POST", "/tab/click_text", {"tabId": TAB, "text": "Log in", "tag": "button"})
time.sleep(5)  # Wait for redirect to dashboard
```

**Pitfall**: `:has-text()` is a Playwright selector, not CSS. The evaluate endpoint uses CSS only. Use `document.querySelectorAll('button').forEach(...)` for JS-based clicking, or the `/tab/click_text` endpoint for Playwright-style text matching.

**See also**: `camoufox-social-scrape` skill → `references/localstorage-extraction.md` for the full Sub2API auth flow and API key extraction via screenshot.

## aiprimetech additional notes

- Auth: OAuth only (Google, GitHub, Discord). Registration disabled (invite code required)
- SPA config (`window.__APP_CONFIG__`): `registrationEnabled: false`, `oauthProviders: ["google","github","discord"]`
- User account: earndeel@gmail.com, ID 3401
