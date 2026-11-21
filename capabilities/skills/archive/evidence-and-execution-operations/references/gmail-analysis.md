# Gmail mailbox-analysis depth

## Per-account read-only OAuth

Create a separate account home for every Gmail identity and copy the OAuth client there; do not reuse the default token path for a second account. Request only `https://www.googleapis.com/auth/gmail.readonly`, use the exact registered redirect URI, preserve the pending state and PKCE verifier, and verify the returned identity with `users.getProfile`.

The bundled helper keeps the token and pending state inside `HERMES_HOME`:

```bash
ACCOUNT_HOME="$HOME/.hermes/google_accounts/<account>"
mkdir -p "$ACCOUNT_HOME"
cp "$HOME/.hermes/google_client_secret.json" "$ACCOUNT_HOME/google_client_secret.json"
GPY="${HERMES_AGENT_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
[ -x "$GPY" ] || GPY=python3

HERMES_HOME="$ACCOUNT_HOME" GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback' \
  "$GPY" scripts/gmail_readonly_oauth.py auth-url

HERMES_HOME="$ACCOUNT_HOME" GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback' \
  "$GPY" scripts/gmail_readonly_oauth.py auth-code '<complete-redirect-url>'

HERMES_HOME="$ACCOUNT_HOME" "$GPY" scripts/gmail_readonly_oauth.py verify
```

If the callback is expired, already used, or has a mismatched state, start a fresh `auth-url` flow. Never print token JSON, client secrets, or full message bodies.

## Complete inventory

For each verified account, call `users.getProfile` and `users.labels.list`, then page `users.messages.list` with `includeSpamTrash=True` and `maxResults=500` until `nextPageToken` is absent when the request means all mail. Count actual message IDs and do not use `resultSizeEstimate` as the total.

Batch metadata for sender/recipient/date/thread/reply headers, snippets, labels, `internalDate`, and size. Save normalized metadata and a failure log before classification; retry only bounded transient failures and split failed batches to item level so coverage is measurable.

## Thread analysis and report

Group messages by `threadId` and order by `internalDate`. Use metadata for global ranking, then fetch complete bodies for urgent or unresolved candidates and any thread whose snippet is insufficient. Classify surfaced threads as urgent reply, reply, action without reply, waiting, reference, or noise, and mark heuristic classifications as such.

Report scope, verified identity, Spam/Trash boundary, pagination and metadata coverage, failures, attention items, actions, waiting items, trends, and unauthorized accounts separately. Keep per-account results separate before any labeled comparison, and never mutate the mailbox during analysis.
