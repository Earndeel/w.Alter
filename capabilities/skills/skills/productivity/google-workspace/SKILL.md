---
name: google-workspace
description: "Gmail, Calendar, Drive, Docs, Sheets via gws CLI or Python."
version: 1.0.2
author: Nous Research
license: MIT
required_credential_files:
  - path: google_token.json
    description: Google OAuth2 token (created by setup script)
  - path: google_client_secret.json
    description: Google OAuth2 client credentials (downloaded from Google Cloud Console)
metadata:
  hermes:
    tags: [Google, Gmail, Calendar, Drive, Sheets, Docs, Contacts, Email, OAuth]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [himalaya]
---

# Google Workspace

Gmail, Calendar, Drive, Contacts, Sheets, and Docs — through Hermes-managed OAuth and a thin CLI wrapper. When `gws` is installed, the skill uses it as the execution backend for broader Google Workspace coverage; otherwise it falls back to the bundled Python client implementation.

## References

- `references/gmail-search-syntax.md` — Gmail search operators (is:unread, from:, newer_than:, etc.)
- `references/oauth-troubleshooting.md` — Full OAuth debugging flow: redirect_uri_mismatch, access_denied, API not enabled, stale tokens, Desktop vs Web clients
- `references/klaviyo-unsubscribe-limitations.md` — Klaviyo unsubscribe pages (JS-rendered, can't be automated via curl/fetch), alternative workarounds
- `references/drive-upload-trash.md` — Drive upload & trash via raw Python API (the CLI has no upload/delete subcommand)
- `references/direct-gemini-api.md` — Direct Gemini API calls via urllib when provider routing fails or a specific model is requested
- `references/email-to-podcast-workflow.md` — Turn emails into audio briefings with TTS (Gemini → edge-tts fallback) and deliver via Telegram
- `references/gmail-label-management.md` — Create labels, bulk-organize emails, archive patterns (requires raw Python, not available via CLI wrapper)

## Scripts

- `scripts/setup.py` — OAuth2 setup (run once to authorize)
- `scripts/google_api.py` — compatibility wrapper CLI. It prefers `gws` for operations when available, while preserving Hermes' existing JSON output contract.

## First-Time Setup

The setup is fully non-interactive — you drive it step by step so it works
on CLI, Telegram, Discord, or any platform.

Define a shorthand first. Prefer the Hermes venv Python so dependency installs do not hit Debian/PEP668 system-Python restrictions:

```bash
GPY="${HERMES_AGENT_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
[ -x "$GPY" ] || GPY="python3"
GSETUP="$GPY ${HERMES_HOME:-$HOME/.hermes}/skills/productivity/google-workspace/scripts/setup.py"
```

### Step 0: Check if already set up

```bash
$GSETUP --check
```

If it prints `AUTHENTICATED`, skip to Usage — setup is already done.

### Step 1: Triage — ask the user what they need

Before starting OAuth setup, ask the user TWO questions:

**Question 1: "What Google services do you need? Just email, or also
Calendar/Drive/Sheets/Docs?"**

- **Email only** → They don't need this skill at all. Use the `himalaya` skill
  instead — it works with a Gmail App Password (Settings → Security → App
  Passwords) and takes 2 minutes to set up. No Google Cloud project needed.
  Load the himalaya skill and follow its setup instructions.

- **Email + Calendar** → Continue with this skill, but use
  `--services email,calendar` during auth so the consent screen only asks for
  the scopes they actually need.

- **Calendar/Drive/Sheets/Docs only** → Continue with this skill and use a
  narrower `--services` set like `calendar,drive,sheets,docs`.

- **Full Workspace access** → Continue with this skill and use the default
  `all` service set.

**Question 2: "Does your Google account use Advanced Protection (hardware
security keys required to sign in)? If you're not sure, you probably don't
— it's something you would have explicitly enrolled in."**

- **No / Not sure** → Normal setup. Continue below.
- **Yes** → Their Workspace admin must add the OAuth client ID to the org's
  allowed apps list before Step 4 will work. Let them know upfront.

### Step 2: Create OAuth credentials (one-time, ~5 minutes)

Tell the user:

