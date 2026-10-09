# OAuth Setup Debugging Playbook

Concrete error patterns and their resolution, captured from real sessions.

## Desktop vs Web Clients

- **Desktop client** (`{"installed": ...}`): `redirect_uris` typically `["http://localhost"]` or `["http://localhost:PORT"]`. Google compares the redirect URI exactly (including trailing slash). The script defaults to `http://localhost/` with the trailing slash; override with `GOOGLE_OAUTH_REDIRECT_URI`.
- **Web client** (`{"web": ...}`): `redirect_uris` must be added in **both** the local JSON file AND Google Cloud Console → Credentials → OAuth client → Authorized redirect URIs. Use an explicit port like `http://localhost:8080/oauth2callback` to avoid ambiguity. Set `GOOGLE_OAUTH_REDIRECT_URI` to the exact match before running `--auth-url`.

## Error Sequence & Fixes

### 1. `redirect_uri_mismatch` (400)
Google rejects the auth request because the `redirect_uri` in the URL doesn't exactly match what's registered for the OAuth client.

**Check:** `cat ~/.hermes/google_client_secret.json | jq '.[].redirect_uris'`

**Fix:**
- Set `GOOGLE_OAUTH_REDIRECT_URI` to the exact registered value (including trailing slash if present)
- For Web clients: add the same URI in Cloud Console → OAuth client
- Regenerate `--auth-url`
- Example from session: OpenClaw Desktop client registered `http://localhost` but the script used `http://localhost/` — the trailing slash mismatch caused the 400. For Web clients, `http://localhost:8080/oauth2callback` worked after registration.

### 2. `access_denied` (403) — "App in testing mode"
Google shows: "App hasn't completed Google verification. Only approved test users can access."

**Fix:** Add the user's email at `https://console.cloud.google.com/auth/audience` → Test Users → Add Users. Wait 1-2 minutes for propagation.

### 3. `accessNotConfigured` (403) — "API not enabled"
Google Drive API (or another API) hasn't been turned on for the project.

**Fix:** The error message includes a direct link. Open it and click Enable. Example: `https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=PROJECT_ID`

### 4. `invalid_grant` — Stale refresh token
The stored refresh token has been revoked or expired (e.g., from an old OpenClaw setup).

**Fix:** `$GSETUP --revoke`, then re-authenticate from Step 3.

## Working Setup from May 10, 2026 (genai-470208)

- Project: `genai-470208` (Conjuring Studio)
- Client: Web OAuth, `http://localhost:8080/oauth2callback`
- Token: `~/.hermes/google_token.json`
- Scopes: all (email, calendar, drive, contacts, sheets, docs)
- Python: `/root/.hermes/hermes-agent/venv/bin/python`
- Env needed: `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8080/oauth2callback`
