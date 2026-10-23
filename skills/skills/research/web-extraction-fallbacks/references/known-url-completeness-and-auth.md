# URLs connues : complétude et fallback authentifié

## Règle de routage

Une URL explicite est une cible d'extraction, pas une requête de découverte. Commencer par Scrapling ; utiliser `stealthy_fetch` pour les pages dynamiques, interactives ou protégées.

## Quality gate

Ne jamais considérer un HTTP 200 comme preuve de complétude. Vérifier le statut, l'URL finale, le titre, le volume de texte utile et les structures attendues. Signaler comme incomplet un shell React/Next vide, une page de login ou de challenge, des marqueurs `enable JavaScript`, des iframes, une pagination, du lazy-loading ou des endpoints/API indiquant que le HTML brut ne contient pas toute la donnée.

## Rôle de curl

`curl` est un préflight/diagnostic facultatif : headers, MIME, redirections, HTML brut, JSON embarqué, marqueurs d'hydratation et indices d'API. Il ne constitue pas l'extraction finale d'une page et son résultat partiel doit être rejeté au profit de Scrapling ou d'un navigateur rendu.

## Fallback avec session personnelle

Après un échec réel de Scrapling, si une session personnelle valide est disponible, lancer Camoufox Max full stealth dans une session isolée et injecter uniquement les cookies du domaine cible. Valider la session par du contenu protégé et l'absence de redirection login ; le nombre de cookies injectés ne suffit pas. Ne jamais transmettre ces cookies à Bright Data, à un proxy tiers ou aux logs.
