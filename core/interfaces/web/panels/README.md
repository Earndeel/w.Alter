# core/interfaces/web/panels — Panneaux de l'interface web

| | |
|---|---|
| **Rôle** | Afficher dans l'interface web de Walter (dsh-web) des pages servies par d'autres modules Walter : une entrée dans la barre latérale, la page dans la zone principale ; et des **liens** (Réglages › Général : une ligne titre + description + bouton « Ouvrir ↗ » qui ouvre une page dans un nouvel onglet, sans relais ; avec `section`, le lien prend une entrée entière des Réglages sous cet identifiant : un clic sur l'entrée ouvre directement la page dans un nouvel onglet ; si le navigateur refuse l'onglet, la page de secours avec son bouton s'affiche). Le serveur web relaie `<path>/…` vers le serveur du module, seulement pour un navigateur qui a passé la barrière Host/Origin et le cookie de connexion de l'interface. |
| **Propriétaire** | walter-core (interfaces). |
| **État** | En service depuis le 14/11/2026 : panneau `devboard` (tableau de développement, ops/devboard) sous `/devboard/`. Lien `model-library` (bibliothèque des modèles du Router, derrière Cloudflare Access) = page Réglages › Modèles depuis le 16/11/2026 (remplace la page Modèles de DSH, désactivée par la composition). |
| **Ne fait pas** | Lecture seule (GET/HEAD, autre méthode = 405), sauf les `POST` sous les préfixes `actions` que le panneau déclare (corps JSON ≤ 64 Kio, même barrière ; ex. les boutons du tableau, `/api/actions/`) ; ne transmet jamais le cookie ni l'en-tête `Authorization` de l'interface au module, ni les `Set-Cookie` du module au navigateur ; pas de WebSocket ; ne choisit pas quels panneaux existent (réglage de l'instance). |
| **Contrats** | Réglage `@instance/config/core/engine.toml` `[[dsh.web.panels]]` (`id`, `label`, `path` = `/nom`, `upstream` = origine http(s), `actions` facultatif = préfixes `/x/` où un `POST` est relayé) ; et `[[dsh.web.links]]` (`id`, `label`, `description` facultative, `url` https, `section` et `section_label` facultatifs) ; rendus dans le bloc géré `dsh-panels` du profil web par `walter harness install dsh`. |

## Fichiers

| Fichier | Rôle |
|---|---|
| `index.mjs` | Moitié hôte (greffon DSH) : valide la liste, monte une route préfixe par panneau sur `webServer`, vérifie `connection.requestRejection`, relaie (flux SSE compris), publie `window.__WALTER_PANELS__` (id, libellé, chemin seulement). |
| `client.js` | Moitié navigateur : entrée `sidebar.panellist` + page `main` (cadre plein écran sur `<path>/`). |
| `tests/panels.test.mjs` | `node --test tests/panels.test.mjs` |

## Ajouter un panneau

1. Le module sert sa page avec des chemins **relatifs** (ressources et API), pour fonctionner sous `<path>/`.
2. Ajouter un bloc `[[dsh.web.panels]]` dans `engine.toml`, puis `walter harness install dsh --apply` et redémarrer `dsh-web`.

## Accès

Tailnet : `http://100.91.35.121:3080` ; Internet : `https://portal.walter-ai.cloud` (tunnel Cloudflare, application
Cloudflare Access « W.Alter web », règle « Monsieur only » = code par e-mail ; le relais `../access-gate` vérifie le jeton
Access puis pose seul le cookie de connexion de l'interface : Access est la seule connexion, 15/11/2026).

## Adresse publique : le Worker de bord (`../edge/worker.mjs`)

Le cookie de connexion de l'interface est `SameSite=Strict` : une page atteinte depuis un autre site (connexion
Cloudflare Access, lien dans une messagerie) peut arriver sans lui et recevoir 401 alors que le navigateur est connecté.
Le Worker `walter-web-edge` (route de l'adresse publique, après Access) répond à ce seul cas (navigation GET venue d'un
autre site, 401) par une page qui se recharge elle-même depuis le site : le cookie part alors. Un navigateur vraiment
non connecté reçoit le 401 au rechargement (pas de boucle). Tests : `node --test ../edge/tests/edge.test.mjs`.
Déploiement : `walter-cloudflare -- wrangler deploy --config @instance/config/core/web-edge.wrangler.toml`.
