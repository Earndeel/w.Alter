### Walter Ops — installer, déployer, protéger et restaurer

Ancien walter-backup (renommé le 2026-10-29 ; `walter-backup` reste un alias exact). Façade unique sur les mécanismes de sauvegarde existants (PostgreSQL, state.db, offsite chiffré, tests de restauration) et sur git. Fonctionne sans les autres modules ni modèle.

**Utilisation**
- `walter-ops backup status` : trois réponses séparées — conformité du code, santé de chaque sauvegarde, dernière restauration prouvée.
- Avant une modification risquée : `walter-ops backup checkpoint --level git --scope <dépôt>` (code, recette), `--level files --scope <module>`, `--level db --schema <schéma>` (migration). La commande rend la marche à suivre pour revenir en arrière ; elle ne restaure jamais elle-même.
- `walter-ops git` : dépôts Walter, travail non commité et son âge.
- `walter-ops check` : surveille aussi les caches déjà suivis et le travail non suivi ancien ; archives et
  rapports conservés sont comptés séparément. Alertes G0 seulement, aucun nettoyage automatique. Âge fondé sur mtime.

Les compatibilités déclarées et les preuves historiques ne sont pas des résidus à supprimer. Voir `git.preserved_paths`
et `git.generated_patterns` dans la configuration ; détail et limites dans le README.

Une restauration réelle se fait seulement avec l'accord de {{owner.address}}.

À venir (conçu, pas encore construit) : installation propre d'un nouveau Walter, onboarding, restauration intégrale d'une instance (`walter-ops install|onboard` répondent « planned »).