> You need a Google Cloud OAuth client. This is a one-time setup:
>
> 1. Create or select a project:
>    https://console.cloud.google.com/projectselector2/home/dashboard
> 2. Enable the required APIs from the API Library:
>    https://console.cloud.google.com/apis/library
>    Enable: Gmail API, Google Calendar API, Google Drive API,
>    Google Sheets API, Google Docs API, People API
> 3. Create the OAuth client here:
>    https://console.cloud.google.com/apis/credentials
>    Credentials → Create Credentials → OAuth 2.0 Client ID
> 4. Application type: "Desktop app" → Create
> 5. If the app is still in Testing, add the user's Google account as a test user here:
>    https://console.cloud.google.com/auth/audience
>    Audience → Test users → Add users
> 6. **IMPORTANT — Testing mode tokens expire after ~7 days.** To get permanent tokens, publish the app to Production:
>    https://console.cloud.google.com/apis/credentials/consent → click "Publish App". No Google verification needed for personal use.
> 7. Download the JSON file and tell me the file path
>
> Important Hermes CLI note: if the file path starts with `/`, do NOT send only the bare path as its own message in the CLI, because it can be mistaken for a slash command. Send it in a sentence instead, like:
> `The JSON file path is: /home/user/Downloads/client_secret_....json`

Once they provide the path:

```bash
$GSETUP --client-secret /path/to/client_secret.json
```

If they paste raw client credentials instead of a file path:
- For a Desktop client, write a valid Desktop OAuth JSON file yourself, save it somewhere explicit (for example `~/Downloads/hermes-google-client-secret.json`), then run `--client-secret` against that file.
- For a Web client (`{"web": ...}`), choose an exact localhost redirect URI such as `http://localhost:8080/oauth2callback`, add it to the local JSON under `web.redirect_uris`, and run auth with `GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback'`. The user must also add that exact URI in Google Cloud Console → OAuth client → Authorized redirect URIs before opening the auth URL, otherwise Google returns `redirect_uri_mismatch`.

### Step 3: Get authorization URL

**⚠️ CRITICAL — Check client type AND set redirect URI BEFORE generating URL:**

```bash
# 1. Check client type
cat ~/.hermes/google_client_secret.json | python3 -c "import json,sys; d=json.load(sys.stdin); key='web' if 'web' in d else 'installed'; print('Type:', key); print('redirect_uris:', d[key].get('redirect_uris',[]))"

# 2. ALWAYS set redirect URI for Web clients (for BOTH --auth-url AND --auth-code)
export GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback'
```

**⚠️ CRITICAL — Check client type AND set redirect URI BEFORE generating URL:**

```bash
# 1. Check client type and registered redirect URIs
cat ~/.hermes/google_client_secret.json | python3 -c "import json,sys; d=json.load(sys.stdin); key='web' if 'web' in d else 'installed'; print('Type:', key); print('redirect_uris:', d[key].get('redirect_uris',[]))"

# 2. ALWAYS set redirect URI for Web clients (for BOTH --auth-url AND --auth-code)
# Use the EXACT URI from step 1 (including port and path)
export GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback'  # must match registered URI
```

- **Desktop (`installed`)**: `$GSETUP --auth-url` works out of the box (uses `http://localhost`).
- **Web**: You MUST set `GOOGLE_OAUTH_REDIRECT_URI` to match one of the registered `redirect_uris`, otherwise the user gets `redirect_uri_mismatch` (400).

**PITFALL — redirect_uri_mismatch (2026-05-24 confirmed)**: The default `setup.py` generates `http://localhost/` as redirect. If the client is a "web" type with registered URIs like `http://localhost:8080/oauth2callback`, the auth URL fails immediately. ALWAYS check the client type first. The error message from Google is: "Vous ne pouvez pas vous connecter, car cette appli a envoyé une demande non valide. Erreur 400 : redirect_uri_mismatch". Fix: set `GOOGLE_OAUTH_REDIRECT_URI` to the EXACT registered URI and regenerate.

**PITFALL — Missing scopes**: If `$GSETUP --check` shows "AUTHENTICATED (partial)" with missing scopes, re-auth with `--services all` to get ALL scopes in one go. Do NOT settle for partial auth — the user expects all scopes to work permanently.

**PITFALL — Copy-paste UX**: When sending an OAuth URL to the user, ALWAYS present it as a clean clickable link. Long URLs with `%20` and query params are hard to copy-paste on mobile/messaging. If possible, open the URL directly on the user's Mac via `ssh mac "open -a 'Brave Browser' '<url>'"` instead of sending the raw URL.

Use the service set chosen in Step 1. Examples:

```bash
# Desktop client (works directly)
$GSETUP --auth-url --services email,calendar --format json
$GSETUP --auth-url --services all --format json

# Web client (MUST set redirect URI)
GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback' $GSETUP --auth-url --services all --format json
```

This returns JSON with an `auth_url` field and also saves the exact URL to
`~/.hermes/google_oauth_last_url.txt`.

