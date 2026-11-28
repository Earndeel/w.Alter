# runtime — environnement Python partagé de Walter

| | |
|---|---|
| **Rôle** | Fournir l'environnement Python partagé des modules Walter. |
| **Propriétaire** | walter-runtime (`/walter/ops/runtime`). |
| **État** | **active** (constat du 09/11/2026) : fondation sans service. |
| **Ne fait pas** | Contenir le code d'un module. Être appelé par le chemin de l'interpréteur (toujours `walter-python`). |
| **Contrats** | [contracts/runtime.json](contracts/runtime.json) ; commande `walter-python` ; `requirements.lock`, `requirements-dev.lock`. |

Fondation : un seul environnement Python pour les modules qui partagent les mêmes dépendances (memory, logs,
bus, skills, secrets, context, hooks de core). Interface : la commande `walter-python` (sur le PATH), jamais le
chemin de l'interpréteur.

- `requirements.lock` : versions exactes (production) ; `requirements-dev.lock` : outils de test.
- `venv/` : reconstruisible, hors git et hors export :
  `uv venv --python /usr/bin/python3.12 venv && uv pip install --python venv/bin/python -r requirements.lock -r requirements-dev.lock`
- Ajouter une dépendance : l'ajouter au lock, réinstaller, relancer les tests des modules consommateurs.

Les modules qui ont des dépendances propres et incompatibles gardent leur propre environnement (core, llm,
router, raw-vault).
