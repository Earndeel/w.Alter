# Walter Memory — Projections d'état courant (préparation du chantier)

> Rôle : décrire comment Memory répond à « où en est X maintenant ? » pour quatre familles d'état — personnel,
> projet, relationnel, situationnel — à partir de la mémoire existante. Propriétaire : Walter Memory. État : **P1
> (projection Projet) en service depuis le 19/11/2026** (§ 7), pertinence corrigée le même jour (§ 8) ; **P2 (Personnel + Situationnel) en service depuis le 19/11** (§ 9) ; P3–P4 en projet. Ne fait pas : un second stockage, une
> seconde boucle de consolidation, une décision de modèle par message. Contrats : `MemoryViewQuery` v1
> (`memory_view`), Context. Code : `walter_memory/projection.py`, `walter_memory/personal.py`.

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
| P2 ✓ 19/11 | Personnel + Situationnel (§ 9) | « où en suis-je » : lieu, tâches ouvertes, sujet actif, règles en vigueur ; aucune donnée `local_only` vers un modèle cloud |
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
- ~~L'état d'un projet racine montre ses faits les plus récents, tels que l'extraction les a rangés (faits VIDAA sous
  `project:walter`)~~ : corrigé le 19/11 à la source (attribution) et à la lecture (pertinence), § 8.
- La ligne « Statut » ne connaît que le vocabulaire du cycle de vie. Les chaînes reposent sur le nom de la chose
  (faux positifs possibles, par exemple « gps »).
- Les plans sans budget de connaissances (L1/L2, `records` seul) n'ont pas de section « État courant ».
- Le bloc `subject:synthesis` du préflight peut recouper la section ; il n'a pas été modifié.

## 8. Pertinence de l'état courant (19/11/2026)

**Demande de Monsieur** (après validation technique de P1) : les exemples réels manquaient de pertinence — des faits
VIDAA dans l'état de w.Alter, des derniers faits techniques au lieu de l'état global, P1 « en cours » et beaucoup
d'objectifs « demandés ». Trois corrections à la source, sans nouveau pipeline ni modèle supplémentaire.

### 8.1 Attribution (`walter_memory/attribution.py`)

Tout est dit à l'assistant : le modèle d'extraction rangeait sous le projet de l'assistant (`[attribution] assistant`
dans le `projects.toml` de l'instance) ce dont parlait une session technique, même la télévision de Monsieur.
Règles déterministes, appliquées seulement quand c'est manifeste :
- l'assistant comme **locuteur ou destinataire** (« Selon W.Alter… », « Monsieur demande à W.Alter de… ») n'est
  pas un sujet : ces tournures sont retirées avant de chercher un nom ;
- un énoncé reste sous le projet de l'assistant s'il nomme ce projet ou un de ses sous-projets, ou un outil que ses
  propres connaissances citent souvent (Hermes, Claude Code… : `integrated`, calculé sur les données) ;
- sinon, s'il nomme **en tête** (110 premiers caractères) un autre projet connu → ce projet (`names_other_project`) ;
  une mention plus loin est incidente et ne déplace rien ;
- s'il parle d'**une chose de Monsieur** (« sa télévision », « sa boîte mail ») → aucun projet, sujet `other`,
  domaine `personal` (`owner_thing`) ;
- dans le **même fil**, un énoncé qui nomme la même chose qu'un énoncé déplacé le suit (`same_thing_in_thread`) ;
- un énoncé qui ne nomme rien garde le choix du modèle (inconnu n'est pas faux).

Branchement : l'extraction l'applique avant d'écrire (`extract2`, `attributes.attribution` garde l'ancienne valeur et
la règle) ; la consigne du modèle dit aussi que le projet est le sujet réel, pas la session. L'existant :
`attribution.fix(apply=)` passe par la garde avec une opération `attribute` (migration `044`), une change par
connaissance, sources, lignée et historique intacts, annulable par étiquette. Appliqué le 19/11 : **23 déplacements**
(11 choses de Monsieur, 4 autres projets, 8 voisins de fil), étiquette `attribution-2026-11-19` ; plus aucune
connaissance VIDAA sous `project:walter`.

### 8.2 Sélection déterministe de l'état (`projection.py`)

