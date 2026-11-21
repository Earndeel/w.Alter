# Raw Vault — fichiers bruts

| | |
|---|---|
| **Rôle** | Conserver les octets originaux de ce qui n'est pas du texte (photos, captures, vidéos, audio, documents) et les relier au catalogue canonique de Walter Memory. |
| **Propriétaire** | raw-vault, composant de Walter Memory (`/walter/cognition/memory/vault`). |
| **État** | **active** (constat du 09/11/2026) : service `raw-vault-s3` (S3 local 127.0.0.1:8899, buckets `raw` en clair et `secure` chiffré par rclone crypt) ; octets sur Google Drive. Le catalogue est `core.objects`, implémenté une seule fois dans `walter_memory.objects`. `rawvault.py` est un ancien point d'entrée (`obsolete`) qui renvoie vers `walter-memory objects`. |
| **Ne fait pas** | Mettre des octets bruts dans Walter Memory : seul le texte dérivé (OCR, transcription, légende) y entre, avec un lien vers l'objet. Tenir un second catalogue. |
| **Contrats** | [contracts/raw-vault.json](contracts/raw-vault.json) ; MCP `vault_search`, `vault_get`, `vault_put` ; CLI `walter-memory objects` ; présentation agent dans [manifest/](manifest/MANIFEST.md). |

Clés S3 et emplacements : dans l'instance (`@instance/bootstrap/raw-vault/`). Imports en masse : `rclone copy` puis
insertion au catalogue, pas le cache d'écriture S3. Exploitation : `/walter/docs/RUNBOOK.md` § Raw Vault.
