# Relais Access de Walter Web (`walter-web-gate`)

| | |
|---|---|
| **Rôle** | Entre le tunnel Cloudflare et Walter Web (`dsh-web`), pour l'adresse publique `portal.walter-ai.cloud` seulement : vérifie le jeton Cloudflare Access de chaque requête (HTTP et WebSocket) et connecte tout seul un navigateur nouveau. Cloudflare Access (code par e-mail) devient la seule connexion. |
| **Propriétaire** | core/interfaces/web. |
| **État** | En service depuis le 2026-11-15 (unité `walter-web-gate`, 127.0.0.1:3081). Tests : `node --test tests/` (8/8). |
| **Ne fait pas** | Ne remplace pas Access (il s'appuie dessus) ; ne touche pas au noyau du moteur ; ne sert pas le tailnet (qui atteint `dsh-web` directement, avec son lien à jeton) ; ne garde aucun secret à lui. |
| **Contrats** | Entrée : requêtes du tunnel avec `Cf-Access-Jwt-Assertion`. Sortie : `127.0.0.1:3080`. Réglages : `@instance/config/core/web-gate.json` (hôte public, équipe et audience Access, e-mails admis, fichier `login-url`). |

## Fonctionnement

1. Jeton Access absent, invalide (signature RS256 des clés de l'équipe, audience, émetteur, expiration) ou e-mail non
   admis, ou autre hôte : **403**, Walter Web n'est jamais atteint (comble l'écart noté le 2026-11-14).
2. Navigation refusée par Walter Web (401 = navigateur sans son cookie) : le relais lit le jeton de lancement dans le
   fichier `login-url` (relu à chaque fois, il change à chaque redémarrage), l'échange sur la boucle locale contre le
   cookie de Walter Web, et renvoie ce cookie avec une page qui se recharge (le rechargement part du site, donc le cookie
   `SameSite=Strict` est envoyé). Un cookie témoin de 30 s empêche toute boucle.
3. Tout le reste passe tel quel.

Le jeton de lancement ne quitte jamais la VM et n'est jamais journalisé. Le Worker `../edge` reste en place (inoffensif,
devenu redondant).

**Retour arrière** : remettre `http://127.0.0.1:3080` dans l'entrée `portal.walter-ai.cloud` de
`/services/cloudflared/config/config.yml`, redémarrer `cloudflared-tunnel`, puis `systemctl disable --now walter-web-gate`.
