# Abonnement Claude dans Walter Router

La route `claude-pro` utilise une session OAuth d'abonnement déclarée par l'instance dans Walter Secrets (`claude-subscription`). Aucun modèle n'est choisi dans l'adaptateur : le Router fournit l'identifiant exact et seules les entrées `verified_models` de l'instance sont proposées comme offres exécutables. Voir aussi INTEGRATION.md et EXECUTION.md.

## Transport et propriété du harness

LiteLLM traduit les `messages`, outils, paramètres et réponses. Une instance éphémère du client officiel Claude Code fournit ses en-têtes authentifiés et son bloc d'attribution technique. Un relais local authentifié construit la requête sortante avec le payload du consommateur et ce seul bloc natif. Il n'importe aucune identité Agent SDK, instruction de programmation, date, information de machine, CLAUDE.md, outil natif ou paramètre de contexte de Claude Code.

Le bloc `x-anthropic-billing-header` reste du texte système technique envoyé au fournisseur ; le déploiement ne prétend donc pas que chaque octet de contexte appartient à Walter. Les prompts/politiques internes du serveur ne sont pas observables. Si la forme du bloc natif change, l'appel échoue explicitement plutôt que d'importer du contenu inconnu.

Le client natif reçoit uniquement un accusé synthétique sans outil. La vraie réponse et ses appels de fonctions retournent directement au consommateur : la boucle d'outils est celle du harness appelant (Walter Engine pour `walter-router run`, depuis le retrait de `serve/text_agent.py` le 11/11/2026). Le transport HTTP de la passerelle rend les appels d'outils au harness appelant, comme pour les autres fournisseurs. Aucun fallback de modèle et aucun retry implicite dans ce transport ; le Router garde sa politique de fournisseurs du même modèle et ses notifications.

Chaque appel possède un relais HTTP loopback sur un port éphémère et un sous-processus borné. Ce ne sont pas des services persistants. Les deux entrées du relais sont authentifiées, le fournisseur distant est fixe, et une seule inférence est transmise par invocation. Le streaming provient du fournisseur et n'est pas une découpe après génération. Délais et fermeture du consommateur ferment le relais, la réponse distante, le client natif et son répertoire temporaire. Comme pour les autres processus, une interruption brutale de l'hôte n'est pas une annulation transactionnelle.

## Configuration de l'instance

Dans `config/llm/gateway.json`, la clé optionnelle `claude_subscription` contient :

- `enabled` : activation explicite ; false par défaut.
- `grant` : identifiant de l'autorisation Walter Secrets, défaut `claude-subscription`.
- `cli` : chemin de la CLI native compatible. Une copie dédiée peut être provisionnée sans changer la CLI globale.
- `state_dir` : répertoires privés temporaires, `@instance/...` accepté.
- `usage_log` : journal append-only de métadonnées de consommation réelle, sans contenu ni secret.
- `verified_models` : identifiants explicitement qualifiés sur le compte, jamais une assimilation automatique du catalogue à une disponibilité.

La fiche d'autorisation est de nature `subscription`, fournisseur `anthropic-claude`, responsable `walter-secrets`, stockage déclaré vers `claudeAiOauth.accessToken` d'un fichier privé compatible CLI. Seul Walter Secrets lit/renouvelle ce fichier, avec verrou interprocessus et remplacement atomique du jeton et du refresh token. Le client natif reçoit seulement l'access token en environnement ; il ne lit ni ne renouvelle le fichier.

L'environnement enfant n'hérite d'aucune clé API, ancienne passerelle ou configuration utilisateur/projet. Il ne peut pas choisir de continuer avec des crédits payants. Le registre d'abonnement n'est pas une preuve de facture : le type de compte et l'activation éventuelle d'usage supplémentaire doivent être vérifiés sur le profil.

## Plusieurs comptes

Plusieurs comptes Claude peuvent servir la même route `claude-pro` (deuxième compte ajouté le 2026-11-07). Chaque compte est un abonnement de `config/router/subscriptions.json` (`route_provider: claude-pro`, par exemple `anthropic-pro`, `anthropic-pro-2`) et une autorisation Walter Secrets (`claude-subscription`, `claude-subscription-2`). Le lien entre les deux appartient à la passerelle : `claude_subscription.accounts` dans `config/llm/gateway.json` (`{"anthropic-pro": "claude-subscription", …}`, le premier = compte par défaut). Une route ne nomme que son compte (`account`), jamais une autorisation ; un compte absent de cette table est refusé.

`execution.routes()` produit une route par compte, dans l'ordre de déclaration (rester sur le même compte garde son cache de prompt). Chaque route porte le quota de son compte : un compte au-delà de 90 % de sa semaine, ou à 100 % de sa fenêtre cinq heures, passe après les routes payantes, les autres restent devant. Un refus « rate limit » sur un compte passe tout de suite au compte suivant (les attentes de rafale ne s'appliquent qu'avant une route payante). Chaque tentative note son compte : `models.exec_log.account`, journal walter-llm, journal d'usage du pont (lignes sans compte = `anthropic-pro`). Les quotas se lisent compte par compte (`walter-router subscriptions refresh`).

Ajouter un compte : connexion PKCE officielle (lien `claude.ai/oauth/authorize`, client public de la CLI, portées `user:profile user:inference`, fenêtre de navigation privée pour ne pas reprendre le compte déjà connecté) → `@instance/state/router/claude-N/session.json` (0600), fiche `accounts/claude-subscription-N.toml`, entrée `accounts` de la passerelle, puis `declared.upsert` + `declared.bind_claude_meter` (écrivain unique des abonnements). Vérifier que le profil est un autre compte que les précédents.

## Catalogue, quotas et usage

`walter-router research --source claude_pro` lit le catalogue du compte et n'insère comme offres que les modèles qualifiés. Le cycle prix de 48 h inclut cette source. Les listes et dates de qualification appartiennent à l'instance, pas au code partagé.

`walter-router subscriptions refresh anthropic-pro` lit les vraies fenêtres cinq heures, semaine, et par famille quand le fournisseur les expose. La source est `claude_usage_api`, non une estimation des transcripts. Les métadonnées des vraies générations sont enregistrées par le pont ; l'accusé synthétique natif n'est pas comptabilisé comme génération. Les prix affichés sont le prix de revient du forfait quand il est mesurable, pas une facture API par token.

La route d'abonnement est classée avant les routes payantes du même modèle tant que le quota semaine est sous 90 % et la fenêtre cinq heures n'est pas épuisée. Une restriction explicite `provider=claude-pro` empêche toute sortie vers un autre fournisseur. Les offres `claude-pro` ne sont pas écrites comme fournisseur direct dans les configurations auxiliaires Hermes : elles passent par les interfaces Walter.

## Vérification et limites

```bash
walter-secret grants claude-subscription
walter-router research --source claude_pro
walter-router route --model IDENTIFIANT --provider claude-pro
walter-router run < requete.json
```

La requête de test peut imposer le modèle et `provider: claude-pro`, un goal complet, des toolsets explicites et un budget borné. Les diagnostics ne doivent jamais afficher le jeton ou les codes d'autorisation. Une présence au catalogue n'est pas une qualification de génération, vision ou tool use. Les appels HTTP/LiteLLM indépendants de la CLI ne sont pas qualifiés sur cette session. Certains modèles refusent le choix d'outil forcé ; l'erreur fournisseur reste explicite, sans retrait silencieux du paramètre.

Après une mise à jour du client, vérifier à nouveau les empreintes du contexte sortant et les outils. La CLI est un transport officiel utilisé dans un pont contrôlé, pas une promesse de compatibilité OAuth générale avec toute bibliothèque.
