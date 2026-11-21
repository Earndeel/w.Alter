---
name: torrent-harvest
description: Use when Monsieur wants a torrent — scan index, best magnet.
---

# torrent-harvest — index torrent multi-sites

Outil : `/root/hermes_workspace/kaeydcrqyhbhfzcjvzfnwy/torrent-harvest/` (harvest.py + sites.json).

## Usage
`python3 harvest.py "requête" [--type films|series|anime|fr|general] [--limit N] [--json]`
Scanne toutes les sources actives en parallèle, score (seeders + bonus FR + bonus 1080p/2160p + malus CAM/TS), sort le meilleur magnet en tête. `--json` pour output machine.

## Recettes par source (bypass documenté, vérifié 18/09/2026)

### API JSON ouvertes (aucun bypass requis, requests/aiohttp suffisent)
- **apibay** (API Pirate Bay, `https://apibay.org`) : GET `q.php?q=<mot>`.
  Pièges : requête SENSIBLE à la casse (toujours lower()), multi-mots cassé → query sur le 1er mot puis filtrage client ; exclure FRENCH/VF du filtre (bonus score, pas filtre).
- **yts** (films) : `yts.mx` mort NXDOMAIN mondial ; API actuelle `https://movies-api.accel.li/api/v2/list_movies.json?query_term=` (fallback `yts.lt` — le site annonce lui-même la migration).
  Schéma 2026 : `seeds` (pas seeders), `size_bytes` fourni, `size` = string « 463.81 MB ».
- **solidtorrents** (`https://solidtorrents.to`) : GET `/api/v1/search?q=&sort=seeders`.
  Pièges : clé `infohash` (pas info_hash) ; rate-limit occasionnel → réponse non-JSON, retourner [] sans crash.
- **nyaa** (`https://nyaa.si`) : HTML `?f=0&c=0_0&q=` (c=3_1 anime). Tailles en `GiB` binaire (parseur : accepter GiB/MiB ET Gigabyte). infoHash 40-hex dans le HTML de la ligne, magnet reconstruit.

### HTML simple (curl + UA navigateur suffit, pas de Cloudflare)
- **knaben** (`https://knaben.org`) : search `/search/<q>`. Lignes `<tr data-id="<40hex>">` avec magnet complet + [catégorie, titre, taille, date, seeders, leechers, source]. Titre = ancre `<a>` la plus LONGUE (les courtes = catégorie/source). Source massive multi-catégories. Ajout 18/09/2026.
- **bitsearch** (`https://bitsearch.to`) : search `/search?q=`. Hash + slug via `/download/torrent/<HASH>?title=<slug>` + magnet complet dans la carte. Taille/seeders absents du HTML simple (0), magnets valides. Ajout 18/09/2026.
- **torlock** (`https://www.torlock.com`) : torrents VÉRIFIÉS ✓. Search `/all/torrents/<q>-1.html`, parse par ancres `tl-name` (le markup `<tr>` varie !), fenêtre de 700 chars pour size/seeders, puis page détail pour le magnet. Titres avec `>` en tête → lstrip. Ajout 18/09/2026.
- **fitgirl** (`https://fitgirl-repacks.site`) : #1 mondial repacks jeux (Top 5 TorrentFreak 2026). WP search `/?s=` → posts `rel="bookmark"` → magnet complet dans chaque post + taille "Repack Size". Lent (4 posts séquentiels ~40s) mais unique pour les jeux. Ajout 18/09/2026.
- **torrentfunk** (`https://www.torrentfunk.com`) : search `/?q=`. Lignes `<tr>` avec `/torrent/<id>/<slug>.html` + taille + seeders. PAS de magnet dans la page détail — y extraire le 40-hex et reconstruire le magnet. Fix encodage : decode utf-8/ignore (octets invalides).
- **torrentdownloads** (`https://torrentdownloads.pro`) : search `/search/?search=`. Page détail `/torrent/<id>/<slug>` contient le magnet COMPLET. Même fix encodage.

### EZTV — cas d'école d'API menteuse (18/09/2026)
L'API `/api/get-torrents` a migré sur `eztvx.to` et répond (200, JSON, magnet_url) mais **ignore search_words** : renvoie les derniers ajouts. La search HTML = POST avec jeton CSRF (403 en POST nu). Adapter eztv corrigé dans harvest.py (search_words + seeds + filename + magnet_url) mais source désactivée tant que la search ne marche pas. Ne pas croiser une API 200 avec une API fonctionnelle.

