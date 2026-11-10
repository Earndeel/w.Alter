# Walter Memory — structure réelle (vérifiée le 19/10/2026)

Cartographie de ce qui existe **aujourd'hui** (pas la cible : voir `ARCHITECTURE.md`). Chiffres relevés le 19/10
vers 11 h 50 UTC dans la base `hindsight` du conteneur `hindsight-pg`. Pour les mettre à jour : fin de document.

## En une phrase

Tout ce que vivent Monsieur et ses agents arrive par des **connecteurs** dans un **journal unique** (`core.events`,
jamais réécrit) ; des **traitements** en tirent un index de recherche, des faits résumés et des fiches de personnes
(Kardex) ; les agents **lisent** ensuite tout cela par une seule porte (la passerelle :8890 et ses façades), qui
vérifie à chaque lecture que l'information a le droit de sortir.

## Schéma

```
 SOURCES                         ENTRÉE                       STOCKAGE (Postgres hindsight-pg)        LECTURE
 ───────                         ──────                       ────────────────────────────────        ───────
 Hermes (state.db, 5 profils) ─┐ minuteurs walter-memory-*                                    ┌─ Hermes (fournisseur walter-memory → recall)
 Beeper (Mac, toutes messageries)┤ + walter-logs-watch     ┌──► core.events  (journal, 503 k) ──┐ │
 Gmail, Agenda Google ──────────┤                         │    core.objects (fichiers, 10,7 k) │ ├─ Claude Code / Codex : hook à chaque
 Claude Code, Codex, DSH ───────┤ hook walter_hook.py ────┤                                    │ │   message → /v1/context
 Notes des agents (retain) ─────┤ passerelle :8890 ───────┘    walter_logs (ce que les agents │ │
 Historique avant le 01/10 ─────┘ legacy_import (une fois)       ont FAIT, 647 k)              │ ├─ MCP walter : memory_recall / context /
                                                                                               │ │   search / events, person_lookup, vault_*
                    TRANSFORMATIONS                                                            │ │
                    ───────────────                                                            │ └─ CLI walter-memory (agents)
   indexeur (2 min) ──────────► search.chunks (index, 287 k morceaux dont 60 k écartés) ◄──────┤
   synthèse L3 (30 min) ──────► core.derived_items (faits, 55,5 k)  ◄──────────────────────────┤      tout passe par la règle de lecture
   import historique ─────────► core.derived_items (Hindsight + user_model, legacy_derived)     │      (read_policy) : confidentialité
   social (6 h) ──────────────► core.entities / kardex.* (personnes, relations, écarts)  ◄─────┘      actuelle, provenance, rétractations
   triage (10 min, en essai) ─► triage.decisions (rien n'est envoyé)
   confidentialité ───────────► privacy.* (classe de chaque donnée, jamais relâchée)
```

## 1. D'où viennent les données

