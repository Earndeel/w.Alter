# Google OAuth Scope Management

Lessons from session 2026-05-24: token regeneration without all scopes.

## Problem
When the Google OAuth token gets regenerated (e.g., during re-auth), the new token may
only include the scopes requested in that specific auth flow. If you re-auth with
`--services drive` only, the resulting token loses gmail, calendar, contacts, etc.

## Solution
Always re-auth with `--services all` when fixing missing scopes:

```bash
GPY="${HERMES_AGENT_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
GSETUP="$GPY $HOME/.hermes/skills/productivity/google-workspace/scripts/setup.py"

# Check client type first
cat ~/.hermes/google_client_secret.json | python3 -c "import json,sys; d=json.load(sys.stdin); key='web' if 'web' in d else 'installed'; print('Type:', key); print('redirect_uris:', d[key].get('redirect_uris',[]))"

# Set redirect URI to match registered URIs (web clients)
export GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback'

# Generate auth URL with ALL scopes
$GSETUP --auth-url --services all --format json
```

## Redirect URI Mismatch
Error `redirect_uri_mismatch` means the redirect_uri in the auth URL doesn't match
what's registered in Google Cloud Console.

**Fix**: Check registered URIs in client secret JSON, then set `GOOGLE_OAUTH_REDIRECT_URI`
to match BEFORE generating the auth URL. Must be set for BOTH `--auth-url` AND `--auth-code`.

Common registered URIs:
- Desktop clients: `http://localhost`
- Web clients: `http://localhost:8080/oauth2callback`

## User Experience
- Open the auth URL on the user's Mac via SSH: `ssh mac 'open -a "Brave Browser" "URL"'`
- After authorization, user pastes the redirect URL back
- Exchange: `$GSETUP --auth-code "THE_URL" --format json`
- Verify: `$GSETUP --check` — should show all scopes as available

## User Preference
Monsieur expects ALL scopes to be present AT ALL TIMES. Never regenerate a token
with a subset of scopes. Always use `--services all`.
