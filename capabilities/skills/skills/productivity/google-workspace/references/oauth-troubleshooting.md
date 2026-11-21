# Google OAuth Troubleshooting Field Manual

Complete resolution map from a real multi-hour OAuth setup session (2026-05-10). Every error below was hit and fixed.

## Error → Cause → Fix

### `redirect_uri_mismatch` (400)

**Root cause**: The redirect_uri in the auth URL doesn't exactly match one registered in the OAuth client's Google Cloud Console entry.

**Debugging steps (in order)**:
1. Inspect the stored client secret: `cat ~/.hermes/google_client_secret.json | python3 -c "import json,sys; d=json.load(sys.stdin); c=d.get('installed') or d.get('web'); print(c.get('redirect_uris', ['NO URIS']))"`
2. Check the auth URL redirect_uri: extract the `redirect_uri` query param
3. **Common mismatch**: trailing slash (`http://localhost/` vs `http://localhost`). Google canonicalizes empty paths as `/` — always use the slash form for `localhost`.
4. **Desktop vs Web clients**: Desktop clients use `http://localhost` (loopback, any port). Web clients must have exact URIs pre-registered.
5. **Fix for Web clients**: set `GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback'` before running `setup.py --auth-url`, and ensure the exact URI is in the client's Authorized redirect URIs in Cloud Console.

**PITFALL**: A `redirect_uri_mismatch` after a previously working client usually means the client was regenerated, or the user provided a new JSON without redirect_uris. Always re-read the client secret before generating a new auth URL.

**AGENT PITFALL**: `GOOGLE_OAUTH_REDIRECT_URI` must be set for **BOTH** `--auth-url` AND `--auth-code`. If you only set it for the URL step, the code exchange silently fails with `invalid_grant`. The default `setup.py` generates `http://localhost/` as redirect — this mismatches any Web client with a different registered URI (e.g. `http://localhost:8080/oauth2callback`). Always check client type first (`cat ~/.hermes/google_client_secret.json | python3 -c "import json,sys; d=json.load(sys.stdin); key='web' if 'web' in d else 'installed'; print('Type:', key); print('redirect_uris:', d[key].get('redirect_uris',[]))"`) and set the env var on both commands.

### `access_denied` → "App in testing mode" (403)

**Root cause**: The OAuth consent screen is in "Testing" status and the user's Google account hasn't been added as a test user.

**Fix**: User must go to `https://console.cloud.google.com/auth/audience` → **Test users** → **Add Users** → add their Gmail. Wait 1-2 minutes for propagation. The agent should then provide a fresh auth URL.

**Note**: This error ONLY appears for apps in Testing mode. Published/production apps don't have this restriction.

### `invalid_grant` / `Bad Request` on token refresh

**Root cause**: The refresh token was revoked, the client secret changed, the token is from a different OAuth client, **or the OAuth app is in Testing mode**.

**⚠️ IMPORTANT — Do NOT assume Testing mode is the cause without evidence.** Even when the app IS in Production, `invalid_grant` can happen. Check these causes FIRST before blaming Testing mode:

1. **Password change** — User changed their Google password → all refresh tokens are silently revoked
2. **Manual revocation** — User visited myaccount.google.com/permissions and removed the app, or used "Sign out of all devices"
3. **Scope modification** — If scopes were changed on the OAuth consent screen in Cloud Console, existing tokens are invalidated
4. **Client secret rotation** — If the OAuth client was deleted/recreated in Cloud Console and a new JSON was downloaded, old tokens won't work with the new secret
5. **Google security detection** — Suspicious activity (new IP, automated access patterns) can trigger automatic token revocation
6. **Testing mode expiration** — Only check this AFTER ruling out the above

**Testing mode expiration (VERY COMMON)**: Apps in "Testing" mode issue refresh tokens that expire after **~7 days**. This is the #1 cause of `invalid_grant` on previously-working tokens. The user will say "it shouldn't be expired, I didn't set an expiration" — they're right that they didn't, but Google enforces it for Testing-mode apps.

**Fix for Testing mode expiration**: Publish the app to Production:
1. Go to https://console.cloud.google.com/apis/credentials/consent
2. Click "Publish App" (moves from Testing → Production)
3. Re-authorize: `$GSETUP --revoke` then redo Steps 3-5
4. Production refresh tokens do NOT expire (unless user revokes or changes password)

**Fix for other causes**: Revoke the old token (`$GSETUP --revoke`) and redo Steps 3-5 of the setup.

**Lesson**: When migrating from another system (e.g., OpenClaw), old tokens are useless. Always start fresh with the current client secret.

### `invalid_client` on device code flow (401)

**Root cause**: Device code flow (`/device/code` endpoint) only works with OAuth clients of type "TVs and Limited Input devices", not Desktop or Web clients.

**Fix**: Don't try device flow. Use loopback redirect (`http://localhost`) with Desktop/Web clients instead.

### API not enabled (`accessNotConfigured`, 403)

**Root cause**: The Google API (Gmail, Calendar, Drive, etc.) hasn't been enabled for the project.

**Fix**: User must enable the API. Direct links per service:
- Gmail: `https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=PROJECT_ID`
- Calendar: `https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview?project=PROJECT_ID`
- Drive: `https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=PROJECT_ID`
- Sheets: `https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=PROJECT_ID`
- Docs: `https://console.developers.google.com/apis/api/docs.googleapis.com/overview?project=PROJECT_ID`
- People/Contacts: `https://console.developers.google.com/apis/api/people.googleapis.com/overview?project=PROJECT_ID`

After enabling, wait 1-2 minutes for propagation.

## Full flow that works (as of 2026-05-10)

1. **User creates OAuth client** (or provides JSON). Prefer Desktop type for simplicity, but Web works with `GOOGLE_OAUTH_REDIRECT_URI`.
2. **User adds themselves as test user** if app is in Testing mode.
3. **User adds redirect URI** to Authorized redirect URIs if Web client (Desktop doesn't need this).
4. **Agent stores client secret**: `$GSETUP --client-secret /path/to/json`
5. **Agent generates auth URL**: `GOOGLE_OAUTH_REDIRECT_URI='...' $GSETUP --auth-url --services all --format json`
6. **User opens URL in browser**, authorizes, copies the redirect URL
7. **Agent exchanges code**: `GOOGLE_OAUTH_REDIRECT_URI='...' $GSETUP --auth-code "THE_URL"`
8. **Agent verifies**: `$GSETUP --check` → AUTHENTICATED

## Client types and their quirks

| Type | Redirect URI | Port flexibility | Needs test users |
|------|-------------|-----------------|-----------------|
| Desktop | `http://localhost` (loopback) | Any port auto-accepted | If in Testing |
| Web | Exact pre-registered URI | Must match exactly | If in Testing |
| TV/Limited Input | Device code flow | N/A | If in Testing |

## Expanding scopes

To add scopes (e.g., user wants Gmail after initially only authorizing Drive):
```bash
$GSETUP --revoke  # Kill old token
GOOGLE_OAUTH_REDIRECT_URI='...' $GSETUP --auth-url --services all --format json
# User re-authorizes with expanded scopes
GOOGLE_OAUTH_REDIRECT_URI='...' $GSETUP --auth-code "..."
```
