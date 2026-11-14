# Leçon d'incident 2026-08-22 — sync Beeper incomplète + extraction de profil par dimensions

Incident réel : contact hamoni14 (Irene Hsu). Deux corrections utilisateur dans la même session + une découverte d'API.

## 1. Le trou de pagination silencieux de l'API Beeper

Symptôme : une analyse "complète" déclare qu'une info n'existe pas dans la conversation (ici le nom complet du contact), alors qu'elle est dans un bloc non synchronisé de 43 messages.

Cause racine :
- L'API Beeper (`GET /v1/chats/{id}/messages`) renvoie **20 messages max par page, quel que soit le `limit` demandé** (200, 1000… → toujours 20).
- `beforeSortKey=` est **ignoré silencieusement** : chaque page redonne exactement la même chose en boucle. Idem pour tous les autres paramètres testés (`afterSortKey`, `sinceSortKey`, `fromSortKey`, `maxSortKey`, `untilSortKey`, `before=`).
- Le seul paramètre de descente qui fonctionne : **`cursor=`** alimenté avec la valeur `oldestCursor` de la réponse précédente.

Pattern correct :

```python
all_msgs, cursor = [], None
while True:
    url = f"{API}/v1/chats/{CHAT}/messages?limit=200" + (f"&cursor={cursor}" if cursor else "")
    d = fetch(url)   # Bearer token
    items = d.get("items", [])
    if not items:
        break
    all_msgs.extend(items)
    new_cursor = d.get("oldestCursor")
    if not new_cursor or new_cursor == cursor:
        break
    cursor = new_cursor
# dédoublonner par message id, trier par sortKey
```

Vérifications post-ingestion obligatoires :
- COUNT en base vs total paginé (dédupliqué par id).
- Timestamp du plus vieux message récupéré = début attendu de la conversation.
- Tout delta incrémental doit être construit sur le curseur, jamais sur "les N derniers messages".

Règle absolue : **avant de conclure "l'info n'existe pas dans la conversation", prouver que le corpus est complet**. Une info absente peut être un trou de sync, pas une absence réelle. C'est l'utilisateur qui a repéré le manquement ("elle le dit dans nos derniers échanges") — le système doit le repérer seul.

Ingestion idempotente : `WHERE NOT EXISTS (SELECT 1 FROM kardex.messages WHERE source_message_id=%s AND contact_id=%s)` — rejouable sans doublons.

Médias view-once : les placeholders sont des NOTICE "This image can only be replayed once". Le média réel est parfois en cache Mac sous `~/Library/Application Support/BeeperTexts/media/local.beeper.com/<hash>` — SCP via tailnet direct (`ssh -o BatchMode=yes lucasjouvencon@100.127.150.1`, guillemets doubles autour du chemin avec espaces), conversion WebP→PNG avant vision_analyze. Les mtime des fichiers sont en heure locale Mac (décalage avec les timestamps UTC des messages).

## 2. Extraction de profil PAR DIMENSIONS, jamais narrative

Correction utilisateur explicite à deux reprises dans la même session :
1. « pourquoi il n'y a pas plus de data concernant le style de communication » → une synthèse qualitative ne remplace pas les métriques chiffrées (latence médiane, longueur, emoji/msg, openers, rafales).
2. « pourquoi tu n'as pas extrait plus de données concernant son age et occupation ? » → l'âge ("Almost 36") et le métier ("still teaching mandarin") étaient dans le corpus depuis le début, jamais scannés champ par champ.

Procédure correcte : grille de dimensions systématique sur le corpus COMPLET :
âge · occupation · famille · nationalité/ville d'origine · routine quotidienne · santé/sport · peurs/désirs profonds · vices · possessions/achats · ex/relations passées · secrets avoués ("classified information") · argent · langues · noms cités (romans ET caractères chinois/japonais).

Chaque dimension produit soit un claim avec citation exacte + message_id, soit un négatif archivé. Les négatifs OSINT (homonymes écartés avec raison) s'archivent aussi en evidence pour ne pas re-chercher en vain à la prochaine session.

## 3. Chaîne probatoire claims/evidence — pièges SQL rencontrés

- `kardex.claims.claim` est NOT NULL → texte dans `claim`, détails structurés dans `metadata` jsonb.
- Toute erreur dans un batch psycopg2 fait rollback de TOUT le batch, y compris les INSERT réussis avant l'erreur. Après correction, tout réinsérer et vérifier que les RETURNING sont réellement committés.
- Une info qui évolue : nouveau claim avec `supersedes_claim_id`, ancien claim → `status='superseded'`, `valid_to=now()`. Jamais de delete — l'historique probatoire se conserve. Statut intermédiaire `'partial'` autorisé (ex: prénom connu, nom inconnu), remplacé par `'confirmed'` quand complété.
- Colonnes pièges : `relationship_events.date_start` (pas event_date), `open_loops.loop_type` (pas loop_name), `contacts.communication_style` pointe vers `kardex.communication_patterns`.
- Métriques : recalculer `osint-public-profile-lookup/scripts/kardex_comm_metrics.py <contact_id>` après chaque ingestion (idempotent, purge/réinsère ses propres patterns).

## 4. Résultat validé de la session (preuve que le pattern marche)

Corpus réparé : 729 → 792 messages. Identité complète extraite du bloc manquant :
- "My name is Irene" (21:55Z)
- "my Chinese is Ts Ro last name Hsu" (23:26Z) — TS=purple, Ro=soft
- Contact final : `Irene Hsu (紫柔)` ; claim identity_name confirmé (1.0) avec chaîne supersedes complète (#2 partial → #12 partial → #14 → #15 confirmed), historique probatoire conservé sans aucun delete.
