# Walter Browse — le web

Obtenir des données du web vite et de façon fiable, et agir sur un site connecté comme {{owner.address}} quand c'est nécessaire. Le moteur choisit sa profondeur (requête directe, HTML, Scrapling, Camoufox, Webtop) ; l'agent décrit ce qu'il veut, pas comment l'obtenir.

**Organisation** : moteur commun avec profils appris par domaine et cache ; navigateur persistant Camoufox (`:9377`), et Chromium (CloakBrowser, `:9378`) quand un site l'exige, visible et pilotable par {{owner.address}} ; sortie réseau par sa machine avec son identité.

**Utilisation**
- Chercher, lire, extraire : `walter_browse(query=… | url=…)` (`content_only=true` pour lire une page ; `expected_fields` pour extraire).
- Agir connecté : `browser_session(site)` (cookies injectés côté serveur ; `browser_sites` liste les sites), puis `walter-browser -s <session> new|nav|snap|click|ktype|shot|close`. Rappeler `browser_session` si une page de connexion apparaît.

**Règles** : lire le web uniquement par `walter_browse` (il choisit la sortie réseau), jamais `curl`/`wget` depuis le shell ; ne jamais extraire de cookies soi-même ; frappe humaine, jamais de remplissage programmatique.