| Source | Comment elle entre | Rythme | Volume dans `core.events` | Confidentialité par défaut | État au 19/10 |
|---|---|---|---|---|---|
| Hermes (principal + creative-factory, hephaestus, video-agent, wild) | connecteur `hermes` (lecture seule des state.db), déclenché en secondes par `walter-logs-watch`, minuteur de secours | continu | 283 794 (appels d'outils compris) | `cloud_allowed` ; profil `wild` = `local_only` | OK (dernier message Hermes 04:02, Monsieur passe surtout par Claude Code) |
| Beeper (WhatsApp, Telegram, Instagram… via le Mac) | connecteur `beeper` (API du Mac, lecture seule) ; médias → coffre chiffré | 3 min | 196 395 depuis 2018 | messages de tiers `redacted_cloud` | OK ; 1 média en échec définitif |
| Gmail | connecteur `gmail` (lecture seule, e-mails humains) | 5 min | 4 016 | `redacted_cloud` | tourne sans erreur mais **aucun e-mail nouveau depuis le 16/10** : à vérifier |
| Agenda Google | connecteur `calendar` | 5 min | 412 | — | tourne ; dernier ajout le 15/10 |
| Claude Code, Codex, DSH | hook `walter_hook.py` → `walter-memory agent-sessions` (pas de minuteur) | à chaque fin de tour | 7 176 + 2 118 + 19 | `cloud_allowed` | OK |
| Notes dictées par les agents (`retain`) | passerelle `/v1/agent-memory` | à la demande | 22 (`claude`, `walter`) | classée à l'écriture | OK, très peu utilisé |
| Historique antérieur | `connectors/legacy_import.py` (idempotent) | ponctuel | 9 238 messages Kardex | — | refait le 19/10 pour 335 souvenirs Hindsight tardifs |

Fichiers bruts (photos, vidéos, audio, documents) : `core.objects` = 10 666 objets, octets dans Google Drive
(zone claire `raw`, zone chiffrée `secure`). **Aucun n'a encore de texte dérivé** (OCR, transcription) : ils ne sont
pas cherchables par leur contenu.

## 2. Où elles sont rangées (schémas Postgres)

| Schéma | Rôle | Contenu principal | Taille |
|---|---|---|---|
| `core` | **La vérité durable.** Journal en ajout seul, 221 partitions mensuelles | `events` 503 182 (cloud 289 k, redacted 207 k, local 7,7 k) ; `event_keys` (index des identifiants) ; `objects` 10 666 ; `derived_items` 55 503 ; `source_identities` 3 637 → `entities` 3 627 (personnes) ; `relationships` 2 401 | 846 Mo |
| `search` | Index de recherche **dérivé et reconstructible** | `chunks` 286 887 morceaux (texte + plein-texte + vecteur local 256 d) ; 60 k écartés du rappel avec leur raison (`hidden_reason` : 52 k bruit, 8 k faits Hindsight marqués bruit) ; deux index vectoriels HNSW (connaissances / preuves) | 1,15 Go |
| `kardex` | Couche sociale (dépend de Walter Memory, A10) | `relationship_baselines` 899, `communication_deviations` 1 201, `claims` 361, `evidence` 426, `messages` 9 238 (ancien pipeline) | 13 Mo |
| `privacy` | Règles et détections de confidentialité | `policies`, `detections` 4 099 | < 1 Mo |
| `ingestion` | Fonctionnement des connecteurs | `connectors` (15), points de reprise, file `jobs` (médias Beeper 11 423 faits, 1 mort), `failures` | 95 Mo |
| `system` | Coûts et mesures | `model_calls` 21 824 (chaque appel de modèle, coût), `budgets`, `context_requests` 507, `agent_calls` 1 436 | 8 Mo |
| `walter_logs` | **Ce que les agents ont fait** (messages, raisonnement, outils et résultats complets, secrets masqués) | 4 930 sessions (Hermes 4 816, Claude Code 70, Codex 42, DSH 2), ~647 k événements | 2,1 Go |
| `bus` | Événements entre modules | `turn.ended` 933, `session.ended` 105, `skill.*` 58, `vault.changed` 6 | < 1 Mo |
| `triage` | Décisions d'essai sur les messages entrants | `decisions` 3 339 (mode fantôme : rien n'est envoyé) | 1 Mo |
| `legacy`, `user_model` | Ancien pipeline retiré (01/10) : sa connaissance est conservée pour examen, sa mécanique (synchronisation Qdrant, tables de routeur) supprimée le 09/11 | `memory_facts` 8 900 avec provenance et graphe (`hindsight_entities` 294), profil compilé… — en grande partie déjà dans `core.derived_items` | ~78 Mo |
| `public` | **Extensions seules** (vector, pg_trgm, pgcrypto, unaccent) depuis le 09/11 : objets de Hindsight et schémas `walter_voice` / `walter_audit` supprimés (nettoyage phase 1, base 7,72 → 5,96 Go) ; contenu dans l'archive de la phase 0 et le point de restauration de la phase 1 | — | < 1 Mo |
| `skills`, `models`, `x_research` | Autres modules (walter-skills, Walter Router…) qui partagent la base, pas la mémoire | — | 85 Mo |

Faits dérivés (`core.derived_items`) en détail :

| Origine | Statut | Nombre | Dernier ajout | Lisible par le rappel |
|---|---|---|---|---|
| Hindsight (souvenirs, observations, documents) | `legacy_derived` | 34 493 | 16/10 | oui depuis le 19/10, si non marqué bruit et rattaché à une conversation lisible (≈ 23 k) |
| Synthèse L3 des conversations Hermes (résumés, décisions, préférences, faits, tâches ouvertes) | `derived` | 10 807 | **14/10** | oui |
| Ancien compilateur de profil (`user_model`) | `legacy_derived` | 10 203 | 01/10 | seulement ≈ 300 décisions rattachées à un message ; le reste n'a pas de provenance ou n'est pas indexé |

## 3. Comment elles sont transformées

