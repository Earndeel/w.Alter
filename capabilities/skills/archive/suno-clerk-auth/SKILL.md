---
name: suno-clerk-auth
description: "Suno AI music platform — Clerk auth cookie extraction and session management for authenticated browsing."
tags: [suno, clerk, auth, cookies, music, browsing]
platforms: [linux]
triggers:
  - suno login
  - suno account
  - suno cookie
  - suno browse
  - clerk auth
---

# Suno Clerk Auth

Suno uses **Clerk** for authentication. Session state spans 3+ domains. Extract cookies from Mac Brave → inject into Camoufox (webtop port 9378) → navigate.

## Auth Architecture

| Domain | Key Cookies | Purpose |
|--------|-------------|---------|
| `suno.com` | `__session`, `clerk_active_context`, `has_logged_in_before` | Main app session |
| `.suno.com` | `__client_uat`, `__client_uat_Jnxw-muT`, `__stripe_mid/sid` | Client auth tokens, Stripe |
| `auth.suno.com` | `__client`, `__client_Jnxw-muT` | Clerk provider tokens |
| `studio-api.prod.suno.com` | `sessionid` | Studio API session |

## Cookie Extraction

Standard Brave SQLite + Keychain decryption pipeline. Filter for `host_key LIKE '%suno%'`.

**Auth-critical cookies** (must inject all domains):
- `suno.com` → `__session`, `clerk_active_context`
- `auth.suno.com` → `__client`, `__client_Jnxw-muT`
- `.suno.com` → `__client_uat`, `__client_uat_Jnxw-muT`
- `studio-api.prod.suno.com` → `sessionid`

**Excludable** (analytics, not needed for auth):
- `_ga`, `_ga_*`, `_gcl_au`, `_dd_s`, `ajs_anonymous_id`, `IR_*`, `prelude_dispatch_id`

After filtering analytics, expect ~17 auth cookies.

## Injection + Verification

```python
# Inject auth cookies
POST /sessions/walter/cookies → {"ok": true, "count": 17}

# Navigate — redirects to /discover when authenticated
POST /tabs {"userId": "walter", "sessionKey": "suno-main", "url": "https://suno.com"}
# → URL becomes "https://suno.com/discover"

# Verify: screenshot should show sidebar with username + credits
# Look for: avatar, username, "N Credits" counter, "Upgrade to Pro" button
```

## UI Landmarks

- Sidebar: "Home", "Explore", "Create", "Studio", "Library", "Hooks", "Notifications"
- Prompt box: "Describe the song you want to make"
- Credits display in sidebar header
- Model version banner (v5.5 as of 2026-05)

## Pitfalls

1. **Clerk multi-domain**: Must inject cookies from ALL 3+ domains (suno.com, auth.suno.com, .suno.com, studio-api.prod.suno.com). Missing auth.suno.com cookies → redirect to login.
2. **`__client` and `__client_Jnxw-muT`**: Both variants needed — Clerk uses A/B test bucketing for cookie names.
3. **Session expiry**: Clerk sessions are shorter-lived than typical web sessions. If Camoufox shows login page, cookies are stale — re-extract from Mac Brave.

## Related Skills

- `webtop-authenticated-browsing` — full pipeline (extract → inject → navigate → interact)
- `songwriting-and-ai-music` — Suno prompt engineering for music generation
