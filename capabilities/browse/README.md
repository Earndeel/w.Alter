# Walter Browse

Shared extraction/search engine, session manager and request validation. Hermes is a thin adapter in ports/hermes; MCP calls walter_browse.browse from the same package. No core import from Hermes. The runtime uses its existing isolated Scrapling Python environment, declared as a dependency.

State: WALTER_BROWSE_STATE_DIR (default: the active instance's `state/browse`, from `walter instance path`); shared across harnesses. Search credentials: WALTER_BROWSE_ENV_FILE (default: the instance's `bootstrap/browse-search.env`, mode 0600). Scrapling interpreter: WALTER_SCRAPLING_PYTHON (default `~/.venv/scrapling/bin/python`). Secrets stay server-side. Engines: plain HTTP, static HTML, Scrapling, Camoufox, Chromium (CloakBrowser) and Webtop; extraction must satisfy the same semantic contract on every path.

Compatibility: old skill scripts and universal-scraper wrapper point here. hermes_adapter.py is a legacy diagnostic adapter and is excluded from the runtime-independent import boundary; normal calls do not import it. Existing fallback and extraction behavior is preserved.

Test: python -m pytest runtime/test_*.py tests -q. Set WALTER_BROWSE_STATE_DIR to an isolated test directory. No real account needed.

## Network exits

`network/wg-exit/`: scoped WireGuard exits (container + loopback HTTP proxy) for browser sessions, `walter-wg-exit` on the PATH. See its README.

## Écran du navigateur de Walter (Selkies)