| Traitement | Ce qu'il fait | Rythme | Remarques |
|---|---|---|---|
| Indexeur (`walter-memory-index`) | découpe les messages, e-mails, faits et textes d'objets en morceaux, calcule mot-clé + vecteur local, repère les doublons entre sources ; **écarte le bruit** (raison enregistrée) | 2 min | depuis le 19/10 : injections des harnesses, relectures de transcription, sorties d'outils, blocs de mémoire déjà injectés, messages de moins de 3 mots |
| Synthèse L3 (`walter-memory-extract`) | résume chaque conversation **Hermes** en faits (via Walter Router) | 30 min | **ne produit plus rien depuis le 14/10** (dernier run : 40 conversations vues, 0 segment) ; ne lit pas Claude Code ni Codex. Reprise par la session Context engine |
| Social / Kardex (`walter-memory-social`) | relie identités → personnes, groupes, mesures de relation, écarts | 6 h | OK |
| Confidentialité | classe chaque donnée à l'entrée (`cloud_allowed` / `redacted_cloud` / `local_only`), ne relâche jamais | à l'entrée | les numéros de téléphone ne sont pas détectés (voir §5) |
| Triage (`walter-memory-triage`) | décide ignorer / retenir / prévenir / préparer une réponse pour chaque message entrant | 10 min | mode fantôme |
| Import historique | Hindsight, Kardex et user_model → `legacy_derived` (A2 : jamais promu automatiquement) | ponctuel | |

## 4. Comment elles sont lues

Une seule porte d'entrée en écriture comme en lecture : la passerelle `walter-memory-gateway` (127.0.0.1:8890), ou la
bibliothèque `walter_memory` pour les programmes locaux.

| Qui lit | Par où | Ce qu'il reçoit |
|---|---|---|
| Hermes et ses profils | fournisseur `walter-memory` → `recall` (budget bas, 6 souvenirs) avant chaque tour + outils memory_recall/retain/reflect | voir « ordre du rappel » |
| Claude Code, Codex (à chaque message) | hook → `/v1/context` (personnes 300 jetons, connaissances 600, preuves 300 si la question porte sur « quand / qui a dit ») | bloc « Mémoire W.Alter (injectée…) » |
| Tous les agents MCP | `memory_recall`, `memory_context`, `memory_search`, `memory_events`, `person_lookup`, `vault_*`, `logs_*` (walter-core → CLI `walter-memory`) | les mêmes fonctions, toujours en mode « cloud-safe » |
| Autopilot (santé, quotidien) | sondes de rappel par la passerelle | score sur 100 |

**Ordre du rappel (depuis le 19/10)** : 1) fiche Kardex des personnes nommées ; 2) faits dérivés (L3 + faits
Hindsight lisibles), dédoublonnés, réordonnés par le poste `rerank` de Walter Router (3 s max, ordre local sinon) ;
3) une ou deux preuves d'origine (messages, e-mails) en appoint, davantage si la question porte sur un échange.
Avant de sortir, **chaque** ligne est revérifiée auprès de son propriétaire canonique (`read_policy`) : classe de
confidentialité actuelle, provenance lisible, pas de rétractation, contenu toujours à jour, pas de secret.

## 5. Ce qui ne fonctionne pas (19/10)

1. **Synthèse L3 arrêtée depuis le 14/10** et aveugle aux conversations Claude Code / Codex, devenues majoritaires :
   les faits récents n'existent que sous forme de messages bruts. (Session Context engine.)
2. **Fichiers bruts non lus** : 10 666 objets, 0 texte dérivé (pas d'OCR ni de transcription).
3. **Gmail** : aucun e-mail ingéré depuis le 16/10 alors que le connecteur tourne sans erreur — à vérifier.
4. **Numéros de téléphone non détectés** par la confidentialité : des faits en contenant sont `cloud_allowed` et
   peuvent sortir vers un modèle cloud (constaté pendant le banc). Décision de politique à prendre (D5).
5. **Solde OpenRouter bas (0,78 USD)** : sous 1 USD les synthèses cloud s'arrêtent ; le réordonnancement du rappel
   (0,002 USD par appel) bascule alors sur l'ordre local, moins bon (voir DECISIONS 19/10).
6. ~11 k faits Hindsight n'ont pas de conversation d'origine retrouvée et restent exclus du rappel ; la banque
   `walter-shadow` (18,7 k) n'est pas importée (doublon de la mémoire canonique).
7. Restes : 1 média Beeper en échec définitif ; une connexion `hindsight_adapter:walter-shadow` inscrite mais morte
   depuis le 14/10 (sa banque n'existe plus depuis le 09/11) ; erreurs anciennes dans `ingestion.connectors.last_error` (hermes, triage, agent_sessions) non
   effacées après correction.

## Mettre à jour ces chiffres (pour les agents)

`walter-memory health` (fraîcheur, files, budgets) ; `walter-memory stats` ; volumes : requêtes SQL sur les schémas
ci-dessus (lecture seule, `docker exec hindsight-pg psql -U hindsight -d hindsight`). Qualité du rappel :
`walter-python /opt/walter-memory/bench/recall_bench.py --bench-dir <dossier du banc> --path recall|context`
puis `bench/recall_judge.py` (le banc utilise le réordonnancement payant : ~0,06 USD par passage).
