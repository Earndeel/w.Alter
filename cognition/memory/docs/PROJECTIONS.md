# Walter Memory — Projections d'état courant (préparation du chantier)

> Rôle : décrire comment Memory répond à « où en est X maintenant ? » pour quatre familles d'état — personnel,
> projet, relationnel, situationnel — à partir de la mémoire existante. Propriétaire : Walter Memory. État : **P1
> (projection Projet) en service depuis le 19/11/2026** (§ 7) ; P2–P4 en projet. Ne fait pas : un second stockage, une
> seconde boucle de consolidation, une décision de modèle par message. Contrats : `MemoryViewQuery` v1
> (`memory_view`), Context. Code : `walter_memory/projection.py`.

## 1. Principe

Une projection est **une lecture**, pas une copie. L'état courant existe déjà dans `core.derived_items` depuis la
réconciliation du 19/11 :
- une **lignée** (`lineage_id`) = une propriété et ses versions ;
- la version courante = statut `derived` ou `verified`, avec `valid_to` vide ou futur ;
- les anciennes versions sont `superseded`, datées et lisibles par `knowledge.history` ;
- une contradiction non tranchée = `contested` des deux côtés.

Une projection choisit, ordonne et rend ces lignes pour une clé donnée. Elle ne réécrit rien.

- **Aucune duplication** : pas de table d'états. Ce qui peut être conservé n'est qu'un cache reconstructible (§ 4).
- **Aucune décision par message** :
  - la clé (quel projet, quelle personne, quelle situation) vient de ce qui est déjà décidé à chaque message — le
    préflight et l'état de travail (`working.state`, sujet du fil) ;
  - la projection elle-même est déterministe (requête + règles de fiabilité) ;
  - les seuls appels de modèle restent ceux de l'écriture : extraction, `memory.reconcile`, cartes de sujets. Ils
    tournent au moment où la mémoire change, pas au moment où on la lit.

## 2. Les quatre projections

| Projection | Clé | Ce qu'elle lit (existant) | Ce qu'elle rend |
|---|---|---|---|
| **Projet** | `project:<x>` normalisé (`knowledge.subject_key`) | connaissances g1 courantes du sujet ou de `attributes.projects` ; étapes du Run Plane des objectifs ; carte de sujet (`views`) | une ligne par lignée (version courante, date de fait, provenance) ; d'abord les objectifs et engagements ouverts (étape), puis les décisions et contraintes en vigueur, puis les faits d'état (dernier énoncé par nom : composant, modèle, service) ; les contestations avec les deux versions |
| **Personnel** | le propriétaire | préférences, contraintes, règles (`working.owner_rules`), objectifs durables, engagements ; portée `until`/`task` avec `valid_to` | ce qui vaut maintenant pour Monsieur ; les états de tâche au-delà de `state_ttl_days` marqués « à revérifier » |
| **Relationnel** | une entité personne (Kardex) | fiche Kardex (`person_lookup`), `kardex.relationship_baselines` et `communication_deviations` (déjà calculés), connaissances g1 du sujet `person:*` reliées par `subject_entity_ids` | qui, la relation, le rythme habituel et l'écart actuel, ce qui est en cours avec cette personne |
| **Situationnel** | maintenant | `whereabouts.current` (lieu), tâches ouvertes (`tasks_list`), sujet actif et plan du fil (`working.state`), période ou épisode courant (`periods`, `episodes`), agenda quand l'OAuth Calendar sera là | où, sur quoi, ce qui attend, ce qui arrive ; chaque ligne avec sa fraîcheur |

**Ordre de fiabilité**, commun aux quatre et déjà présent dans la garde :
1. dit ou confirmé par Monsieur ;
2. vérifié ou prouvé (Run Plane) ;
3. rapporté par un agent ;
4. tiers.

Une ligne contestée l'indique toujours. Une ligne expirée (`valid_to` passé) n'est jamais servie comme courante.

**Passé** : la même projection, avec `at=<date>`, rend l'état tel qu'il était à cette date. Elle prend les versions
dont l'intervalle `valid_from` → `valid_to` contient la date. C'est la base de « qu'est-ce qui a changé depuis… ».

## 3. Intégration

- **Context** : une section « État courant » placée avant les connaissances libres, pour la clé du sujet que le
  préflight a déjà choisi. Les questions sur le passé ajoutent les états remplacés (`HISTORY_HINT`, déjà en place).
  Le reste de Context est inchangé.
