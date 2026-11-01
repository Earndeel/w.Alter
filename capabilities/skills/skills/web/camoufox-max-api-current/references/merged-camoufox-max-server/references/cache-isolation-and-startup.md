# Cache partagé Python/Node — cause racine des instabilités Camoufox (2026-08-11)

## Symptômes observés (le "serveur instable" classique)

- `/health` répond `browserConnected: true` alors que chaque `/tab/new` échoue
  avec `Target page, context or browser has been closed`.
- Après un `camoufox fetch` Python, le serveur node crashe avec
  `Invalid Extended Type at offset 0 val 7`.
- Après un fetch node, le Python camoufox dit `CamoufoxNotInstalled:
  official/stable is not installed`.

## Cause racine UNIQUE

`camoufox` (pipe Python) et `camoufox-js` (Node, utilisé par `server-max.js`)
écrivent TOUS LES DEUX dans `~/.cache/camoufox` (`INSTALL_DIR` de camoufox-js
= `userCacheDir("camoufox")`, qui ignore XDG_CACHE_HOME et hardcode
`<HOME>/.cache/camoufox`), mais avec des **formats incompatibles** :
structures `official/stable` + `version.json` différents. Chaque fetch de l'un
**casse l'autre**. Le serveur 9377 n'est donc jamais stable tant que les deux
partagent le même cache.

## Fix durable : isoler le HOME du serveur node (une seule cause, pas 3 patchs)

Préférence de Monsieur : corriger la **cause racine en une isolation**, ne pas
empiler des rustines par redémarrage. La solution retenue :

- Le process `server-max.js` tourne avec `HOME=/root/.camoufox-node-home` →
  son binaire vit dans `/root/.camoufox-node-home/.cache/camoufox`.
- Le Python camoufox garde `~/.cache/camoufox` (venv hermes-agent).
- Sessions/cookies du serveur inchangés via `CAMOFOX_DATA_DIR` (le serveur le
  respecte déjà, ligne `const CONTEXT_DIR = process.env.CAMOFOX_DATA_DIR ||
  ~/.camoufox-max-data`).
- Piège : la variable de port est **`CAMOFOX_MAX_PORT`**, PAS `PORT`
  (`onst PORT = parseInt(process.env.CAMOFOX_MAX_PORT || '9378')`). Le défaut
  dans le fichier est 9378, mais le déploiement W.Alter utilise 9377.

## Commande unique de démarrage (idempotente)

`/root/.hermes/scripts/start-camoufox-max.sh` — à lancer au reboot comme après
crash. Elle :

1. crée le HOME dédié node ;
2. si `version.json` manque dans le cache node → fetch une seule fois dans SON
   cache (`HOME=... node .../__main__.js fetch`) ;
3. si `/health` répond déjà `ok:true` → sort (idempotent) ;
4. demande à systemd de démarrer le service, qui lance Node avec
   `HOME+ CAMOFOX_DATA_DIR+ CAMOFOX_MAX_PORT` et reste l'unique superviseur ;
5. **attend un vrai test onglet** (`/tabs` → `tabId`) avant de déclarer la
   victoire — le `/health` brut peut mentir (il vérifie `browser !== null`,
   pas la connexion réelle).

## Leçon de maintenance

- /health `browserConnected: true` n'est PAS une preuve de santé. Le test réel :
  ouvrir un onglet avec un POST `/tabs` et vérifier le `tabId`.
- Ne jamais lancer un fetch du binaire "pour vérifier" — chaque fetch écrase
  l'éventuel binaire de l'autre runtime. Si le binaire Node manque, le script
  effectue le fetch dans le HOME dédié, puis systemd démarre le service avec le
  même HOME.
- Ne pas lancer un second `server-max.js` à la main : systemd est le propriétaire
  unique du port et du cycle de vie. Cela évite les collisions de port et les
  processus hérités d'un ancien `HOME`.