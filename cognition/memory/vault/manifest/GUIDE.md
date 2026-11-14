# Raw Vault — guide détaillé

## Objectif

Conserver les octets originaux de tout ce qui n'est pas du texte dans la vie de {{owner.address}} (photos, captures d'écran,
vidéos, notes vocales, documents) et les relier à la mémoire. Seul le texte dérivé (OCR, transcription, légende)
entre dans Walter Memory, avec un lien vers l'objet. Un agent s'en sert pour retrouver un fichier, le récupérer
sur la VM pour le traiter, ou déposer un fichier à conserver.

## Comment l'utiliser

1. `vault_search(text, kind, source)` : cherche dans les noms et le texte dérivé ; `kind` = image, screenshot,
   video, audio, document, archive ; texte vide = objets récents permis.
2. `vault_get(object_id, dest_dir)` : télécharge un objet sur la VM, intégrité vérifiée ; renvoie le chemin.
3. `vault_put(path, source, captured_at, links)` : dépose un fichier local une seule fois (dédoublonné par contenu) ;
   `links` rattache des personnes ou conversations (`kardex_contact:5`, `hermes_session:<id>`).

## Organisation

| Partie | Rôle |
|---|---|
| Google Drive « W.Alter Raw Vault » (`rawvault:`) | Octets en clair, dossier navigable |
| Drive « W.Alter Raw Vault Secure » (rclone crypt) | Objets `local_only`, médias de tiers, exports Hermes |
| `raw-vault-s3` (127.0.0.1:8899) | Façade S3 : bucket `raw` et bucket `secure` ; cache `/var/cache/raw-vault` |
| `core.objects` (Walter Memory) | Catalogue unique ; `walter_memory.objects` |

## Interfaces

| Besoin | MCP | CLI |
|---|---|---|
| Chercher | `vault_search` | `walter-memory objects …` |
| Récupérer / déposer | `vault_get`, `vault_put` | `walter-memory objects …` |

## Limites

- Les objets restreints sont refusés avant tout téléchargement.
- Imports massifs (Takeout, photothèque) : `rclone copy` + insertion au catalogue, pas le cache S3.
- Un objet sans texte dérivé n'est trouvable que par son nom, sa source ou sa date.
