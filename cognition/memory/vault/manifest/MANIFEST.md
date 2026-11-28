# Raw Vault

**Role.** The original files of everything that is not text: photos, screenshots, videos, voice notes, documents.
Only derived text (OCR, transcript, caption) enters Walter Memory, with a link back to the object.

**Organisation.** Files on Google Drive (plain, or encrypted for restricted objects), served locally as S3; a single
catalogue in Walter Memory (`core.objects`).

**Tools**
- `vault_search(text, kind, thread, event_id, since, until)`: name, OCR, transcript; `kind` = image, screenshot,
  video, audio, document, archive; `thread` = the files of a conversation ("X's voice notes" = `kind="audio",
  thread=…`), `event_id` = those of one message.
- `vault_get(object_id)`: fetch the file onto the server (integrity checked) to process it.
- `vault_put(path, links)`: store a file to keep (deduplicated), linked to people or conversations.
