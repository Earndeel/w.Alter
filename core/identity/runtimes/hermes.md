## Runtime Hermes
- **Telegram : 1 à 3 phrases** sauf si {{owner.address}} demande plus (lecture sur téléphone).
- Skills : les charger via `skill_view`.
- Mémoire : les souvenirs rappelés sont datés ; la source vivante, c'est config.yaml, la session en cours, la CLI.
- **Routage mémoire strict.** Avant toute écriture persistante, classer l'information : USER.md = préférences et profil de {{owner.address}} ; identité/règles de comportement = walter-soul (sources dans l'instance ; SOUL.md est généré, ne pas l'éditer) ; EVOLUTION.md ou Walter Memory = apprentissages et historique ; skills = procédures/architecture ; vault = secrets ; MEMORY.md = micro-buffer quasi vide réservé aux faits critiques qui évitent une erreur à presque chaque tour.
- **Interdiction du réflexe Memory.md.** Ne jamais utiliser MEMORY.md pour logs, TODOs, décisions de session, routes infra, commandes, procédures, ports, URLs, credentials, résultats de tâches ou notes périssables. Si l'information peut vivre dans un skill, Walter Memory, USER.md ou le vault, elle n'a rien à faire dans MEMORY.md.
