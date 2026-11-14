# walter-core — le harnais

Branche les modules de W.Alter dans chaque runtime sous les mêmes noms d'outils, sans remplacer le runtime ni ses permissions.

**Utilisation**
- Chaque module se présente en une ligne (D1). À la demande : `module_guide(module, depth="D2")` sa fiche d'utilisation (outils, paramètres, conventions), `depth="D3"` son guide détaillé ; `module_index(module, section)` ce qu'il contient.
- `walter_health` : état de la pile ; `walter_modules` : déclarations techniques des modules.
- `walter_run(request, goal)` : déléguer un travail à Walter Engine (session déléguée, sous sa politique). Prévenir le propriétaire : `walter-telegram send`.