- **MCP / contrat** : `memory_view(depth="state", key="project:walter")` dans le contrat `MemoryViewQuery` existant
  (champs `version`, `watermark`, `stale`, `sources`, `deeper` → historique d'une lignée). Pas de nouvel outil.
- **CLI** : `walter-memory state <clé> [--at date]` pour les vérifications.

## 4. Fraîcheur et coût

- **Lot 1 sans cache** : un sujet compte de quelques dizaines à quelques centaines de lignes courantes. Mesures du
  19/11 : 4 113 connaissances de projet sur 248 sujets, 84 sur 28 personnes, 573 pour le propriétaire. Une requête
  indexée suffit probablement ; à mesurer avant d'ajouter quoi que ce soit.
- **Si la mesure l'exige**, un cache rendu dans `processing`. Il est indexé par (projection, clé, `watermark`), le
  `watermark` étant le dernier `core.derived_changes.change_id` qui touche la clé. Le consommateur de bus
  `memory.organic` invalide la clé à chaque événement `memory.derived` qui la concerne. Le même mécanisme existe
  déjà pour les décisions mémorisées. Ce cache reste jetable et n'est jamais une source.

## 5. Prérequis et questions ouvertes

1. **Fin du passage sur l'existant** : environ 5 300 connaissances, 120 par passage du rattrapage, sous la garde
   actuelle. Tant qu'il n'est pas fini, une projection peut encore montrer deux états non reliés.
2. **Alias de sujets** : `subject_key` règle la casse et la ponctuation, pas les alias. Par exemple, « walter » et
   « w.alter » sont unifiés, mais pas « walter » et « walter-memory » qui est un sous-projet.
   - Proposition : une table d'alias dans la configuration de l'instance (`@instance/config/memory/subjects.toml`) ;
   - à terme, des entités projet dans `core.entities`.
   - Tranché par Monsieur le 19/11 : **pas de fusion** ; une hiérarchie parent / enfant (§ 7).
3. **Liens de chaîne manquants** : le modèle de décision ne relie pas toutes les étapes d'une même chose (exemple
   réel : les états successifs de Hermes du 9 au 18/11). La projection par nom (« dernier énoncé sur X ») compense à
   la lecture : elle montre le plus récent en premier et les autres comme « antérieurs non reliés ». C'est sans
   écriture.
4. **Date du fait ≠ date de l'énoncé** : `valid_from` est la date où l'énoncé a été dit. Quand le texte date l'état
   (« depuis le 16 novembre »), l'extraction devrait remplir `valid_from` avec cette date. C'est une amélioration de
   l'extraction, pas des projections.

## 6. Lots proposés

| Lot | Contenu | Critère d'acceptation |
|---|---|---|
| P1 | projection Projet (lecture, règles de fiabilité, `at=`), CLI, `memory_view depth=state`, section Context | sur 5 projets réels : état courant juste, aucun état expiré servi, ancien état retrouvé par `at=`, latence < 50 ms, empreinte de Context inchangée hors section |
| P2 | Personnel + Situationnel | « où en suis-je » : lieu, tâches ouvertes, sujet actif, règles en vigueur ; aucune donnée `local_only` vers un modèle cloud |
| P3 | Relationnel (Kardex) | fiche + rythme + écart + en cours, pour 5 personnes, vérifié par agrégats |
| P4 | cache + invalidation par le bus, seulement si P1–P3 dépassent la latence | relecture identique avec et sans cache |

## 7. P1 — projection Projet (19/11/2026)

**Décision de Monsieur** : une projection est une lecture structurée de la mémoire existante ; les sous-projets ne
sont pas fusionnés avec leur parent.

**Catalogue et hiérarchie**
- Les projets sont lus dans les sujets courants `project:*` normalisés (`knowledge.subject_key`, au moins
  5 connaissances). Il n'y a pas de table de projets : la liste des noms est gardée 60 s par processus, le contenu
  est toujours lu en direct.
- Configuration de l'instance : `@instance/config/memory/projects.toml` (défaut neutre du module :
  `config/projects.toml`) :
  - `[aliases]` : deux graphies d'un même projet ;
  - `[parents]` : sous-projet → parent ;
  - `[subjects]` : un sujet sans préfixe qui appartient à un projet (le sujet nu « walter »).
- Sans entrée `[parents]`, un nom en deux mots dont le premier est un projet d'au moins 20 connaissances est rangé
  sous lui.
- Un sous-projet garde son propre état complet, avec son sujet, sa provenance et son historique.
- Son parent n'en reçoit que les compteurs et, sur 7 jours, au plus 4 lignes importantes :
  - un objectif bloqué ;
  - une contestation ;
  - une décision de Monsieur ;
  - un objectif réalisé ;
  - un état remplacé.
- Le parent ne reçoit jamais les faits techniques de l'enfant. Chaque ligne garde son auteur et son identifiant.

