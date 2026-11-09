# Grand nettoyage de Walter Memory — audit et plan (à valider)

| | |
|---|---|
| **Rôle** | Audit de la volumétrie de la base `hindsight` et de ses dépendances, classement de ce qu'elle contient, et plan de nettoyage par phases avec les volumes récupérables estimés. Demande de Monsieur du 2026-11-09. |
| **Propriétaire** | walter-memory (exécution par la bibliothèque et les commandes de Memory, jamais par du SQL à la main). |
| **État** | **Plan, rien n'est supprimé.** Mesures du 2026-11-09 vers 12 h UTC, par agrégats (aucun contenu lu). Chaque phase demande l'accord de Monsieur. |
| **Ne fait pas** | Ne touche ni au Raw Vault (Drive), ni à `state.db` de Hermes, ni aux sauvegardes existantes. Ne change pas la règle de confidentialité. |
| **Contrats** | `core.events` append-only (déclencheur `events_append_only`) ; suppression réelle seulement par une opération de Memory tracée dans `system.purges` ; RUNBOOK § Walter Memory. |

## 1. Ce que contient la base (7,35 Go)

| Schéma | Taille | Contenu | Catégorie |
|---|---|---|---|
| `walter_logs` | 2,84 Go | journal brut des agents : 633 000 événements (Hermes 95 %) ; `tool/result` de Hermes = 866 Mo, index 754 Mo | observabilité |
| `public` | 1,62 Go | tables de Hindsight, **retiré le 19/10** ; plus aucune écriture depuis ; dump final gardé (`hindsight-final-20261019.dump`) | artefact technique |
| `search` | 1,34 Go | index de recherche : 308 000 morceaux, dont 77 800 masqués (201 Mo) et 33 000 issus de Hindsight | index (reconstructible) |
| `core` | 0,96 Go | 565 000 événements (221 partitions mensuelles), 58 900 éléments dérivés, 11 076 objets du coffre, entités | mémoire + projet + bruit (§ 2) |
| `models` | 135 Mo | Router : bancs, classements, prix, journal d'exécution | données du Router (hors périmètre) |
| `views` | 102 Mo | vues organiques g1 (191 sujets, 62 périodes, 47 épisodes) et leurs versions (90 Mo) | connaissance dérivée |
| `ingestion` | 96 Mo | connecteurs, points de reprise, files ; **gonflement** : 67 Mo pour 1 500 lignes | technique |
| `legacy` | 53 Mo | ancien pipeline (faits, arêtes Hindsight, audit) ; plus d'écriture depuis le 01/10 | artefact technique |
| `user_model` | 41 Mo | compilateur de profil de l'ère Hermes (`user-profile-compiler`, toutes les 5 min, hors registre) | technique à décider |
| `walter_voice` | 38 Mo | voix, **retirée le 19/10** | artefact technique |
| autres | ~130 Mo | bus (28 Mo), skills (28 Mo), kardex (13 Mo), system, audit, extraction, triage, runs, processing, privacy, `x_research` (vide) | divers |

### Événements de `core.events` par catégorie

| Catégorie | Sources et types | Événements | Décision proposée |
|---|---|---|---|
| **Mémoire personnelle** | Beeper (203 300), Gmail (4 100), agenda (412), localisation Overland (27 000), documents (259), Kardex hérité (9 200) | ~244 000 | **garder intégralement** |
| **Conversations avec Walter** | messages Hermes (45 000 dans 2 867 fils), Claude Code (3 400), Codex (6 500), DSH, `walter` | ~55 000 | **garder intégralement** ; classer par fil (personnel / projet Walter) sans rien supprimer |
| **Observabilité recopiée** | `tool.called` (Hermes 216 300, Claude Code 16 600, Codex 6 000), `skill.used` (16 000), `conversation.started/ended` (9 300) | ~265 000 (138 Mo + 21 Mo de clés, plus leurs index) | **retirer de `core.events`** : 100 % des `tool.called` sont présents dans `walter_logs` (vérifié appel par appel), aucun n'est indexé, aucun élément dérivé n'en dépend |

Sur les fils Hermes, 2 443 contiennent du travail technique (terminal, fichiers, skills) et portent 98 % des messages
(44 000) : l'essentiel de Hermes est du développement de Walter. 1 296 fils automatiques (tâches planifiées) n'ont
aucun message, seulement des appels d'outils.

### Dépendances relevées

- Clés étrangères entre schémas : `legacy.hindsight_fact_entities → public.entities` (bloque la suppression de
  `public` tant que `legacy` existe) ; `ingestion.connectors → core.sources` ; `kardex.* → core.entities` ;
  `views.view → core.generations`.
- Vues de compatibilité dans `public` sur `legacy` (`v_active_facts`, `v_hindsight_active_edges`,
  `v_pending_outbox`, `v_recent_audit`).
