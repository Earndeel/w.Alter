# Voies officielles d'accès agent à Colab grand public

## Sources vivantes
- API REST et restriction bêta/allowlist : https://developers.google.com/colab/api/reference/rest
- Création, paramètres d'idempotence et scope : https://developers.google.com/colab/api/reference/rest/v1beta/runtimes/create
- Ressource Runtime et connexion Jupyter : https://developers.google.com/colab/api/reference/rest/v1beta/runtimes
- MCP : https://github.com/googlecolab/colab-mcp
- Dépendances MCP : https://github.com/googlecolab/colab-mcp/blob/main/pyproject.toml

Relire ces sources avant de déployer : l'existence d'une référence publique ne vaut pas autorisation d'accès de notre projet.

## MCP avec session navigateur
Le README décrit un serveur qui relie l'agent local à une session Colab dans le navigateur. Le client doit fonctionner localement sur l'appareil et supporter `notifications/tools/list_changed`. La configuration officielle lance `uvx` avec l'argument exact `git+https://github.com/googlecolab/colab-mcp` ; vérifier le `requires-python` courant (>=3.13 dans le pyproject consulté) avant installation.

Ne pas présenter ce montage documenté comme un GPU headless indépendant ou comme une connexion VM↔Mac déjà validée. Une installation du paquet ou une authentification Drive réussie ne prouve ni la session navigateur ni l'exécution CUDA.

## API headless, mais soumise à admission du projet
Service grand public : `https://colaboratory.googleapis.com`, à distinguer de Colab Enterprise. La référence indique explicitement une bêta disponible sur allowlist. Après admission du projet seulement, elle documente `gcloud services enable colaboratory.googleapis.com`.

Lire l'état du projet et obtenir l'accord avant de soumettre une demande, d'activer un service ou de modifier OAuth. Ne pas inférer l'admission à partir de Google AI Pro, d'une réponse publique HTTP 200 ou d'un token Drive/Gmail. Le scope de création exigé est exactement `https://www.googleapis.com/auth/colaboratory` ; vérifier les scopes actuels sans afficher credentials ni tokens, et réautoriser uniquement le scope requis si Monsieur accepte.

Méthodes documentées :
- `GET /v1beta/subscription` : abonnement de l'utilisateur demandeur.
- `GET /v1beta/runtimespecs` : spécifications et éligibilité de l'utilisateur.
- `GET /v1beta/runtimes` : runtimes affectés.
- `POST /v1beta/runtimes` : allocation retournant une Operation.
- `GET /v1beta/runtimes/{runtimeId}` : état et informations de connexion.
- `DELETE /v1beta/runtimes/{runtimeId}` : suppression de l'affectation ciblée.

Avant allocation, vérifier les droits, la disponibilité, les compute units et le budget autorisé. Sélectionner explicitement les champs requis `runtimeSpec.variant`, `runtimeSpec.accelerator` et `runtimeSpec.shape` à partir des spécifications effectivement disponibles, sans inventer de GPU accessible.

La création n'est idempotente que si `requestId` est fourni ; la documentation exige un UUID4. Le `runtimeId` facultatif doit respecter les contraintes RFC-1034 documentées. Valider les identifiants avant requête et ne pas les corriger silencieusement. Ne pas répéter aveuglément une allocation après timeout.

## Exécution et récupération de preuve
Le runtime est un serveur Jupyter. Utiliser l'API ou le client Jupyter standard avec `connectionInfo.url` ; fournir `connectionInfo.token` dans le header exact `X-Colab-Runtime-Proxy-Token`. Le token est court : respecter `connectionInfo.expireTime` et le renouveler via `runtimes.get` à l'approche de l'expiration. Ne jamais le journaliser ni le conserver dans une procédure.

Aucun endpoint `executeNotebook` n'est documenté dans les références consultées ; ne pas en inventer un. L'allocation n'est pas une preuve d'exécution : exiger les sorties CUDA vérifiées selon `on-demand-probe.md`. Ne supprimer que le runtime créé par notre test, puis relire l'état pour vérifier la suppression.

Tant que l'admission du projet, OAuth Colab, l'allocation et un calcul CUDA n'ont pas été vérifiés, qualifier la voie de « documentée, non opérationnellement validée ».