**Contenu** (sections dans cet ordre, chacune avec un plancher de lignes avant que le reste du budget soit
partagé ; pour un parent, les sous-projets passent juste après l'état)
- **État actuel** : les faits courants, du plus récent au plus ancien en date de fait.
  - Une date donnée par le texte (« depuis le 16 novembre ») compte comme début. Une date postérieure à l'énoncé est
    un plan, jamais une date de fait.
  - Un fait est marqué `incertain` quand il appartient à une chaîne non reliée, `contesté` avec l'autre version.
  - Une ligne « Statut » donne le cycle de vie du projet (actif / arrêté). Elle est lue dans les énoncés du sujet et
    dans ceux d'autres sujets qui le citent (`attributes.projects`), seulement quand le projet est le sujet
    grammatical de l'état. Elle est marquée « non vérifié » si ni Monsieur ni une preuve ne l'établit, et
    « contredit par des énoncés non reliés » si c'est le cas.
- **Objectifs et tâches** :
  - en cours, bloqués, réalisés et abandonnés récemment (14 jours), avec la dernière étape du Run Plane ;
  - une demande sans suite depuis plus de 30 jours est comptée, pas présentée.
- **Décisions et règles en vigueur** : les décisions décidées, exécutées ou vérifiées, les demandes de Monsieur,
  ainsi que les contraintes, préférences et corrections. Les propositions sont comptées, jamais présentées comme en
  vigueur.
- **Changements récents** (14 jours, `core.derived_changes`) : un remplacement cite la version en vigueur.
- **Problèmes** :
  - statut non réconcilié ;
  - objectifs bloqués ;
  - chaînes non reliées : plusieurs énoncés courants sur la même chose, non liés, étalés sur au moins 20 h. Le plus
    récent n'est pas tenu pour vérifié ;
  - contradictions avec les deux versions.
- **Prochaines étapes connues** : seulement des demandes enregistrées, jamais déduites.
- **Pied** : l'accès à l'historique (`at=`, `extract2 history --item`).

**Règles**
- Vue courante = `derived` / `verified` dont `valid_to` est vide ou futur.
- Vue `at=` = les versions (remplacées comprises) dont l'intervalle contient la date, la date de fait comptant
  comme début.
- Une connaissance expirée n'est jamais servie comme courante. `walter-memory state --check` le vérifie sur chaque
  identifiant cité.

**Intégration**
- `memory_view(depth="state", key=…, at=…)` (MCP et `views.read`).
- `walter-memory state <projet> [--at] [--list] [--check <projets…>]`.
- Context : section « État courant » avant la mémoire libre.
  - Elle n'apparaît que quand le message demande un état (« où en est… », « état », « statut ») et nomme un projet.
    La recherche est par noms et alias, sans modèle.
  - Son budget est pris sur ce qu'elle remplace : 60 % des connaissances libres plus les cartes de sujets
    (L3 : 600 + 200 → 240 + 0 + 560).
  - La mémoire libre ne répète plus aucune connaissance du projet.
- Aucun appel de modèle à la lecture, et pas de cache.
- Index de lecture seuls : migrations `041`–`043`.

**Mesures du 19/11** (données réelles, projection chaude)

| Projet | connaissances | latence médiane | max (10 lectures) |
|---|---|---|---|
| W.Alter (16 sous-projets) | 1 073 | 38 ms | 48 ms |
| Walter Memory | 369 | 19 ms | 23 ms |
| Walter Router | 361 | 19 ms | 22 ms |
| walter-context | 125 | 14 ms | 15 ms |
| Hermes | 214 | 10 ms | 23 ms |

- La vue `at=2026-11-12` est vérifiée sans défaut : W.Alter 44 ms / 851, Walter Memory 22 ms / 221, Hermes 17 ms / 215.
- La première lecture après le démarrage d'un processus prend 170–400 ms (plans de requêtes, analyse des textes).
- Préflight complet, chaud :

| Question | avant P1 | après P1 | bloc mémoire avant | bloc mémoire après |
|---|---|---|---|---|
| « Où en est w.Alter ? » | 1 714 ms | 510–610 ms | 1 076 tokens | 1 080 tokens |
| « Où en est Walter Memory ? » | 1 396 ms | 505–525 ms | 938 tokens | 1 296 tokens |

  Le gain de temps tient surtout à des caches chauds : la projection tourne en parallèle des recherches et
  n'allonge pas le préflight.
- **Budget** : le plafond de Context est inchangé (connaissances 600 + cartes 200 = 800 → connaissances 240 + état 560).
  Le nombre de tokens réellement servis monte un peu (W.Alter + 4, Walter Memory + 358), parce qu'avant les
  connaissances et les cartes ne remplissaient pas leur part. La section remplace la mémoire libre du projet ;
  elle ne s'y ajoute pas.

**Limites connues**
- L'état d'un projet racine montre ses faits les plus récents, tels que l'extraction les a rangés : au 19/11, des
  faits VIDAA sous `project:walter`. C'est un défaut d'attribution de l'extraction, pas de la projection.
- La ligne « Statut » ne connaît que le vocabulaire du cycle de vie. Les chaînes reposent sur le nom de la chose
  (faux positifs possibles, par exemple « gps »).
- Les plans sans budget de connaissances (L1/L2, `records` seul) n'ont pas de section « État courant ».
- Le bloc `subject:synthesis` du préflight peut recouper la section ; il n'a pas été modifié.
