# Grand nettoyage de Walter Memory — audit, archive et plan

| | |
|---|---|
| **Rôle** | Audit de la volumétrie de la base `hindsight` et de ses dépendances, classement de son contenu, archive « avant nettoyage », et plan de nettoyage par phases avec risques et gains. Demande de Monsieur du 2026-11-09. |
| **Propriétaire** | walter-memory. Exécution par des commandes de Memory, jamais par du SQL à la main. |
| **État** | **Phase 0 faite et vérifiée le 2026-11-09** (§ 3) : rien n'est supprimé de Memory. Phases 1 à 5 : objectifs validés par Monsieur, **exécution destructive non autorisée** ; préparation faite (§ 4). Phase 6 : décisions fonctionnelles séparées. |
| **Ne fait pas** | Ne touche ni au Raw Vault (Drive), ni à `state.db` de Hermes. Ne change pas la règle de confidentialité. |
| **Contrats** | `core.events` append-only (déclencheur `events_append_only`) ; suppression réelle seulement par une opération de Memory tracée dans `system.purges` ; RUNBOOK § Walter Memory. Outils : `ops/memory_archive.py` (archive, vérification, restauration isolée), `ops/obs_dedup_proof.py` (preuve de la phase 2). |

**But** (Monsieur) : pas seulement libérer 2 à 3 Go, mais rebâtir une base de connaissances cohérente. La mémoire
personnelle passe en premier, l'histoire du développement est structurée, et l'observabilité devient indépendante.

## 1. Ce que contient la base (7,35 Go le 2026-11-09)

| Schéma | Taille | Contenu | Catégorie |
|---|---|---|---|
| `walter_logs` | 2,84 Go | journal brut des agents : 695 000 événements (Hermes 94 %) ; peu de lignes mortes | observabilité |
| `public` | 1,62 Go | 22 tables, 1 vue matérialisée, 4 vues et 16 fonctions de Hindsight, **retiré le 19/10**. **Contient aussi les extensions dont Memory dépend** (`vector`, `pg_trgm`, `pgcrypto`, `unaccent`) | artefact technique + socle |
| `search` | 1,34 Go | index de recherche : 318 000 morceaux, dont 77 800 masqués et 33 000 issus de Hindsight | index (reconstructible) |
| `core` | 0,96 Go | 565 000 événements (221 partitions mensuelles), 60 700 éléments dérivés, 11 076 objets du coffre, entités | mémoire + projet + observabilité recopiée |
| `models` | 135 Mo | Router : bancs, classements, prix | hors périmètre |
| `views` | 102 Mo | vues g0 et g1 et leurs versions | connaissance dérivée |
| `ingestion` | 96 Mo | connecteurs, points de reprise, files ; **gonflement** (§ 4.3) | technique |
| `legacy` | 53 Mo | ancien pipeline ; ses déclencheurs appellent des fonctions de `public` | artefact technique |
| `user_model` | 41 Mo | compilateur de profil de l'ère Hermes, **arrêté le 09/11** (table gardée) | historique, phase 6b |
| `walter_voice` | 38 Mo | voix, retirée le 19/10 | artefact technique |
| autres | ~130 Mo | bus, skills, kardex, system, audit, extraction, triage, runs, processing, privacy, `x_research` (vide) | divers |

### Événements de `core.events` par catégorie

| Catégorie | Sources et types | Événements | Décision proposée |
|---|---|---|---|
| **Mémoire personnelle** | Beeper (203 300), localisation (27 100), Kardex hérité (9 200), Gmail (4 100), agenda (412), documents (262) | ~244 000 | **garder intégralement** |
| **Conversations avec Walter** | messages Hermes, Claude Code, Codex, DSH, `walter` | ~55 000 | **garder intégralement** ; classées par fil (§ 3.2) |
| **Observabilité recopiée** | `tool.called` (239 000), `skill.used` (16 100) | ~255 000 | **retirer de `core.events`** : correspondance avec `walter_logs` prouvée événement par événement (§ 4.2) |
| **Cycle de vie des sessions** | `conversation.started` (5 269), `conversation.ended` (4 467) | ~9 700 (3,7 Mo) | **garder** : elles portent des informations absentes de `walter_logs` (§ 4.2) |

