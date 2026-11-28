# Multi-account Gmail OAuth checklist

Use this reference with `google-workspace-multi-account`. It intentionally contains placeholders only; never paste a token, client secret, password, or full callback URL into this file.

## Preflight

```bash
GPY="${HERMES_AGENT_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
[ -x "$GPY" ] || GPY="python3"
BASE="${HERMES_HOME:-$HOME/.hermes}"
SCRIPT="$BASE/skills/productivity/google-workspace/scripts/setup.py"
```

1. Check the existing account without changing it:

```bash
"$GPY" "$SCRIPT" --check
```

2. Inspect only OAuth client metadata and choose an exact redirect URI:

```bash
"$GPY" -c 'import json,os; p=os.path.join(os.environ.get("HERMES_HOME",os.path.expanduser("~/.hermes")),"google_client_secret.json"); d=json.load(open(p)); k="web" if "web" in d else "installed"; print("type="+k); print("redirect_uris="+repr(d[k].get("redirect_uris",[])))'
```

For a Web client, the redirect URI must be registered in Google Cloud and exported for both commands below. Example only:

```bash
REDIRECT='http://localhost:8080/oauth2callback'
```

Do not use the example unless it appears exactly in the client’s registered URI list.

## Isolate each account

```bash
ACCOUNT_ROOT="$BASE/google-accounts"
mkdir -p "$ACCOUNT_ROOT/account-a" "$ACCOUNT_ROOT/account-b"
# Reuse the already-approved client secret through a protected symlink or copy.
# Do not copy google_token.json from the primary account.
```

The two account homes must be different. Their `google_oauth_pending.json` and `google_token.json` files must never be shared.

## Generate consent URL

Run once per account, changing `ACCOUNT_HOME` and `ACCOUNT_EMAIL` each time:

```bash
ACCOUNT_HOME="$ACCOUNT_ROOT/account-a"
ACCOUNT_EMAIL='account-a@gmail.com'
HERMES_HOME="$ACCOUNT_HOME" \
GOOGLE_OAUTH_REDIRECT_URI="$REDIRECT" \
  "$GPY" "$SCRIPT" --auth-url --services email --format json
```

If adding a `login_hint`, treat it only as a convenience. The account selected on Google’s consent screen is authoritative. Keep the generated state in that account home.

## Exchange callback

After the owner approves the exact account, copy the complete redirected URL (including `code` and `state`) from the browser address bar. A localhost connection error is expected when no callback listener is running; the URL is still usable.

```bash
CALLBACK_URL='PASTE_THE_FULL_REDIRECT_URL_HERE'
HERMES_HOME="$ACCOUNT_HOME" \
GOOGLE_OAUTH_REDIRECT_URI="$REDIRECT" \
  "$GPY" "$SCRIPT" --auth-code "$CALLBACK_URL"
```

The same account home, client, redirect URI, and pending OAuth flow must be used for generation and exchange. Never reuse a callback in another account directory.

## Verify identity and preserve primary

Verify the new token without printing its contents:

```bash
HERMES_HOME="$ACCOUNT_HOME" "$GPY" -c '
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
home = Path(__import__("os").environ["HERMES_HOME"])
creds = Credentials.from_authorized_user_file(str(home / "google_token.json"))
profile = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
print(profile["emailAddress"])
print("scope_count=" + str(len(creds.scopes or [])))
'
```

The printed address must equal the requested address exactly. Then run the same profile check against the original primary home and confirm it still returns the original primary identity. Only after both checks pass may the operation be reported as complete.

## Routing note

The standard `google_api.py` reads `$HERMES_HOME/google_token.json`; it does not discover all token directories. Until account-aware routing is implemented, set `HERMES_HOME` explicitly for every command and label results with the source account. Do not replace the primary token to switch identities.