Agent rules for this step:
- **ALWAYS check client type first** — do not blindly generate with default redirect.
- Extract the `auth_url` field and send that exact URL to the user as a single line.
- Tell the user that the browser will likely fail on `http://localhost` after approval, and that this is expected.
- Tell them to copy the ENTIRE redirected URL from the browser address bar.
- If the user gets `Erreur 400 : redirect_uri_mismatch`, inspect the OAuth client's registered `redirect_uris` in `~/.hermes/google_client_secret.json` and make `setup.py` use the exact registered redirect URI before generating a fresh auth URL.
- If the user gets `Error 403: access_denied`, send them directly to `https://console.cloud.google.com/auth/audience` to add themselves as a test user.

### Step 4: Exchange the code

**Remember**: `GOOGLE_OAUTH_REDIRECT_URI` must still be set (same value as Step 3).

```bash
# Desktop client
$GSETUP --auth-code "THE_URL_OR_CODE_THE_USER_PASTED" --format json

# Web client (MUST set redirect URI — same as Step 3)
GOOGLE_OAUTH_REDIRECT_URI='http://localhost:8080/oauth2callback' $GSETUP --auth-code "THE_URL_OR_CODE_THE_USER_PASTED" --format json
```

**PITFALL**: For Web clients, `GOOGLE_OAUTH_REDIRECT_URI` must be set for **BOTH** `--auth-url` AND `--auth-code`. If you only set it for Step 3, the code exchange will fail silently with an `invalid_grant` error.

If `--auth-code` fails because the code expired, was already used, or came from
an older browser tab, it now returns a fresh `fresh_auth_url`. In that case,
immediately send the new URL to the user and have them retry with the newest
browser redirect only.

### Step 5: Verify

```bash
$GSETUP --check
```

Should print `AUTHENTICATED`. Setup is complete — token refreshes automatically from now on.

### Notes

- Token is stored at `~/.hermes/google_token.json` and auto-refreshes.
- Pending OAuth session state/verifier are stored temporarily at `~/.hermes/google_oauth_pending.json` until exchange completes.
- If `gws` is installed, `google_api.py` points it at the same `~/.hermes/google_token.json` credentials file. Users do not need to run a separate `gws auth login` flow.
- To revoke: `$GSETUP --revoke`

## Usage

All commands go through the API script. Set `GAPI` as a shorthand:

```bash
GPY="${HERMES_AGENT_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python}"
[ -x "$GPY" ] || GPY="python3"
GAPI="$GPY ${HERMES_HOME:-$HOME/.hermes}/skills/productivity/google-workspace/scripts/google_api.py"
```

### Gmail

