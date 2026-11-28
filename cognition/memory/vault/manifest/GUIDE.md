# Raw Vault — detailed guide

## Purpose
Keep the original bytes of everything that is not text in {{owner.address}}'s life (photos, screenshots, videos, voice
notes, documents) and link them to memory. Only derived text (OCR, transcript, caption) enters Walter Memory, with a
link to the object. An agent uses it to find a file, fetch it onto the server to process it, or store a file to keep.

## How to use it
1. `vault_search(text, kind, source, thread, event_id, since, until)`: searches names and derived text; `kind` =
   image, screenshot, video, audio, document, archive; empty text = recent permitted objects.
2. `vault_get(object_id, dest_dir)`: downloads an object onto the server, integrity checked; returns the path.
3. `vault_put(path, source, captured_at, links)`: stores a local file once (deduplicated by content); `links` attaches
   people or conversations (`kardex_contact:5`, a session or thread id).

## Organisation
| Part | Role |
|---|---|
| Google Drive "W.Alter Raw Vault" (`rawvault:`) | Plain bytes, browsable folder |
| Drive "W.Alter Raw Vault Secure" (rclone crypt) | `local_only` objects, third-party media, raw exports |
| `raw-vault-s3` (127.0.0.1:8899) | S3 facade: bucket `raw` and bucket `secure`; write-back cache `/var/cache/raw-vault` |
| `core.objects` (Walter Memory) | Single catalogue; library `walter_memory.objects` |

## Interfaces
| Need | MCP | CLI |
|---|---|---|
| Search | `vault_search` | `walter-memory objects …` |
| Fetch / store | `vault_get`, `vault_put` | `walter-memory objects …` |

## Limits
- Restricted objects are refused before any download.
- Bulk imports (Takeout, photo library): `rclone copy` + catalogue insert, not the S3 cache.
- An object without derived text can only be found by its name, source or date.
