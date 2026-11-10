# walter-core — le harnais

Branche les modules de W.Alter dans chaque runtime sous les mêmes noms d'outils, sans remplacer le runtime ni ses permissions.

**Utilisation**
- Chaque module se présente ici (niveau 1). Pour aller plus loin : `module_index(module, section)` liste ce qu'il contient ; `module_guide(module)` donne son guide détaillé.
- `walter_health` : état de la pile ; `walter_modules` : déclarations techniques des modules.
- `walter_run(request, goal)` : déléguer un travail à Walter Engine (session déléguée, sous sa politique). Prévenir le propriétaire : `walter-telegram send`.
