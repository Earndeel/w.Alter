# walter-logs — guide détaillé

## Objectif

Conserver ce que les agents de W.Alter ont **fait**, quel que soit le runtime (Hermes et ses profils, Claude Code,
Codex, DSH) : messages, raisonnements, appels d'outils avec leurs arguments complets, résultats complets, résumés
de compaction, choix de modèle. Walter Memory garde la vie de {{owner.address}} ; walter-logs garde le travail des agents.
Un agent s'en sert pour retrouver comment une tâche a été menée, une commande ou une erreur exacte, ou ce qui a été
dit avant une compaction.

## Comment l'utiliser

1. `logs_search(query, runtime, event_type, tool, session, since, until)` : mots (plein texte, sans accents) ou
   chaîne exacte (chemin, message d'erreur, identifiant). Chaque résultat porte une référence `session#seq`.
2. `logs_timeline(session, seq, before, after)` : le déroulé autour d'un événement, dans l'ordre.
3. `logs_get(session, seq)` : un événement en entier, avec l'appel ou le résultat d'outil lié.

## Organisation

| Partie | Rôle |
|---|---|
| Schéma PG `walter_logs` (`sessions`, `events`) | Journal append-only, une classe de confidentialité par événement |
| `walter_memory/logs.py` | Écriture, masquage des secrets à l'écriture |
| `walter-logs-watch` | Synchronisation par inotify en quelques secondes + rattrapage horaire ; aucune minuterie |

Sources en lecture seule : `state.db` de Hermes et de ses profils, transcriptions Claude Code / Codex / DSH.

## Interfaces

| Besoin | MCP | Hermes | CLI |
|---|---|---|---|
| Chercher | `logs_search` | `walter_logs_search` | `walter-memory logs search` |
| Déroulé | `logs_timeline` | `walter_logs_timeline` | `walter-memory logs timeline` |
| Événement complet | `logs_get` | `walter_logs_get` | `walter-memory logs get` |

## Limites

- Les secrets sont masqués à l'écriture ; un secret transformé de façon inhabituelle peut échapper au masque.
- Le profil `wild` (app macOS) est `local_only` : invisible aux clients cloud (`--cloud-safe`).
- Les sessions en cours apparaissent avec quelques secondes de retard.