## Interaction Guidelines
- **Include All Folders**: When asked to browse or search emails, always search across all folders/categories (don't restrict to `INBOX` or specific category labels). Use broad queries like `newer_than:3d` or `in:anywhere` instead of defaulting to INBOX-only results.
- **Default Action**: Use `$GAPI gmail search "in:anywhere newer_than:3d"` (not just `""`) to pull recent mail across all categories.
- **Do not trust `resultSizeEstimate` for cleanup decisions**: Gmail API estimates can be wildly off on filtered/category queries (e.g. estimate says hundreds while pagination returns only a few). For destructive actions, page through message IDs and count the actual list before modifying/trashing.
- **HTML Body Stripping**: `gmail get` returns the body as-is — newsletters (FT, Medium, etc.) return raw HTML. Strip tags before summarizing: `re.sub(r'<[^>]+>', ' ', body)` + `html.unescape()`. See `references/email-to-podcast-workflow.md` for the full extraction recipe.

```bash
# Search (returns JSON array with id, from, subject, date, snippet)
$GAPI gmail search "is:unread" --max 10
$GAPI gmail search "from:boss@company.com newer_than:1d"
$GAPI gmail search "has:attachment filename:pdf newer_than:7d"

# Read full message (returns JSON with body text)
$GAPI gmail get MESSAGE_ID

# Send
$GAPI gmail send --to user@example.com --subject "Hello" --body "Message text"
$GAPI gmail send --to user@example.com --subject "Report" --body "<h1>Q4</h1><p>Details...</p>" --html
$GAPI gmail send --to user@example.com --subject "Hello" --from '"Research Agent" <user@example.com>' --body "Message text"

# Reply (automatically threads and sets In-Reply-To)
$GAPI gmail reply MESSAGE_ID --body "Thanks, that works for me."
$GAPI gmail reply MESSAGE_ID --from '"Support Bot" <user@example.com>' --body "Thanks"

# Labels
$GAPI gmail labels
$GAPI gmail modify MESSAGE_ID --add-labels LABEL_ID
$GAPI gmail modify MESSAGE_ID --remove-labels UNREAD
```

### Calendar

```bash
# List events (defaults to next 7 days)
$GAPI calendar list
$GAPI calendar list --start 2026-03-01T00:00:00Z --end 2026-03-07T23:59:59Z

# Create event (ISO 8601 with timezone required)
$GAPI calendar create --summary "Team Standup" --start 2026-03-01T10:00:00-06:00 --end 2026-03-01T10:30:00-06:00
$GAPI calendar create --summary "Lunch" --start 2026-03-01T12:00:00Z --end 2026-03-01T13:00:00Z --location "Cafe"
$GAPI calendar create --summary "Review" --start 2026-03-01T14:00:00Z --end 2026-03-01T15:00:00Z --attendees "alice@co.com,bob@co.com"

# Delete event
$GAPI calendar delete EVENT_ID
```

### Drive

⚠️ **Limitation**: `$GAPI drive` only supports `search`, `get`, `download`, `move`. For **upload** and **trash/delete**, use raw Python with `googleapiclient` (see code below). The script has no upload or delete subcommand.

```bash
# Search/list metadata
$GAPI drive search "quarterly report" --max 10
$GAPI drive search "mimeType='application/pdf'" --raw-query --max 5

# Get metadata
$GAPI drive get FILE_ID

# Download/export to local disk
$GAPI drive download FILE_ID --output /tmp/report.txt
$GAPI drive download GOOGLE_DOC_ID --export-mime text/plain --output /tmp/doc.txt
$GAPI drive download GOOGLE_DOC_ID --export-mime application/pdf --output /tmp/doc.pdf

# Move a file/folder to another Drive folder (requires full Drive scope)
$GAPI drive move FILE_ID DESTINATION_FOLDER_ID
```

#### Drive image processing pipeline (download → process → upload)

When batch-processing Drive images (upscale, edit, convert), use this pattern:
1. `drive search` to list files in a folder
2. `files().get_media()` + `MediaIoBaseDownload` to download each to `/tmp/`
3. Process with AI model (e.g., GPT Image 2 via OpenAI `/v1/images/edits`)
4. `create_drive_folder()` to make output folder (check if exists first)
5. `MediaFileUpload` + `files().create()` to upload results back

Key: always check folder existence before creating (search by name + parent). Use `hermes_tools.terminal` in `execute_code`, not bare `terminal`.

## PDF Form Filling with Gemini Vision

For filling PDF forms (IRS, legal docs, applications), see `references/pdf-form-filling.md`.
Workflow: PyMuPDF field discovery → Gemini 3.1 Pro analysis → PyMuPDF fill → Drive upload.
Available model: `gemini-3.1-pro-preview` via vault key `gemini/api_key`.

#### Drive upload & trash (raw Python fallback)

When upload or trash/delete is needed, use `googleapiclient` directly with the Hermes token:

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

creds = Credentials.from_authorized_user_file('~/.hermes/google_token.json',
    scopes=['https://www.googleapis.com/auth/drive'])
service = build('drive', 'v3', credentials=creds)

# UPLOAD: create file in specific folder
file_metadata = {'name': 'output.mp4', 'parents': ['PARENT_FOLDER_ID']}
media = MediaFileUpload('/tmp/output.mp4', mimetype='video/mp4')
file = service.files().create(body=file_metadata, media_body=media,
    fields='id,name,size,webViewLink').execute()

# TRASH (soft delete): move to trash
service.files().update(fileId='FILE_ID', body={'trashed': True}).execute()

# LIST & TRASH BY NAME PATTERN
results = service.files().list(q="name contains '0510'", fields="files(id, name)").execute()
for f in results.get('files', []):
    service.files().update(fileId=f['id'], body={'trashed': True}).execute()
```

Drive move uses `files.update(addParents=..., removeParents=...)`; confirm the target file and destination folder with the user before moving.

### Contacts

```bash
$GAPI contacts list --max 20
```

### Sheets

```bash
# Read
$GAPI sheets get SHEET_ID "Sheet1!A1:D10"

# Write
$GAPI sheets update SHEET_ID "Sheet1!A1:B2" --values '[["Name","Score"],["Alice","95"]]'

# Append rows
$GAPI sheets append SHEET_ID "Sheet1!A:C" --values '[["new","row","data"]]'
```

### Docs

```bash
$GAPI docs get DOC_ID
```

## Output Format

All commands return JSON. Parse with `jq` or read directly. Key fields:

- **Gmail search**: `[{id, threadId, from, to, subject, date, snippet, labels}]`
- **Gmail get**: `{id, threadId, from, to, subject, date, labels, body}`
- **Gmail send/reply**: `{status: "sent", id, threadId}`
- **Calendar list**: `[{id, summary, start, end, location, description, htmlLink}]`
- **Calendar create**: `{status: "created", id, summary, htmlLink}`
- **Drive search**: `[{id, name, mimeType, modifiedTime, webViewLink}]`
- **Contacts list**: `[{name, emails: [...], phones: [...]}]`
- **Sheets get**: `[[cell, cell, ...], ...]`

## Rules

1. **Never send email or create/delete events without confirming with the user first.** Show the draft content and ask for approval.
2. **Check auth before first use** — run `setup.py --check`. If it fails, guide the user through setup.
3. **Use the Gmail search syntax reference** for complex queries — load it with `skill_view("google-workspace", file_path="references/gmail-search-syntax.md")`.
4. **Calendar times must include timezone** — always use ISO 8601 with offset (e.g., `2026-03-01T10:00:00-06:00`) or UTC (`Z`).
5. **Drive moves are side effects** — before `drive move`, show the file name/id and destination folder name/id and get explicit confirmation.
6. **Respect rate limits** — avoid rapid-fire sequential API calls. Batch reads when possible.

## Envoi d'emails (scope gmail.send)

Le token par défaut a souvent `gmail.readonly` seulement. Pour envoyer :

```bash
# Relancer auth avec gmail.send
GOOGLE_OAUTH_REDIRECT_URI="http...ck" \
  $GSETUP --auth-url --services email

# Ouvrir sur Mac (pas headless — le redirect doit être visible)
ssh mac "osascript -e 'tell application \"Brave Browser\" to open location \"URL\"'"

# L'utilisateur approuve → redirige vers localhost:8080/oauth2callback?code=...
# (erreur normale). Il copie l'URL complète.

$GSETUP --auth-code "<code>" --services email
$GAPI gmail send --to "..." --subject "..." --body "..."
```

**Pitfall** : redirect_uri = `http://localhost:8080/oauth2callback` (client Web). PAS `http://localhost/`.

## Troubleshooting

Full resolution map with error codes, root causes, and fixes: `references/oauth-troubleshooting.md`.

| Problem | Fix |
|---------|-----|
| `NOT_AUTHENTICATED` | Run setup Steps 2-5 above |
| `REFRESH_FAILED` | Token revoked/expired — **check if app is in Testing mode** (tokens expire after ~7 days). Publish to Production first, then redo Steps 3-5 |
| `redirect_uri_mismatch` (400) | Inspect OAuth client's registered URIs and match exactly (including trailing slash). See troubleshooting ref. |
| `access_denied` → "app in Testing mode" (403) | User must add themselves as a test user at `https://console.cloud.google.com/auth/audience` |
| `HttpError 403: Insufficient Permission` | Missing API scope — `$GSETUP --revoke` then redo Steps 3-5 |
| `HttpError 403: Access Not Configured` | API not enabled — user needs to enable it in Google Cloud Console. Enable URLs in troubleshooting ref. |
| `ModuleNotFoundError` | Run `$GSETUP --install-deps` (use Hermes venv Python on Debian/PEP668) |
| `invalid_client` on device code | Device flow only works for TV/Limited Input clients. Use Desktop/Web client with loopback redirect. |
| Advanced Protection blocks auth | Workspace admin must allowlist the OAuth client ID |
| `ModuleNotFoundError` | Run `$GSETUP --install-deps` |
| Advanced Protection blocks auth | Workspace admin must allowlist the OAuth client ID |

## Revoking Access

```bash
$GSETUP --revoke
```

## Pitfalls

1. **Missing scopes on existing token**: If `$GSETUP --check` shows `AUTHENTICATED (partial)` with missing scopes, re-auth with `--services all`. Don't try to use a partial token — API calls fail with `insufficientPermissions`.

2. **Long OAuth URLs on Telegram/messaging**: Auth URLs with `--services all` are 700+ chars — too long to copy-paste on Telegram. Open directly on Mac Brave via SSH instead of sending as text:
   ```bash
   ssh -o ConnectTimeout=8 -i ~/.ssh/id_ed25519 lucasjouvencon@100.127.150.1 \
     "open -a 'Brave Browser' '$AUTH_URL'"
   ```
   Then ask user to copy the redirect URL from their browser address bar.
