# Raw Vault — fichiers bruts

Les octets originaux de tout ce qui n'est pas du texte : photos, captures, vidéos, notes vocales, documents de {{owner.address}}. Seul le texte dérivé (OCR, transcription, légende) entre dans Walter Memory, avec un lien vers l'objet.

**Organisation** : fichiers sur Google Drive (en clair, ou chiffrés pour les objets restreints), servis en S3 local ; catalogue unique dans Walter Memory (`core.objects`).

**Utilisation**
- `vault_search(text, kind)` : nom, OCR, transcription ; `kind` = image, screenshot, video, audio, document, archive.
- `vault_get(object_id)` : récupérer le fichier sur la VM (intégrité vérifiée) pour le traiter.
- `vault_put(path, links)` : déposer un fichier à conserver (dédoublonné), relié à des personnes ou conversations.
