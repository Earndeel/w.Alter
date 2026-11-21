# walter-logs — ce que les agents ont fait

Journal brut de toutes les sessions d'agents (Hermes et ses profils, Claude Code, Codex, DSH) : messages, raisonnements, appels d'outils avec arguments complets, résultats complets, résumés de compaction. Walter Memory garde la vie de {{owner.address}} ; walter-logs garde le travail des agents.

**Organisation** : schéma `walter_logs` (sessions, événements), append-only, secrets masqués à l'écriture, synchronisé en quelques secondes depuis chaque runtime.

**Utilisation**
- `logs_search(query, runtime, event_type, tool, since)` : mots ou chaîne exacte (chemin, erreur, identifiant) ; chaque résultat porte `session#seq`.
- `logs_timeline(session, seq)` : le déroulé autour ; `logs_get(session, seq)` : un événement en entier.

Pour retrouver comment une tâche a été menée, une commande exacte, ou ce qui précédait une compaction.
