# Walter Memory — la mémoire de {{owner.address}}

Vérité durable de sa vie : ce qui s'est passé (messages Beeper, e-mails, agenda, conversations avec W.Alter, fichiers), ce qui en a été appris, et qui sont les personnes.

**Organisation** : historique canonique append-only (`core.events`) ; connaissances dérivées toujours reliées à leurs preuves ; Kardex = couche sociale (identités, relations, mesures) ; index de recherche plein texte + sémantique ; connecteurs qui alimentent le tout. Classes de confidentialité : `cloud_allowed`, `redacted_cloud`, `local_only`.

**Utilisation**
- `memory_context(query)` d'abord pour tout sujet personnel ou de projet (personnes citées, connaissances, sources).
- `memory_search` : qui/quand/quoi, avec source et date ; `memory_events(text, source, since, until, order="newest"|"oldest", event_id, limit)` : le texte exact d'un événement — liste compacte, `order="oldest"` pour le tout premier, puis `event_id` pour un événement en entier.
- `person_lookup(name)` : fiche d'une personne ; `memory_recall` / `memory_reflect` : faits synthétisés, synthèse sourcée.
- `memory_retain(content)` : enregistrer un fait durable, jamais un secret ni un journal transitoire.

Souvenirs datés : vérifier l'état réel avant de l'affirmer ; recouper une réponse importante avec les sources.