## 2. Ce qui est gardé quoi qu'il arrive

- **Le personnel** : messages, e-mails, agenda, lieux, documents, Kardex, objets du coffre.
- **Les conversations** : toutes celles entre Monsieur et Walter.
- **L'histoire du projet** : décisions, travaux, incidents, motivations et enseignements (éléments dérivés, vues,
  `DECISIONS.md`, historique git).
- **`walter_logs`**, source canonique de l'observabilité.
- **Les données du Router.**
- **Les extensions** du schéma `public`.

## 3. Phase 0 — archive et sauvegarde (faite le 2026-11-09)

### 3.1 Un seul instantané

Tout a été pris le **2026-11-09 à 12:54:26 UTC**, dans une seule transaction REPEATABLE READ
(`txid_snapshot 50239701`). Elle exporte son instantané à `pg_dump`, puis compte et exporte dedans. Dump, comptages et
archive décrivent donc le même instant. Contrôle préalable : 26 Go libres (seuil de l'outil : 12 Go).

Emplacement : `@instance/backups/memory-archive/2026-11-09-phase0/` (1,4 Go, fichiers 0600, dossiers 0700). Le
`README.md` du dossier décrit sa structure, ses formats et comment le déchiffrer.

| Partie | Contenu | Taille |
|---|---|---|
| `pg/` | Sauvegarde complète du serveur : `hindsight.dump.age` (`pg_dump -Fc`, 1,38 Go), `postgres` et `stremio_app` ; `globals.sql` (**rôles avec leurs empreintes de mot de passe, appartenances** : absents des dumps nocturnes) ; `cluster.json` (version, extensions, réglages, règles d'accès, empreintes des droits) ; `tables.json` (lignes et empreinte du contenu de chacune des 424 tables) | 1,3 Go |
| `project/` | Histoire du projet Walter : 40 257 connaissances, 109 sujets, 3 297 fils et leurs 45 325 messages, chronologie (8 329 lignes en JSONL et en Markdown mois par mois), documentation (`docs.tar`), 4 130 commits | 27 Mo |
| `personal/` | Mémoire personnelle : tous les événements des 6 sources personnelles, entités, identités, relations, catalogue du coffre, tout Kardex ; 20 432 connaissances, 191 vues ; 1 972 fils (9 868 messages) non identifiés comme développement de Walter | 39 Mo |
| `observability/` | Index des 5 447 sessions de `walter_logs` et volumes (le contenu reste dans la base et le dump) | 0,2 Mo |
| `technical/` | Inventaire des schémas historiques | — |

Tout fichier de données est compressé (zstd), puis chiffré avec **age** pour la clé de secours de l'instance.
`MANIFEST.json` donne l'empreinte SHA-256 du contenu clair et du fichier chiffré de chacun des 77 fichiers.
`memory_archive.py verify` : conforme.

### 3.2 Classement (règles, sans modèle ; chaque ligne garde sa règle)

| Objet | Projet Walter | Autres projets | Personnel | Non classé |
|---|---|---|---|---|
| Fils de conversation | 3 297 (45 325 messages) | 309 (6 099) | — | 1 663 (3 769) : 1 055 sans travail technique, 608 techniques sans projet identifié |
| Connaissances dérivées | 40 257 | 4 663 | 8 480 | 7 289 |
| Vues | 109 sujets | 3 sujets | — | 79 sujets, 62 périodes, 47 épisodes |

Par prudence, tout ce qui n'est pas sûrement du développement de Walter est rangé dans `personal/`, avec sa classe
sur chaque ligne. La phase 5 affinera les non-classés.

### 3.3 Restauration complète essayée

Le dump a été restauré dans un PostgreSQL jetable, **sans réseau**, de même image et même version (16.13), rôles
d'abord.

| Contrôle | Résultat |
|---|---|
| Empreintes des fichiers déchiffrés | conformes au manifeste |
| `pg_restore` (structure, puis données sur 4 processus, puis index, contraintes et déclencheurs) | sans erreur, 10 minutes |
| **Chaque table** | **423 tables, 4 998 149 lignes : identiques à l'instantané**, en nombre et en empreinte du contenu (md5 de chaque ligne) |
| Vue matérialisée `public.memory_units_bm25` (Hindsight) | 0 ligne en service (jamais rafraîchie), 51 839 après restauration : `pg_restore` la recalcule depuis les tables restaurées, qui sont exactes. Ce n'est pas une donnée. |
| Rôles (attributs et empreintes des mots de passe), schémas, droits (tables, schémas, par défaut), extensions, nombre d'objets (tables, index, fonctions, déclencheurs, contraintes), bases | égaux |
| Essais fonctionnels | recherche plein texte, recherche vectorielle, déclencheur append-only présent, modification refusée : tous corrects |

Rapport : `restore-check-2026-11-09T131453Z.json` dans l'archive. Le conteneur et les données d'essai ont été
supprimés ensuite.

**Incident utile.** Le premier essai, en un seul `pg_restore -j 4`, a échoué. Le déclencheur de la table partitionnée
`core.events` dépend seulement de la table mère : il a été créé pendant que des partitions se chargeaient encore, et il
a refusé les lignes restaurées. L'outil restaure désormais par sections (`pre-data`, puis `data`, puis
`post-data`), et la leçon est écrite dans `/services/postgres/README.md`. Les dumps n'étaient pas en cause.

### 3.4 Copie hors site gardée sans rotation

- **restic** (Drive, chiffré) : instantanés `8ebe9396` et `0465bcf7` (le second ajoute le README et les rapports),
  étiquettes `keep` et `memory-phase0`.
- **Rotation** : `walter-restic-backup` épargne désormais tout instantané étiqueté `keep` (`forget --keep-tag keep`).
  Le retirer demandera un `restic forget <id>` délibéré.
- **Vérification** : l'instantané a été restauré depuis Drive dans un dossier temporaire. Les 81 fichiers sont
  identiques au bit près (SHA-256), droits 0600 conservés.
- **Copie locale** : le dossier est aussi pris chaque nuit dans l'instantané `folders`.

### 3.5 Disque et secrets

- **Disque** : 26 Go libres avant (83 %), **24 Go après** (84 %).
- **Mot de passe PostgreSQL** : il n'apparaît ni dans l'archive (hors `globals.sql`, chiffré), ni dans les journaux
  de l'outil, ni dans git. L'outil laisse libpq le lire dans le fichier pgpass ; `pg_dump` passe par le socket local
  du conteneur.
- **Empreintes** : `cluster.json` ne garde qu'une empreinte MD5 de chaque vérificateur de mot de passe.

## 4. Préparation des phases suivantes (rien d'exécuté)

### 4.1 Phase 1 — lecteurs actifs des schémas historiques

**Constat bloquant pour une suppression en bloc.** Les extensions `vector`, `pg_trgm`, `pgcrypto` et `unaccent` sont
installées dans le schéma `public`. Six colonnes de `search`, `views`, `legacy` et `walter_voice` utilisent leurs
types, et la recherche plein texte de Memory appelle `public.unaccent` (`search.f_unaccent`). Un
`DROP SCHEMA public CASCADE` détruirait donc les vecteurs de recherche et la recherche plein texte.

La phase 1 supprimera **une liste explicite d'objets** : 22 tables, 1 vue matérialisée, 4 vues de compatibilité,
16 fonctions et 2 séquences de Hindsight. Elle gardera le schéma `public` et ses extensions. Les déplacer dans un
schéma dédié est une option ultérieure, non nécessaire.

Lecteurs relevés (code, tâches planifiées, unités, configuration, base) :

| Lecteur | Ce qu'il lit | Actif ? | À faire avant la phase 1 |
|---|---|---|---|
| Tâche Hermes « Memory Health Check » (`~/.hermes/scripts/memory_health_check.sh`, toutes les 5 min) | `public.memory_units` × `walter_voice.unit_vectors` ; interroge aussi l'API Hindsight et la mémoire vocale retirées, et **tente toutes les 5 min de redémarrer** `hindsight-api` et `walter-voice-memory` (unités en quarantaine) | **oui** | retirer ces blocs (garder les contrôles Memory et skills) ou retirer la tâche, déjà couverte par la vigie de 5 min |
| Contrôle mensuel de restauration (`@instance/config/backup/backup.toml`, `restore_test.compare_tables`) | compte `public.memory_units` et `public.documents` | oui, le 3 du mois | retirer ces deux tables de la liste |
| `walter_memory/purge.py` (`walter-memory purge`, bris de glace) | cherche et supprime dans `public.memory_units`, `public.documents`, `walter_voice.unit_vectors` | à la demande | ignorer les tables absentes |
| `walter_memory/privacy.py` (`walter-memory privacy-rescan`) | étiquettes de `public.documents` et `public.memory_units` | à la demande | idem |
| `walter_memory/hygiene.py` | étiquettes de `public.memory_units` | à la demande | idem ou retirer |
| `connectors/legacy_import.py` | `public`, `walter_audit`, `user_model` | non (import ponctuel du 01/10, fait) | garder comme histoire ; il ne pourra plus être rejoué (l'archive le permet) |
| Déclencheurs de `legacy.memory_facts` | appellent des fonctions de `public` ; clé étrangère `legacy.hindsight_fact_entities → public.entities` ; 4 vues de `public` sur `legacy` | plus d'écriture depuis le 01/10 | supprimer `legacy` et Hindsight **dans la même transaction** |
| `memory_dreaming.py` (tâche Hermes) | API Hindsight | en pause | retirer la tâche |
| Scripts `~/.hermes/scripts/` `hindsight_*`, `bench_hindsight`, `migrate_pg_to_qdrant`, `x_research_*` | `public`, `x_research` | non planifiés | mettre en quarantaine |
| Skill Hermes `walter-operating-mode` | `user_model` (requêtes manuelles) | doc | **corrigée le 09/11** : couche historique, Memory d'abord |

**Dépendances de g0.** Les éléments g0 (`legacy_derived` et `derived`) sont dans `core.derived_items`, et les morceaux
d'index issus de Hindsight dans `search.chunks`. Ni le rappel ni l'index ne lisent `public`. Les retirer, c'est la
phase 6a (bascule g0 → g1), pas la phase 1.

**Mesure.** Compteurs d'accès aux tables relevés le 09/11 vers 13 h (`@instance/backups/changes/2026-11-09-memory-phase1-prep/stats-t0.tsv`).
Une seconde mesure avant la phase 1 montrera qui lit encore, une fois la tâche Hermes corrigée.

### 4.2 Phase 2 — correspondance exacte avec `walter_logs`, type par type

Outil : `ops/obs_dedup_proof.py`, en lecture seule et dans un seul instantané (2026-11-09 13:18 UTC). Chaque événement
de `core.events` est apparié à son enregistrement dans `walter_logs`. Pour Hermes, l'appariement se fait par l'identifiant du
message de `state.db` ; pour les autres, par session et `call_id`. Ensuite, chaque champ est recalculé avec **les
fonctions mêmes du connecteur**. Rapport : `@instance/backups/changes/2026-11-09-memory-phase1-prep/phase2-proof.json`.

| Source et type | Total | Exact | Exact, secret masqué dans `walter_logs` | Doublon interne à `core` (jumeau identique) | Taille de sortie mesurée autrement | Écart réel |
|---|---|---|---|---|---|---|
| Hermes `tool.called` | 216 256 | 201 145 | 2 496 | 12 075 | 537 | 3 |
| Hermes `skill.used` | 16 136 | 14 414 | — | 1 716 | — | 6 |
| Claude Code `tool.called` | 16 832 | 14 477 | 104 | — | 2 226 | 25 |
| Codex `tool.called` | 5 954 | 784 | — | — | 5 166 | 4 |
| DSH `tool.called` | 10 | — | — | — | 10 | — |

Lecture du tableau :
- **Doublons internes à `core`.** Entre fin juillet et mi-octobre, Hermes a réécrit des messages d'outils dans
  `state.db`. Le connecteur a alors enregistré deux fois le même appel, sous deux identifiants de message. Chacun de
  ces 13 791 événements a, dans `core`, un jumeau au contenu identique qui, lui, est apparié.
- **Taille de sortie.** `core` garde seulement un nombre, mesuré sur le JSON du contenu ; `walter_logs` garde la
  sortie complète. Aucune information n'est perdue.
- **Secrets masqués.** 2 600 résumés d'arguments de `core` contiennent un secret que `walter_logs` a masqué à
  l'écriture. Le retrait améliore donc aussi la confidentialité.
- **Écarts réels.** 38 événements (arguments, nom d'outil, résultat manquant) : ils resteront dans `core`.

**`conversation.started` / `conversation.ended` : pas de correspondance exacte.** La plupart des écarts sont des
formes différentes de la même information : identifiant parent préfixé, nom de plateforme, titre ou modèle plus
récents dans `walter_logs`. Mais `core` porte aussi des informations **absentes** de `walter_logs` :
- le coût des sessions Hermes (3 402 sessions) ;
- `originator` et `cli_version` de Codex ;
- l'heure du premier message de Claude Code ;
- les compteurs à l'instant de la fin.

Ces événements sont peu nombreux (9 700, 3,7 Mo) et donnent à Memory le cycle de vie de chaque fil. **Proposition :
les garder.**

**Plan de la phase 2.**
1. Corriger d'abord les connecteurs Hermes et `agent_sessions`, pour qu'ils n'écrivent plus `tool.called` ni
   `skill.used`.
2. Retirer ensuite, par une opération de Memory tracée, uniquement les événements classés exacts, exacts avec secret
   masqué, doublons internes ou différant par la seule taille. L'outil de preuve est relancé juste avant, dans la même
   transaction que le retrait.

### 4.3 Phase 4 — disque et verrous

| Table | Taille | Lignes vivantes | Gonflement | Opération proposée |
|---|---|---|---|---|
| `ingestion.checkpoints` | 49 Mo | 1 483 | très fort (mises à jour continues) | `VACUUM FULL` (quelques secondes) |
| `ingestion.connectors` | 18 Mo | 17 | très fort | `VACUUM FULL` |
| `ingestion.jobs` | 29 Mo | 11 964 | fort | `VACUUM FULL` |
| `walter_logs.sessions` | 77 Mo | 9 013 | fort | `VACUUM FULL` |
| `views.version` | 92 Mo | 22 207 | modéré | `VACUUM FULL` |
| partitions de `core.events` (après la phase 2) | 693 Mo au total, la plus grosse 109 Mo | — | place libérée par la phase 2 | `VACUUM FULL` partition par partition |
| `walter_logs.events` | 2,7 Go | 694 862 | **négligeable** (198 lignes mortes) | **aucune** : la réécrire bloquerait le journal sans rien gagner |

- **Verrous.** `VACUUM FULL` (comme `CLUSTER`) prend un verrou ACCESS EXCLUSIVE pendant toute la réécriture :
  lectures et écritures de la table attendent. Avec ces tailles (≤ 110 Mo par table), cela dure quelques secondes.
  Chaque commande passe avec `lock_timeout = '5s'` et reprend si le verrou n'est pas obtenu, table par table, hors
  des fenêtres de sauvegarde (03:30–05:30 UTC). `pg_repack` (sans verrou long) n'est pas installé et n'est pas
  nécessaire à cette échelle.
- **Disque.** Il faut, le temps de la réécriture, une copie de la table et de ses index, plus le journal WAL
  (`max_wal_size` 2 Go) : au plus ~0,3 Go à la fois. Il y a 24 Go libres.
- **Phase 1 sans compactage.** `DROP TABLE` rend la place au disque immédiatement (fichiers supprimés). Le verrou ne
  porte que sur les tables supprimées, qu'aucun service ne lit une fois les lecteurs de § 4.1 corrigés.

### 4.4 Migration physique de PostgreSQL

La procédure est prête dans `/services/postgres/README.md` :
- vérifications préalables (version 16, même image, même système de fichiers, propriétaire 999:70 en 0700, montage) ;
- arrêt contrôlé des 10 services consommateurs et des sauvegardes ;
- arrêt propre du serveur, déplacement vers le vrai dossier `/services/postgres/data/` (pas un lien) ;
- contrôles, puis retour arrière.

Le déplacement est un renommage sur le même disque : il est instantané, quel que soit le volume. La faire **après**
les phases 1 à 4 sert surtout à ce que la sauvegarde complète de référence prise juste avant, et sa restauration
d'essai, portent sur ~4,9 Go et non 7,4. **Non exécutée** : accord de Monsieur requis.

## 5. Plan actualisé

Chaque phase suit le même déroulé :
1. comptage à blanc ;
2. sauvegarde du jour (modèle de la phase 0) ;
3. exécution par une commande de Memory ;
4. vérifications : `walter-memory health`, `memory-autopilot`, banc de rappel `levels.py`, tests de Memory ;
5. retour arrière possible par la sauvegarde de la phase.

Les suppressions sont tracées dans `system.purges`.

| Phase | Contenu | Gain | Risques et parades | Accord |
|---|---|---|---|---|
| **0** | Archive et sauvegarde | — (+1,4 Go local, +1,4 Go Drive) | — | **faite le 09/11** |
| **1** | Objets de Hindsight dans `public` (liste explicite, **extensions gardées**), `walter_voice`, `walter_audit`, `legacy` (même transaction), `x_research`, `walter_logs.duplicates` | **~1,75 Go**, rendus immédiatement | Extensions dans `public` : jamais de `CASCADE` sur le schéma. Lecteurs du § 4.1 corrigés d'abord. Seconde mesure des compteurs d'accès. | à valider |
| **2** | Connecteurs corrigés, puis retrait des `tool.called` / `skill.used` prouvés (§ 4.2) ; `conversation.*` gardés | ~0,2 Go (après la phase 4) | Les connecteurs réécriraient le stock : correction d'abord. Preuve relancée dans la transaction du retrait. Exception tracée à l'append-only. | à valider |
| **3** | Index de recherche : morceaux masqués supprimés, réindexation | ~0,3 Go | Reconstructible depuis les sources ; banc de rappel avant et après | à valider |
| **4** | `VACUUM FULL` des tables du § 4.3 | ~0,2 à 0,4 Go | Verrous de quelques secondes, `lock_timeout`, hors sauvegardes | à valider |
| **5** | Classement des fils (personnel / projet Walter / autres projets), en partant des règles de l'archive, puis décision de modèle mémorisée (budget ≤ 2 €) ; **aucune suppression** | — | Erreur de classement sans perte (étiquette seulement) | à valider |
| **6** | (a) bascule g0 → g1, puis retrait des dérivés hérités et des morceaux Hindsight (~0,1 Go) ; (b) `user_model` (compilateur **arrêté le 09/11**, table gardée ; 227 candidats et 192 profils postérieurs au 01/10 ne sont pas dans Memory) (~0,05 Go) ; (c) rétention de `walter_logs` (~0,7 Go) | ~0,85 Go | Décisions fonctionnelles | **décisions propres de Monsieur** |

**Total.** Phases 1 à 4 : ≈ **2,4 Go** (7,35 → ~4,9 Go), sans perte d'information ; avec la phase 6 : ≈ 3,25 Go.
Chaque dump quotidien passerait d'environ 1,37 Go à environ 0,9 Go.

## 6. Ce que ce plan ne fait pas encore

- Il ne mesure pas `state.db` de Hermes (5,3 Go), qui sort avec Hermes au lot E7.
- La phase 5 classe des fils entiers, pas des messages.
- Les gains des phases 2 à 4 sont des estimations (taille des lignes et part d'index) ; la place réelle se mesure
  après la phase 4.
