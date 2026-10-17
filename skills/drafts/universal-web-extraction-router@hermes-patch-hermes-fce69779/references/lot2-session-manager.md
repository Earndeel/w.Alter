# Lot 2 — Session Manager (BrowseSession)

Implemented and validated 2026-08-11. First-class, engine-agnostic session
abstraction for walter_browse. `network = local` is ALWAYS the default;
VPN/proxy is per-session and opt-in only. The host network is never changed.

## Architecture

```
browse_session.py (SessionManager + BrowseSession)
   ├── identity: anonymous | personal | temporary | account:<x>
   ├── network:  local (DEFAULT) | vpn | proxy   (country: FR/US/...)
   ├── persistent: False (temporary, TTL 30 min) | True (explicit save)
   ├── storage:   <HERMES_HOME>/cache/walter-sessions/<id>/
   │                state.json (metadata, no secrets)
   │                storage-state.json (Playwright storageState: cookies+origins)
   └── engine:    resolved at acquisition, never baked into the session
        ├── Camoufox Max: userId = "session-<id>" (isolated browser context)
        ├── HTTP replay:  cookies_for_domain() scoped to the endpoint domain
        └── (future)      personal Chrome via CDP

Camoufox MAX is the warm browser pool: one browser process, one context per
session userId. New contexts in the warm browser: ~14 ms each. Warm
re-acquisition: ~1 ms.
```

## API

```python
manager = SessionManager()                      # root = ~/.hermes/cache/walter-sessions

s = manager.create(identity="anonymous", persistent=False, network="local")  # DEFAULT
s = manager.create(identity="personal", persistent=True, session_id="opp")
loaded = manager.load("opp")
saved   = manager.save(s, storage_state={"cookies": [...], "origins": [...]})
manager.destroy(sid)                            # live + disk (explicit)
manager.expire_stale()                          # cleans expired temporaries
manager.list_sessions()                         # dedup by id, metadata only

# Cookie scoping for HTTP replay (point 8):
from browse_session import cookies_for_domain
scoped = cookies_for_domain(jar, endpoint_domain)  # only what the endpoint needs
```

CLI: `--session-id`, `--identity`, `--persistent`, `--network`, `--country`,
`--session-save`. When none of the session flags is passed, the Lot 1 path is
byte-for-byte unchanged (measured overhead ≈ 0 ms).

## Proven behaviours (real tests, 2026-08-11)

1. **Isolation** (`proof_session_isolation.py`): two SIMULTANEOUS sessions,
   cookie `foo=A` vs `foo=B` for the same domain, navigated through the real
   Camoufox browser: A sees `{foo: A}`, B sees `{foo: B}`. `ISOLATION_OK`.
2. **local + VPN FR simultaneously** (`proof_local_vpn.py`): session A exits on
   the host IP (129.150.52.60), session B on NordVPN France
   (187.13.197.204) via the `nordvpn-proxy` container HTTP proxy
   (127.0.0.1:1080, session-scoped `proxy` in `/session/new`). Host IP
   unchanged. `LOCAL_VPN_PREUVE: OK`.
3. **Persistent save/load** (`--session-id persist-demo --persistent
   --session-save`): create → save → load → list round-trip works.
4. **Personal import**: `import_cookies_file('/tmp/cookies-opp.json')`
   → 121 cookies, identity=personal, authenticated=True, summary has no
   values.
5. **localStorage**: written in a session context, read back, exported via
   `/session/state` (origin + localStorage entries).
6. **HTTP replay with session cookies** (`proof_replay_session_cookie.py`):
   `cookies_for_domain()` forwards ONLY the endpoint-domain cookies (2/3
   unrelated cookies dropped). Log hygiene: no secret value in summary, logs,
   or traces.
7. **Lifecycle cleanup**: temporary sessions destroyed on exit/expiry;
   persistent sessions never destroyed accidentally.

## Camoufox MAX server additions

- `POST /session/new` accepts optional `proxy: {server, username?, password?}`
  — proxy is scoped to that session's browser context (Playwright
  `newContext(proxy=...)`). Firefox does NOT support SOCKS auth in contexts,
  so use the HTTP proxy (tinyproxy on 127.0.0.1:1080, no auth required
  locally) for session-scoped geo routing.
- `GET /session/state?userId=...` returns the full Playwright storageState
  (cookies + localStorage origins) with stats (counts only). Cookie values
  are part of the payload (they ARE the session state) but are never logged
  by Python-side code; traces show counts and names only.

## Security / log hygiene

- `BrowseSession.summary()`: metadata only — never cookie values, tokens,
  localStorage content, or headers.
- `redact_cookies_for_log()`: name/domain/httpOnly/secure + sensitive-flag,
  no values.
- `log_event()`: skips kwargs named cookies/values/storage/headers/token.
- `cookies_for_domain()`: the ONLY bridge from session storage to HTTP
  replay; callers never forward the whole jar.
- Cookie files are stored on disk (as before: the old system kept them in
  /tmp too) under the session root with the host's file permissions; they are
  file-backed by explicit `save` only for persistent sessions.

## Pitfalls

1. `localStorage.setItem(...)` returns `undefined`; `page.evaluate` then
   omits `result` → the Python client raises "evaluation omitted result".
   Combine the write+read in one expression.
2. Firefox/Playwright contexts reject SOCKS5 **with authentication**. Use the
   HTTP proxy (no auth on loopback) for per-session geo routing.
3. `list_sessions()` must dedupe by id (live + disk) or persisted sessions
   appear twice.
4. Temporary sessions always get `expires_at`; persistent sessions `None`.
   `expire_stale()` only touches temporaries.
5. Server endpoints added to `server-max.js` require a server restart
   (start via `/root/.hermes/scripts/start-camoufox-max.sh`).

## Benchmarks (2026-08-11)

| Operation | Latency |
|---|---|
| Session create (cold) | 0.1 ms |
| Session load (warm, persisted) | 0.04 ms |
| Destroy | 0.04 ms |
| New browser context in warm Camoufox pool | ~14 ms each (3 → 41 ms) |
| Warm context re-acquisition | ~1 ms each (3 → 4 ms) |
| CLI without session (Lot 1 path) | probe 215–224 ms (unchanged) |
| CLI with session (overhead) | probe 213–227 ms (≈ 0 added) |

## Migration strategy (old → new)

Old system: ad-hoc `/tmp/cookies-*.json` files and a single shared Camoufox
`userId`. Migration is incremental and non-breaking:

1. `import_cookies_file(manager, "/tmp/cookies-opp.json", session_id=...)`
   copies an old file into a named persistent session (one-time step).
2. New `walter_browse` calls may pass `session_id` + `identity` +
   `network/country`; the CLI derives the Camoufox userId
   (`session-<id>`) so contexts are isolated per session.
3. `walter-browse` plugin schema gains session fields in a later step; the
   CLI already exposes them for cron/scripts.
4. Old files remain readable (plain Playwright cookie lists) until fully
   migrated.