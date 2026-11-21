# Gmail Label Management & Email Triage

## Creating Labels (not available via CLI wrapper)

The `google_api.py` CLI has no `create-label` command. Use raw Python with `googleapiclient`:

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file("~/.hermes/google_token.json")
service = build("gmail", "v1", credentials=creds)

# Create a label
body = {
    "name": "LabelName",
    "labelListVisibility": "labelShow",
    "messageListVisibility": "show"
}
result = service.users().labels().create(userId="me", body=body).execute()
# result["id"] is the label ID (e.g., "Label_22")
```

## Moving Emails to Labels (archive + label)

To "file" an email: add the custom label and remove INBOX + UNREAD:

```python
body = {
    "addLabelIds": ["Label_22"],       # target label
    "removeLabelIds": ["INBOX", "UNREAD"]  # archive + mark read
}
service.users().messages().modify(userId="me", id=msg_id, body=body).execute()
```

## Bulk Organization Pattern

Script at `/tmp/gmail_organize.py` (or save under `scripts/`) demonstrates the full pattern:
1. Create labels (handle duplicates gracefully)
2. Categorize message IDs by label
3. Batch apply labels + archive

## Recommended Label Structure (personal Gmail)

| Label | Purpose | Examples |
|-------|---------|---------|
| Finances | Receipts, bank alerts, purchases | Grab, Revolut, Kie AI |
| Tech-AI | AI/dev newsletters, product updates | Medium, Mem0, MuAPI |
| Services | Account notifications, login alerts | Link, IFTTT, 2Captcha |
| Securite | Auth codes, security alerts | Google alerts, Facebook alerts |
| Newsletters | News digests, social media notifications | FT, SpellRoll, Voici, LinkedIn |

## Search Across All Folders

By default, Gmail API `messages.list` only returns messages matching the query in all folders. But `INBOX` label is implicit in some tools. Always use `in:anywhere` or omit label filters when the user wants "all mail":

```
$GAPI gmail search "in:anywhere newer_than:7d" --max 30
```
