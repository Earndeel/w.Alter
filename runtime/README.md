# runtime — environnement Python partagé de Walter

Fondation : un seul environnement Python pour les modules qui partagent les mêmes dépendances (memory, logs,
bus, skills, secrets, context, hooks de core). Interface : la commande `walter-python` (sur le PATH), jamais le
chemin de l'interpréteur.

- `requirements.lock` : versions exactes (production) ; `requirements-dev.lock` : outils de test.
- `venv/` : reconstruisible, hors git et hors export :
  `uv venv --python /usr/bin/python3.12 venv && uv pip install --python venv/bin/python -r requirements.lock -r requirements-dev.lock`
- Ajouter une dépendance : l'ajouter au lock, réinstaller, relancer les tests des modules consommateurs.

Les modules qui ont des dépendances propres et incompatibles gardent leur propre environnement (core, llm,
router, raw-vault).
