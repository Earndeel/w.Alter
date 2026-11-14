# Walter Memory — guide détaillé

## Objectif

Garder la vérité durable de la vie de {{owner.address}} et la rendre utilisable par tous les agents : ce qui s'est passé
(messages, e-mails, agenda, conversations avec W.Alter, fichiers), ce qui en a été appris, et qui sont les personnes.
Un agent s'en sert pour répondre à une question personnelle ou de projet, retrouver qui a dit quoi et quand, et
enregistrer un fait durable. La réussite = une réponse juste et sourcée, dans un contexte borné.

## Comment l'utiliser

1. **Contexte prêt à l'emploi** : `memory_context(query)` en premier pour tout sujet personnel ou de projet
   (fiche Kardex des personnes citées, connaissances dédoublonnées, sources originales si la question porte sur
   qui/quand/quoi ; ~2 k tokens).
2. **Approfondir** : `memory_search` (connaissances + preuves originales, avec source et date ; `evidence_only`
   pour l'historique brut) ; `memory_events` pour le texte exact d'un événement canonique (filtres source, type,
   fil, date) ; `person_lookup` pour la fiche sociale complète d'une personne ; `memory_recall` pour des faits
   synthétisés ; `memory_reflect` pour une synthèse argumentée à partir des preuves permises.
3. **Écrire** : `memory_retain` enregistre un fait durable une fois (`note.recorded`). Jamais de secret, jamais de
   journal transitoire.

Les souvenirs sont des instantanés datés : vérifier l'état réel avant de l'affirmer.

## Organisation

| Partie | Rôle |
|---|---|
| `core.events` | Historique canonique append-only, idempotent, classé par confidentialité |
| `core.objects` | Registre des fichiers bruts (Raw Vault, module `raw-vault`) |
| `search.chunks` | Index plein texte multilingue + vecteurs locaux ; reconstruisible |
| `kardex.*` | Couche sociale : identités, relations, mesures, écarts de communication ; alimentée uniquement par les processeurs de Walter Memory |
| `core.derived_items`, provenance | Connaissances extraites (synthèses L3), toujours reliées à leurs preuves |
| Connecteurs (`walter-memory-*`) | Hermes et ses profils, Beeper, sessions Claude Code / Codex / DSH, index, social, extraction, triage (shadow) |
| `walter_memory.llm` | Seule porte vers les modèles : refuse `local_only`, pseudonymise `redacted_cloud`, budgets |
| Passerelle `:8890`, lib | Seules portes d'écriture |

Le journal des agents (`walter_logs`) et le bus d'événements vivent dans le même dépôt mais sont des modules
distincts (`logs`, `bus`).

## Interfaces

| Besoin | MCP | CLI |
|---|---|---|
| Contexte d'une requête | `memory_context` | `walter-memory context` |
| Recherche unifiée | `memory_search` | `walter-memory search` |
| Événements exacts | `memory_events` | `walter-memory events` |
| Personne | `person_lookup` | `walter-memory social` |
| Rappel / réflexion / mémorisation | `memory_recall`, `memory_reflect`, `memory_retain` | `walter-memory agent-memory` (JSON sur stdin) |
| Santé | `walter_health` | `walter-memory health` |

Hermes et ses profils utilisent le fournisseur de mémoire `walter-memory` (même noyau).

## Confidentialité et limites

- Classes `cloud_allowed`, `redacted_cloud`, `local_only` : les classes ne peuvent qu'être resserrées ; les outils
  MCP n'exposent que ce qui est permis au client. Le profil Hermes `wild` est `local_only`.
- Suppression réelle uniquement par `walter-memory purge` (bris de glace, simulation par défaut).
- Qualité du rappel canonique en cours d'amélioration (DECISIONS 2026-10-18) : recouper une réponse importante
  avec `memory_events` ou `memory_search`.
- Gmail / Calendar en attente d'autorisation OAuth : leur absence dans un résultat ne prouve rien.