camoufox-max dessine ses fenêtres sur l'écran X :101 fourni par le conteneur `walter-browse-display` (image
linuxserver baseimage-selkies) : le propriétaire voit et pilote le navigateur de Walter (clavier, souris) depuis un
navigateur, sur l'adresse Tailscale port 3011 (HTTPS). Fichiers : `ops/browse-display-container.sh` (création du
conteneur), `ops/walter-browse-display.service` (démarrage, lien `/tmp/.X11-unix/X101`),
`ops/camoufox-max-display.conf` (complément de l'unité camoufox-max). Remplace Xvfb + x11vnc + noVNC (20/10/2026).

## Sortie réseau et identité par défaut du navigateur

Une session sans route propre sort par le sélecteur `walter-exit-default` (SOCKS `127.0.0.1:1083`, valeurs de
l'instance : `config/browse/network.toml [default]`), commun à tous les moteurs (26/10). Il choisit toutes les 20 s :
la machine du propriétaire (`walter-exit-mac` : tunnel SOCKS `127.0.0.1:1082` par `ssh mac`) tant que son VPN
WireGuard désigné (`primary_requires_vpn`, sortie France) y est connecté ; sinon la sortie WireGuard `fallback_exit`
(`network/wg-exit`), démarrée automatiquement et arrêtée dès que la machine revient sur son tunnel (même clé : jamais
les deux à la fois ; le VPN de la machine n'est jamais touché). Les deux sortent par la même IP, le changement est donc
invisible des sites ; il ne touche que les nouvelles connexions. Aucune des deux disponible : connexion refusée (jamais
l'IP du serveur). État : `walter-exit-default status`, journal `/var/log/walter-exit-default.log`.
Le navigateur garde le système du propriétaire (`/etc/walter/browse-identity.env`) ; fuseau, langues (langue
principale du pays, puis anglais), position et IP WebRTC sont déduits de l'IP de sortie, et le navigateur est relancé
avec la bonne identité quand cette IP change (contrôle toutes les 5 minutes, seulement sans session ouverte). Une
session peut toujours choisir une autre sortie (`walter-browser exit`). Fichiers : `network/exit-default/`,
`ops/walter-exit-default.service`, `ops/walter-exit-mac.service`, `ops/camoufox-max-identity.conf`.

Appareil et comportement : l'empreinte matérielle (processeur, écran, GPU, polices, graines canvas) est générée une
seule fois d'après la machine du propriétaire et figée (`device-fingerprint.json` dans le dossier de données du
navigateur) : un relancement ne ressemble jamais à un nouvel appareil. La frappe est humaine (vraies touches,
intervalles variables, hésitations ; effacement au clavier, jamais de remplissage programmatique) ; les trajectoires
de souris viennent de l'humanisation de Camoufox. Les cookies du propriétaire ne sont acceptés que par une session qui
sort par sa sortie réseau (refus sinon).


## Moteur Chromium (CloakBrowser), à côté de Camoufox

Camoufox (Firefox, `camoufox-max`, :9377) reste le navigateur par défaut. Quand un site a besoin de Chromium
(fonctions propres à Chrome, site qui refuse Firefox, accès aux internes React…), `cloakbrowser-max` (127.0.0.1:9378)
offre la même API HTTP avec CloakBrowser : un Chromium dont l'empreinte est modifiée dans le code C++ (MIT pour
l'enveloppe ; binaire gratuit v146, 58 patchs, sans clé ni compte, sur linux-arm64). Un seul serveur pour les deux
(`~/.hermes/camoufox-max/server-max.js`, choix par `CAMOFOX_ENGINE=chromium`) : mêmes règles de sortie (par défaut
`walter-exit-default`), identité réseau tirée de l'IP de sortie (fuseau, langues de la région puis anglais, IP
WebRTC, passés en options du binaire, sans émulation CDP), cookies du propriétaire refusés hors de sa sortie, même
écran :101.

Appareil : persona macOS (`--fingerprint-platform=macos`) ; une graine d'empreinte tirée une fois et figée
(`~/.cloakbrowser-max-data/device-fingerprint.json`), d'où le binaire dérive un appareil cohérent (GPU, écran,
cœurs, canvas…). Ne pas forcer de valeur isolée : la cohérence vient de la graine. Polices : celles du Mac du
propriétaire (`~/.cloakbrowser/fonts/macos`), visibles de ce seul service (`FONTCONFIG_FILE=~/.cloakbrowser/fonts.conf`).
Comportement humain : `humanize` de CloakBrowser (souris, clavier, défilement).

Usage : `walter-browser -e chromium -s <session> login SITE|new` (la session retient son moteur), MCP
`browser_session(site, session, engine="chromium")`. Fichiers : `ops/cloakbrowser-max.service` (copie dans
`/etc/systemd/system/`), binaire `~/.cloakbrowser/chromium-146.0.7680.177.3/`, journal `/var/log/cloakbrowser-max.log`.
Version la plus récente (Chromium 155, 87 patchs) : gratuite avec une connexion GitHub, une session simultanée
(`cloakbrowser login`) ; non activée.

## Sorties réseau par type de trafic (Monsieur, 28/10/2026)

Aucune sortie Browse par l'IP nue du serveur. Trois sorties, chacune fermée par défaut :

| Trafic | Sortie | Port |
|---|---|---|
| Chromium (CloakBrowser) : profil des démarches lancées en France | IP de la Freebox des parents (`walter-exit-default` : Mac sur « Lucas » ou `freebox-fr`, même IP) | `:1083` |
| Camoufox + lectures sans navigateur de `walter_browse` (sonde HTTP, HTML statique, Scrapling) | IP réelle locale du propriétaire (Mac **hors** « Lucas ») ; refus si le Mac est sur « Lucas », endormi ou hors ligne ; budget par site (`[local]` de `network.toml`) | `:1084` (`walter-exit-local`, SOCKS5 + proxy HTTP) |
| Recherche par API authentifiée par clé (Brave) | serveur (pas d'antibot, l'IP du propriétaire reste hors du volume de recherche) | — |

Le facade pose le proxy dans l'environnement du sous-processus de lecture (`_router_env`) et Scrapling le reçoit
explicitement (`WALTER_BROWSE_PROXY`, fixé à la création de sa session). Le repli Webtop (qui sort par le serveur)
est désactivé sauf `WALTER_BROWSE_WEBTOP=on`. Contrôle : `walter-exit-local probe` (JSON, code 1 en cas d'écart) ;
état : `walter-exit-local status`, journal `/var/log/walter-exit-local.log`. Fichiers : `network/exit-local/`,
`ops/walter-exit-local.service`, `ops/camoufox-max-local-exit.conf`, `/etc/walter/browse-identity-camoufox.env`.
