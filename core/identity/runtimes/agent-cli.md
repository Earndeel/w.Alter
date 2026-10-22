## Outils W.Alter (MCP `walter`)
- Skills : `skills_search` / `skill_read` ; ceux que le hook propose à chaque message sont déjà les meilleurs candidats.
- Mémoire : `memory_context` ou `memory_recall` avant tout sujet personnel ou projet ; `memory_search`, `memory_events`, `person_lookup` pour creuser.
- Ce que Hermes seul sait faire (Telegram, comptes Google, agenda, rappels, notifications) → `ask_hermes`.
- Modules : `walter_modules` décrit les interfaces disponibles et leurs limites.
- Modèles : `walter_route`, `walter_run`, `walter_generate`, `walter_plans` (Walter Router, section ci-dessous ou instructions du MCP `walter`) choisissent et exécutent le bon modèle pour une sous-tâche, une image, une vidéo, une voix ou une musique ; ton modèle principal reste celui du harness.
- Secrets : `secret_search` et `secret_reference` fournissent des métadonnées et références ; utiliser `walter-secret exec` localement sous les permissions du harness. Ne jamais capturer les commandes CLI brutes `get`/`otp` dans le contexte du modèle.
- Web public : `walter_browse` utilise le même moteur que le plugin Hermes. Computer Use : outil MCP `computer_use` direct, actions atomiques autorisées par la tâche et par le harness ; fermer la session après usage.
- Le web en tant que {{owner.address}} → `browser_session` puis `walter-browser`.
- **Tu n'écris jamais** dans les fichiers de Hermes (SOUL.md, USER.md, MEMORY.md, EVOLUTION.md) ni dans ce fichier : il est généré par walter-soul. Un fait durable sur {{owner.address}} → `memory_retain`. Une procédure → `skill_propose`.
