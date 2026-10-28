### Walter Backup — protéger et restaurer

Façade unique sur les mécanismes de sauvegarde existants (PostgreSQL, state.db, offsite chiffré, tests de restauration) et sur git. Fonctionne sans les autres modules ni modèle.

**Utilisation**
- `walter-backup status` : trois réponses séparées — conformité du code, santé de chaque sauvegarde, dernière restauration prouvée.
- Avant une modification risquée : `walter-backup checkpoint --level git --scope <dépôt>` (code, recette), `--level files --scope <module>`, `--level db --schema <schéma>` (migration). La commande rend la marche à suivre pour revenir en arrière ; elle ne restaure jamais elle-même.
- `walter-backup git` : dépôts Walter, travail non commité et son âge.

Une restauration réelle se fait seulement avec l'accord de {{owner.address}}.