- Code qui lit encore ces schémas : `walter_memory/purge.py`, `hygiene.py`, `privacy.py`, `connectors/legacy_import.py`
  (public, walter_voice, walter_audit, user_model) ; `~/.hermes/scripts/user_profile_compiler.py` (user_model,
  actif) ; `~/.hermes/scripts/x_research_db.py` ; `memory_health_check.sh` de Hermes (walter_voice).
- **La génération g0 est encore la génération active** (pas de bascule g0 → g1 sans Monsieur) : les 44 700 éléments
  dérivés `legacy_derived` et les morceaux d'index issus de Hindsight sont encore lus par le rappel.
- Les connecteurs **produisent encore** les `tool.called` (Hermes, `agent_sessions`) : il faut corriger la source
  avant de retirer le stock, sinon il revient.

## 2. Ce qui est gardé quoi qu'il arrive

Tout le personnel (messages, e-mails, agenda, lieux, documents, Kardex, objets du coffre) ; toutes les
conversations entre Monsieur et Walter ; les décisions, travaux, incidents, motivations et enseignements du projet
(événements, éléments dérivés `decision`, `summary`, `open_loop`, vues g1, `DECISIONS.md`) ; le journal
`walter_logs` comme source canonique de l'observabilité ; les données du Router.

## 3. Plan par phases

Chaque phase : compte à blanc, sauvegarde, exécution par une commande de Memory, vérifications
(`walter-memory health`, `memory-autopilot`, banc de rappel `levels.py`, tests de Memory), retour arrière par la
restauration de la sauvegarde de la phase. Suppressions tracées dans `system.purges`.

| Phase | Contenu | Gain estimé | Réversible ? | Accord |
|---|---|---|---|---|
| **0. Archive et sauvegarde** | (a) dump complet « avant nettoyage » conservé sans rotation (restic avec étiquette dédiée + coffre chiffré Drive), **avec l'export des rôles du serveur** (absents du dump nocturne), restauration essayée (le dump de la nuit du 09/11 a déjà été restauré complètement avec succès, voir `/services/postgres/README.md` § Essais) ; (b) **archive pérenne du projet** : export lisible (Markdown + JSONL) des décisions, résumés, épisodes, vues g1, fils de conversation sur Walter et `DECISIONS.md`, dans le coffre chiffré et dans restic | — (+1,4 Go sur Drive) | — | à valider |
| **1. Artefacts retirés** | `public` (Hindsight), `walter_voice`, vues de compatibilité, puis `legacy` après lecture de ses derniers lecteurs ; `x_research` ; doublons de `walter_logs.duplicates` ; code de Memory qui les lit encore mis à jour | ~1,75 Go | par le dump de la phase 0 (et dumps finaux de Hindsight déjà gardés) | à valider |
| **2. Observabilité hors de `core.events`** | (a) corriger les connecteurs Hermes et `agent_sessions` pour qu'ils n'écrivent plus `tool.called`, `skill.used`, `conversation.*` (déjà dans `walter_logs`) ; (b) retirer les ~265 000 événements existants par une opération de Memory dédiée (exception tracée à l'append-only) | ~0,25 Go avec index | par le dump de la phase 0 | à valider |
| **3. Index de recherche** | supprimer les 77 800 morceaux masqués (doublons ou exclus), réindexer | ~0,3 Go | reconstructible depuis les sources | à valider |
| **4. Compactage** | `VACUUM FULL` des tables gonflées (ingestion, `walter_logs`, `core.events` après la phase 2), `REINDEX` | ~0,1 à 0,3 Go | sans perte | à valider |
| **5. Classement des fils** | étiqueter chaque fil de conversation « personnel » ou « projet Walter » (règles puis décision de modèle mémorisée, budget ≤ 2 €), pour que le rappel personnel ne soit plus noyé ; **aucune suppression** | — | oui | à valider |
| **6. Décisions séparées** | (a) bascule g0 → g1 puis retrait des dérivés hérités et des morceaux Hindsight (~0,1 Go) ; (b) retrait du compilateur de profil de l'ère Hermes et de `user_model` (~0,05 Go) ; (c) politique de rétention de `walter_logs` : résultats d'outils de plus de 90 jours réduits à leur début et leur empreinte, l'original restant dans l'archive de la phase 0 (~0,7 Go) | ~0,85 Go | (c) seulement par l'archive | **décisions propres de Monsieur** |

**Volumes estimés** : phases 1 à 4 ≈ **2,4 Go** (7,35 → ~4,9 Go, sans aucune perte d'information) ; avec la
phase 6 ≈ **3,25 Go** (→ ~4,1 Go). Les sauvegardes suivent : chaque dump quotidien passe d'environ 1,37 Go à
environ 0,9 Go (14 Go de dumps locaux aujourd'hui).

## 4. Ce que ce plan ne fait pas encore

- Il ne mesure pas `state.db` de Hermes (5,3 Go), qui sort avec Hermes au lot E7.
- Il ne distingue pas, à l'intérieur d'un fil, un message personnel d'un message technique : la phase 5 classe des
  fils entiers, pas des messages.
- Les estimations viennent de la taille des lignes et de la part d'index ; la place réelle n'est rendue au disque
  qu'après la phase 4.