Une projection ne montre plus « les derniers faits » mais, dans cet ordre : **état global, avancées récentes,
décisions importantes en vigueur, travaux en cours, blocages, prochaines étapes connues**, puis les sous-projets.
Chaque ligne reçoit un poids calculé sans modèle, à la lecture :
- type d'acte (état +2, résultat +1, fait +1), preuve ou vérification +2, dit par Monsieur +1, projet nommé en tête +1 ;
- portée « tâche » ou domaine de tâche −3 ; ancienneté (> 30 j −1, > 120 j −2) ;
- texte : densité technique (chemins, ports, identifiants, options, unités…, au plus −4) contre vocabulaire d'état
  global en tête (en production, retiré, validé, lot, architecture, runtime… +2) ; une ligne longue −1.

L'état global garde les lignes de poids ≥ 2 (au plus 5) et **compte** le reste (« N autres faits, détails techniques
ou secondaires, consultables dans la mémoire »). Les décisions sont triées par rang (Monsieur d'abord), poids et
vigueur ; les propositions sont comptées. Les chaînes non reliées et les contradictions anciennes sur des détails
sont comptées ; une contradiction récente est toujours montrée. Les prochaines étapes = engagements ouverts et
étapes annoncées explicitement (« reste à », « en attente de son go »…), jamais une hypothèse ni une déduction.
Le budget se partage en trois tours (une ligne par section, puis le plancher, puis le reste), pour que chaque
section ait sa place à 740 tokens. Rien n'est supprimé de la mémoire : `memory_search` et `depth="state"` avec
`at=` retrouvent tout.

### 8.3 Statuts des objectifs et Run Plane (`knowledge.runplane*`, `assimilation`)

Constats : (1) le lien objectif ↔ tâche du Run Plane ne voyait que la tâche d'origine d'une session et prenait une
tâche « parapluie » comme preuve pour tous les objectifs de la session ; (2) une tâche `cancelled` (interruption :
erreur d'outil, redémarrage, message remplacé) annulait l'objectif ; (3) le rattrapage ajoute des étapes
« exécuté » sans changer le stade (voulu : pas de preuve), et beaucoup de demandes anciennes n'ont aucune trace.

Corrections :
- un objectif est relié à la tâche `objective` de **sa** demande (même session, ± 5 min), avec son rôle : `origin`
  (la demande elle-même) ou `attempt` (une reprise) ;
- seule une tâche d'origine **terminée** fait passer l'objectif à « exécuté » (jamais « vérifié » : c'est une
  déclaration d'agent) ; un échec ou une interruption ajoute une étape et garde le stade ; une reprise n'est qu'un lien ;
- le bus déclenche la mise à jour (`task.ended`, `task.updated` → file `goals.runplane`) ; l'existant :
  `knowledge.runplane_backfill(apply=)`, étiquette `runplane-2026-11-19` (12 « exécuté », 128 liens ; relance à vide = 0) ;
- à la lecture, l'état effectif est calculé : **vérifié** (Monsieur ou preuve), **annoncé terminé, non vérifié**
  (stade ou dernière étape « exécuté » d'un agent), **abandonné**, ou ouvert ; un ouvert sans nouvelle depuis 3 jours
  est « sans nouvelle depuis le …, statut inconnu » ; une demande sans aucune trace est **comptée comme statut
  inconnu**, jamais listée comme en cours ni comme prochaine étape ; les objectifs de test sont ignorés et comptés.

P1 apparaissait « en cours » parce que sa tâche du Run Plane était encore ouverte (la session continuait) et que la
validation de Monsieur n'était pas encore extraite : c'est le comportement attendu, pas un défaut.

### 8.4 Garanties et mesures

- Aucun appel de modèle à la lecture ; aucune table nouvelle ; vues `at=` inchangées (même filtre d'intervalle).
- `walter-memory state --check` sans défaut sur les 5 projets, maintenant et à `at=2026-11-12`.
- Latence (projection chaude) : W.Alter 47 ms, Walter Memory 22 ms, Walter Router 28 ms, walter-context 17 ms,
  Hermes 13 ms.
- Retour arrière : annuler le commit ; `knowledge.revert('attribution-2026-11-19', confirm=True)` et
  `knowledge.revert('runplane-2026-11-19', confirm=True)` ; la migration `044` (opération `attribute` autorisée) est
  sans effet seule. Sauvegardes : `/user/Lucas/backups/changes/2026-11-19-memoire-pertinence/`.

## 9. P2 — projections Personnel et Situationnel (19/11/2026)

Même principe que P1 : une lecture de la mémoire existante, sans table, sans cache, sans appel de modèle ; mêmes
règles de fiabilité et mêmes états effectifs des objectifs (la fonction `projection.goal_buckets` est partagée).
Code : `walter_memory/personal.py`.

**Clés** : `owner` (alias moi, monsieur, personnel) = Personnel ; `now` (maintenant, situation) = Situationnel ;
`me` = les deux, situation d'abord (« où en suis-je ? »). `memory_view(depth="state", key=…)`,
`walter-memory state owner|now|me [--at] [--check]`.

**Personnel** (`personal(at=)`) : les connaissances g1 courantes du sujet `owner`, et celles qu'une attribution a
rangées comme une chose de Monsieur (sujet `other`, domaine `personal`, § 8.1).
- **Règles en vigueur** : contraintes, corrections et décisions dites par Monsieur, durables (une règle de travail
  d'une tâche n'est pas sa règle ; ce qu'un agent croit savoir de lui non plus). Les plus réaffirmées d'abord
  (plusieurs sources), puis correction > contrainte > décision, puis la plus récente. Les préférences à part.
- **Valable jusqu'à une date** : ce qui a un `valid_to` futur (portée `until`/`task`), avec sa fin.
- **Objectifs et engagements** : bloqués, en cours, réalisés vérifiés, annoncés terminés non vérifiés, engagements
  pris pas encore commencés, sans nouvelle (statut inconnu) ; les demandes sans trace sont comptées.
- **Ce que Monsieur a dit vouloir** : ses objectifs durables sans aucune trace d'exécution, au statut inconnu.
- **Faits personnels** : dits par Monsieur ou vérifiés d'abord.
- **À revérifier** : les états passagers (portée tâche/until, ou formulés comme un état : « encore », « en
  production »…) sans date de fin et plus vieux que `state_ttl_days` (7 j, `organic.toml`).
- `at=` : l'état personnel à une date (même filtre d'intervalle que P1).

**Situationnel** (`situation()`, maintenant seulement) — chaque ligne dit sa fraîcheur :
- **Lieu** : `whereabouts.current` (domicile, lieu connu, ou distance au domicile ; « ancien » au-delà de 2 h).
- **Agenda (7 jours)** : événements `calendar.event` confirmés (le dernier état de chaque événement), sinon le
  prochain ; l'heure de la dernière synchronisation (`ingestion.connectors`).
- **Travaux ouverts** : objectifs du Run Plane du canal propriétaire (`runs.tasks_list`), les actifs (3 jours)
  listés, les autres « sans nouvelle, statut inconnu » comptés au-delà de deux.
- **Fil en cours** : l'état de travail du fil (`working.state`) quand un appel donne la session (CLI) ; dans
  Context il est déjà servi par sa propre section.
- **Appris ces 3 derniers jours** : les sujets qui ont reçu des connaissances, ou la date de la dernière écriture
  de l'extraction (un retard d'extraction se voit).
- **Période et épisodes** : la vue du jour et de la semaine (`period:day:…`, `period:week:…`) et les épisodes des
  7 derniers jours.

**Confidentialité** (critère P2) : pour un lecteur cloud, ces deux projections ne lisent que la classe
`cloud_allowed`, quel que soit le plafond cloud de Context (`organic.toml [privacy] cloud_context`). Une ligne locale
(position, lieux, épisodes et vues de période locaux, rendez-vous ou règles `local_only`) est **comptée, jamais
rendue** (« N locales non transmises »). Le bloc position de Context, qui suit le plafond, est inchangé. Un lecteur
local (`max_privacy="local_only"`) reçoit tout. `walter-memory state --check owner` vérifie qu'aucune ligne citée
n'est locale, expirée ou remplacée, ni hors de Monsieur.

**Context** : la section « État courant » sert `me` quand le message demande l'état de Monsieur lui-même (« où en
suis-je », « mon état », « ma situation », « ce que j'ai en cours », « mes engagements »…, sans nom de projet ;
`personal.ME_HINT`, sans modèle). Même budget que P1 (pris sur les connaissances libres et les cartes). Elle ne
répète ni les règles déjà servies par la section `rules`, ni les tâches de la section `tasks`.

**Mesures du 19/11** (données réelles, chaud) : Personnel 17–25 ms (504 connaissances, 12 locales comptées) ;
Situationnel 27–29 ms (agenda : bornes calculées pour élaguer les partitions à la planification, 140 ms → 1 ms) ;
Context complet « Où en suis-je ? » 260–490 ms, section 717 tokens pour 740 de budget ; `--check` sans défaut.

**Limites** : l'extraction n'a rien écrit pour Monsieur depuis le 14/11 (quota) : l'état personnel s'arrête là et la
section « Appris » le montre. Le lieu n'est jamais rendu à un lecteur cloud ; une question qui en dépend passe par
le bloc position. Beaucoup d'objectifs anciens restent « sans trace » : comptés, jamais présentés comme en cours.
