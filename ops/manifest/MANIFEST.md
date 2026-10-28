### Walter Backup — protéger et restaurer

Façade unique sur les mécanismes de sauvegarde existants (PostgreSQL, state.db, offsite chiffré, tests de restauration) et sur git. Fonctionne sans les autres modules ni modèle.

**Utilisation**
- `walter-backup status` : trois réponses séparées — conformité du code, santé de chaque sauvegarde, dernière restauration prouvée.
- Avant une modification risquée : `walter-backup checkpoint --level git --scope <dépôt>` (code, recette), `--level files --scope <module>`, `--level db --schema <schéma>` (migration). La commande rend la marche à suivre pour revenir en arrière ; elle ne restaure jamais elle-même.
- `walter-backup git` : dépôts Walter, travail non commité et son âge.
- `walter-backup check` : surveille aussi les caches déjà suivis et le travail non suivi ancien ; archives et
  rapports conservés sont comptés séparément. Alertes G0 seulement, aucun nettoyage automatique. Âge fondé sur mtime.

Les compatibilités déclarées et les preuves historiques ne sont pas des résidus à supprimer. Voir `git.preserved_paths`
et `git.generated_patterns` dans la configuration ; détail et limites dans le README.

Une restauration réelle se fait seulement avec l'accord de {{owner.address}}.
