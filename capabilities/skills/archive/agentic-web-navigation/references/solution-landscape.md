# Paysage des solutions de navigation web agentique

## Positionnement vérifié

Les solutions se répartissent en quatre catégories, qui ne doivent pas être confondues :

- **Moteur déterministe** : Playwright/CDP contrôle précisément les pages, les formulaires, les clics et les captures. Il n’apporte pas de raisonnement agentique seul.
- **Couche agentique** : Stagehand ajoute des actions sémantiques de type `observe`, `act` et `extract` au-dessus d’un navigateur ; Browser Use fournit un agent piloté en langage naturel et une offre cloud ; Skyvern fournit des workflows plus visuels et persistants.
- **Infrastructure cloud** : Browserbase, Browserless et Steel fournissent des navigateurs distants, des sessions, du parallélisme et selon l’offre des fonctions de stealth/proxy/CAPTCHA. Ils ne remplacent pas l’orchestrateur ni la politique de collecte.
- **Extraction/anti-détection spécialisée** : Scrapling vise l’extraction adaptative et Camoufox/Camofox Browser l’anti-détection et les sessions protégées.

## Sources officielles consultées

- Browser Use : `https://browser-use.com/` et `https://browser-use.com/posts/browser-infra`
  - Positionnement : agent qui ouvre des pages, clique, saisit des formulaires et accomplit une tâche décrite en langage naturel.
  - L’infrastructure Browser Use Cloud est présentée par l’éditeur comme un navigateur stealth avec gestion de protections ; traiter ces affirmations comme des claims commerciaux à valider sur les domaines réels.

- Stagehand : `https://docs.stagehand.dev/` et `https://github.com/browserbase/stagehand`
  - Positionnement : framework de navigateur agentique code-first, avec primitives sémantiques et possibilité de rester proche de Playwright.
  - À évaluer comme couche sémantique locale avant d’adopter un navigateur cloud complet.

- Browserbase : `https://www.browserbase.com/` et `https://docs.browserbase.com/guides/authentication`
  - Positionnement : infrastructure de sessions navigateur cloud.
  - La documentation décrit notamment le stealth mode, les proxies et les mécanismes d’identité/session ; cela reste une solution distante, donc à séparer des cookies personnels.

- Skyvern : `https://www.skyvern.com/` et `https://docs.skyvern.com/browser-sessions/introduction`
  - Positionnement : workflows browser visuels et sessions longues.
  - Plus adapté aux automatisations métier répétables qu’à une simple extraction ponctuelle.

- Browserless : `https://browserless.io/`
  - Positionnement : infrastructure Playwright/Puppeteer/CDP avec offres liées au stealth, au CAPTCHA et aux navigateurs headful/proxy.
  - À comparer à Browserbase/Steel uniquement si l’on a réellement besoin de navigateurs cloud parallèles.

- Steel : `https://github.com/steel-dev/steel-browser`
  - Positionnement : navigateur sandbox orienté applications et agents, avec approche open source/self-hostable selon le déploiement.
  - Candidat à tester pour de l’infrastructure dédiée, pas un remplacement immédiat de Camoufox Max.

- Camofox Browser : `https://github.com/jo-inc/camofox-browser`
  - Positionnement : serveur de navigateur anti-détection pour agents, construit autour de Camoufox.
  - Candidat pertinent à comparer avec le serveur Camoufox Max existant ; éviter le doublon sans benchmark domaine par domaine.

- Camoufox : `https://github.com/daijro/camoufox`
  - Positionnement : navigateur basé sur Firefox avec techniques d’anti-détection.
  - Spécialisé et plus lourd/fragile qu’un navigateur de collecte normal ; à réserver aux escalades protégées.

- Scrapling : `https://github.com/D4Vinci/Scrapling`
  - Positionnement : framework de scraping adaptatif et extraction structurée.
  - Premier niveau pour lire des pages ; il ne remplace pas un navigateur lorsque la tâche exige des clics, formulaires ou état de session.

## Conclusion opérationnelle

Pour notre usage, la meilleure combinaison reste :

`recherche → Scrapling → Playwright/CDP pour interaction → Camoufox Max + cookies personnels après échec → Webtop/Brave CDP si nécessaire`

Stagehand est le candidat le plus intéressant à tester comme couche sémantique, sans remplacer le contrôle Playwright. Browser Use Cloud est le candidat le plus rapide pour un POC autonome, mais externalise davantage la session et réduit le contrôle. Browserbase/Browserless/Steel deviennent pertinents pour du volume, du parallélisme ou de l’infrastructure cloud ; Bright Data reste hors du chemin nominal.

## Règles de validation

Avant de retenir un fournisseur, vérifier sur les sites réellement visés :

- conservation et isolation des cookies ;
- import/export d’une session sans exposer les secrets ;
- compatibilité Playwright/CDP ;
- taux de pages réellement chargées, pas seulement de requêtes HTTP réussies ;
- fidélité des prix, tableaux et images ;
- latence et coût des appels LLM ;
- comportement sur CAPTCHA, login, redirections et erreurs de session ;
- possibilité de garder une route locale de secours.

Les performances annoncées par les fournisseurs ne constituent pas un benchmark indépendant. Toute décision de migration doit être précédée d’un test reproductible sur quelques domaines représentatifs.
