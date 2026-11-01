# beeper-messages — Exporting a multi-source conversation with chronological merge and voice-note transcription.

Moved verbatim from SKILL.md on 2026-11-01.

## Exporter une conversation multi-source avec fusion chronologique et transcription des vocaux

Pour produire un export combiné Instagram/WhatsApp depuis Beeper, procéder ainsi :

1. Créer un répertoire de travail temporaire et extraire les événements Beeper avec `walter-memory` :

```bash
mkdir -p /tmp/claude-alina
cd /tmp/claude-alina
walter-memory events --source beeper --since YYYY-MM-DD --limit 100000 > beeper_raw.json
```

2. Identifier les fils cibles dans `beeper_raw.json` en recherchant le nom, le pseudo et les champs `payload`, puis vérifier les `thread_id` retenus avant de filtrer. Conserver les deux fils dans un ensemble explicite, par exemple `T = {'<instagram-thread-id>', '<whatsapp-thread-id>'}`. Ne pas déduire l'identité d'un fil uniquement à partir de son titre si plusieurs conversations portent le même nom.

3. Pour les médias audio, rechercher les objets Raw Vault associés aux fils dans PostgreSQL si `walter-memory objects search` ne fournit pas assez de métadonnées :

```bash
export PGPASSFILE=/root/.pgpass
psql -h 127.0.0.1 -p 5433 -U hindsight -d hindsight -Atc "select id::text, kind, mime, original_name, captured_at, size_bytes, storage_zone, storage_key, source_ref::text, meta::text from core.objects where source='beeper' and kind='audio' order by captured_at desc"
```

Utiliser `/opt/walter-memory` et le module `walter_memory.objects.get_object` pour récupérer les fichiers par identifiant, au lieu d'exposer ou de copier des identifiants d'accès au stockage. Vérifier que `source_ref` relie bien l'objet au `chat_id` et au `message_id` de l'événement.

4. Extraire les vocaux dans un sous-répertoire temporaire, puis les convertir avec `ffmpeg` si nécessaire. Utiliser le fournisseur STT installé dans `/root/.hermes/plugins/gemini-stt/__init__.py` via l'environnement `/root/.hermes/hermes-agent`. Vérifier la disponibilité de `ffmpeg` et de `ffprobe` avant la transcription. Enregistrer pour chaque vocal le statut, le texte, le message source et l'éventuelle erreur.

5. Fusionner les événements des deux fils après filtrage, en triant par `occurred_at` et en imposant l'ordre des messages reçus/envoyés avant les événements de modification ou de suppression lorsque les timestamps sont identiques :

```python
src.sort(key=lambda e: (
    e['occurred_at'],
    0 if e['event_type'] in ('message.received', 'message.sent') else 1,
))
```

Convertir ensuite les timestamps UTC en `Europe/Paris` avec `zoneinfo.ZoneInfo`, et conserver une étiquette de source distincte telle que `[IG]` ou `[WA]` sur chaque ligne.

6. Préserver les événements édités, supprimés, réactions et messages éphémères dans la chronologie. Si l'export ne contient pas le texte original d'une modification, marquer seulement `(modifié)` et indiquer que le texte disponible est celui de l'export. Si un vocal supprimé n'a plus d'objet Raw Vault, le conserver comme vocal supprimé sans inventer de transcription.

7. Rendre le fichier Markdown avec un script séparé. Remplacer les retours `<br>` par de vrais retours à la ligne avant rendu et vérifier que les vocaux transcrits sont repérables. Effectuer des contrôles de cohérence avant livraison : nombre d'événements par source, nombre de vocaux, nombre de transcriptions réussies, présence des bornes temporelles, absence de `<br>` résiduels et inspection du début, de la fin et de quelques lignes de vocaux, réactions et modifications.

8. Écrire le résultat dans `/root/reports/<contact>-instagram-whatsapp-<début>_<fin>.md`, puis supprimer le répertoire temporaire contenant les dumps JSON et les fichiers audio :

```bash
rm -rf /tmp/claude-alina
```

Pièges à vérifier : `walter-memory events` renvoie parfois davantage d'événements que les seuls messages, les vocaux peuvent être référencés dans `core.objects` plutôt que dans l'événement lui-même, un message supprimé peut ne plus avoir de média récupérable, plusieurs événements peuvent partager exactement le même timestamp, et l'export d'un message modifié peut ne pas contenir son texte précédent.
