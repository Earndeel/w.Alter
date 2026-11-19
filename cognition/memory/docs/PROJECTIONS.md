# Walter Memory — Projections d'état courant (préparation du chantier)

> Rôle : décrire comment Memory répond à « où en est X maintenant ? » pour quatre familles d'état — personnel,
> projet, relationnel, situationnel — à partir de la mémoire existante. Propriétaire : Walter Memory. État : projet
> (préparé le 19/11/2026, rien d'implémenté). Ne fait pas : un second stockage, une seconde boucle de consolidation,
> une décision de modèle par message. Contrats : `MemoryViewQuery` v1 (`memory_view`), Context.

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
   - À trancher par Monsieur : faut-il fusionner les sous-projets dans leur projet parent ?
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
