---
title: "Google Drive: Upload, Trash, Bulk Delete via Python API"
category: "drive-operations"
---

# Drive Raw API Operations (Python)

The `$GAPI drive` CLI only covers search/get/download/move. For anything beyond — upload, trash/delete, bulk operations — use `googleapiclient` directly.

## Auth Setup

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file(
    '~/.hermes/google_token.json',
    scopes=['https://www.googleapis.com/auth/drive'])
service = build('drive', 'v3', credentials=creds)
```

## Upload to Specific Folder

```python
from googleapiclient.http import MediaFileUpload

parent_folder = 'DRIVE_FOLDER_ID'  # Get from `drive get` → `parents` field

file_metadata = {
    'name': 'output_video.mp4',
    'parents': [parent_folder],
}
media = MediaFileUpload('/tmp/output_video.mp4', mimetype='video/mp4')
file = service.files().create(
    body=file_metadata,
    media_body=media,
    fields='id,name,size,webViewLink'
).execute()
# Returns: {id, name, size, webViewLink}
```

Batch upload:

```python
files_to_upload = [
    ('/tmp/file1.mp4', 'output1.mp4'),
    ('/tmp/file2.mp4', 'output2.mp4'),
]
for filepath, name in files_to_upload:
    media = MediaFileUpload(filepath, mimetype='video/mp4')
    result = service.files().create(
        body={'name': name, 'parents': [parent_folder]},
        media_body=media,
        fields='id,name,size,webViewLink'
    ).execute()
    print(f"Uploaded {name}: {result['id']} — {result['webViewLink']}")
```

## Trash (Soft Delete)

```python
service.files().update(fileId='FILE_ID', body={'trashed': True}).execute()
```

## List & Delete by Name Pattern

```python
results = service.files().list(
    q="name contains 'prefix'",
    fields="files(id, name)"
).execute()
for f in results.get('files', []):
    service.files().update(fileId=f['id'], body={'trashed': True}).execute()
    print(f"Trashed {f['name']} ({f['id']})")
```

## Filter Trash by Parent Folder

```python
# List files in a specific folder
results = service.files().list(
    q=f"'{FOLDER_ID}' in parents",
    fields="files(id, name)"
).execute()
```

## Get Parent Folder of a File

```python
file = service.files().get(fileId='FILE_ID', fields='id,name,parents').execute()
parent_folder_id = file.get('parents', ['unknown'])
```

## Common MimeTypes

| Extension | MimeType |
|-----------|----------|
| mp4 | video/mp4 |
| mp3 | audio/mpeg |
| png | image/png |
| jpg/jpeg | image/jpeg |
| pdf | application/pdf |
| txt | text/plain |
| json | application/json |

## Dependencies

`google-api-python-client` — available in the Hermes venv:
```bash
~/.hermes/hermes-agent/venv/bin/python -c "from googleapiclient.discovery import build"
```