### Classement TorrentFreak 2026 (official, croisé avec r/VideoToolbox)
1. YTS.bz 2. 1337x 3. NYAA.si 4. The Pirate Bay 5. FitGirl Repacks 6. EXT.to 7. EZTVx.to. Couverture harvest : apibay (=TPB), yts, nyaa, fitgirl, knaben, solid, torlock, bitsearch, tfunk, tdl. Manquants du classement : 1337x (Turnstile), EXT.to (Cloudflare, 403), YTS.bz (l'API officielle est movies-api.accel.li, déjà intégrée).

### Tor / darknet (18/09/2026)
Tor installé (`apt install tor`, service systemd auto). SOCKS5 sur `127.0.0.1:9050`, bootstrap ~2 min au premier lancement. Clearnet comme onion OK une fois `Bootstrapped 100%`.
- **tpb-tor** : The Pirate Bay .onion officiel `piratebayo3klnzokct3wt5yyxb2vpebbuyjl7m623iaxmqhsd52coid.onion` (adresse publiée sur thepiratebay.org clearnet). Mêmes endpoints que apibay (`/q.php`, `/t.php`). Flag `"tor": true` dans sites.json → session SOCKS dédiée via `aiohttp_socks.ProxyConnector` (paquet `aiohttp-socks`, installé avec `--break-system-packages`).
- **Pièges** : (1) ne JAMAIS recopier une adresse .onion de mémoire — la récupérer depuis le site clearnet officiel (sinon « Invalid onion hostname ») ; (2) timeout `alive()` à 60 s pour les sources tor (premier circuit lent) ; (3) Ahmia sans JS ne rend pas les résultats (version JS obligatoire) ; (4) les résultats d'un adapter réutilisé héritent du label de l'ADAPTER — `scan_source` écrase `r["source"]` avec `src["name"]` depuis le fix 18/09.
- **Test** : `python3 harvest.py "interstellar" --json` → 15 rows `tpb-tor`, top = YIFY 1080p 1143 seeders.

### Candidats testés et écartés (18/09/2026)
- **tgx.rs** (TorrentGalaxy) : DNS OK mais search expire depuis VPS. **zooqle.com / magnetdl.com** : TLS reset (filtrage IP datacenter probable) — retenter via Camoufox. **anidex.info** : 502 serveur. **limetorrents.lol** : 403 WAF. **btdig.com** : timeout TLS. **rutracker.org** : 403 sans compte (privé de facto). **ext.to** : Cloudflare "Just a moment" (403).

### Bloquées (ne pas réessayer sans nouvel outil)
- **1337x** (`1337x.to`) : Cloudflare Turnstile — bloque aiohttp (403), Camoufox headless (page « Just a moment » en boucle) ET scrapling stealthy_fetch (15s wait). Seule une session réelle avec cookies valides passe.
- **torrent9** : domaine `.ph` squatté par parking intivesearch (fausse page de résultats). Chercher le domaine officiel courant avant réactivation.
- **eztv** : l'API `/api/get-torrents` répond 200 mais ignore le paramètre `search` (renvoie les derniers torrents) → résultats faux, dangereux.

## Méthode de diagnostic pour nouvelle source (reproducible)
1. DNS via DoH : `curl -s "https://dns.google/resolve?name=<dom>&type=A"` → NXDOMAIN = mort, chercher miroirs.
2. Probe HTTP : curl avec UA Chrome complet → 403/« Just a moment » = Cloudflare → tester Camoufox → tester scrapling stealthy_fetch (wait 15s+, network_idle).
3. Page squatteuse ? Vérifier que le title contient le sujet cherché, pas un parking pub.
4. Si API JSON : inspecter les clés réelles du payload AVANT de coder (les schémas changent : yts a migré seeders→seeds).

## Pièges
- yts.lt annonce lui-même la migration API vers movies-api.accel.li — mettre à jour si encore un move.
- Domaines torrent rotatifs : avant de faire confiance à une URL, tester le domaine courant via DuckDuckGo lite ou DoH.
- L'index sites.json est la source de vérité : y consigner tout changement (domaine mort, nouveau domaine) avec la date.
