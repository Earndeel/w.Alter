# Walter Browse

| | |
|---|---|
| **Rôle** | Moteur commun de recherche, d'extraction et de navigation web pour tous les harnesses : sessions de navigateur, sorties réseau, validation des requêtes. Hermes et le MCP en sont des adaptateurs minces. |
| **Propriétaire** | walter-browse (`/walter/capabilities/browse`). |
| **État** | **active** (constat du 09/11/2026) : services `camoufox-max`, `cloakbrowser-max`, `walter-browse-display`, sorties `walter-exit-*`. |
| **Ne fait pas** | Montrer un secret : cookies et identifiants restent côté serveur, l'agent ne reçoit que des métadonnées. Décider de la tâche ou des permissions (le harness appelant). Conserver les pages (Memory, Raw Vault). |
| **Contrats** | [contracts/browse.json](contracts/browse.json), [contracts/maintenance.json](contracts/maintenance.json) ; MCP `walter_browse`, `walter_web`, `browser_session` ; CLI `walter-browser`. |

Shared extraction/search engine, session manager and request validation. Hermes is a thin adapter in ports/hermes; MCP calls walter_browse.browse from the same package. No core import from Hermes. The runtime uses its existing isolated Scrapling Python environment, declared as a dependency.

State: WALTER_BROWSE_STATE_DIR (default: the active instance's `state/browse`, from `walter instance path`); shared across harnesses. Search credentials: WALTER_BROWSE_ENV_FILE (default: the instance's `bootstrap/browse-search.env`, mode 0600). Scrapling interpreter: WALTER_SCRAPLING_PYTHON (default `~/.venv/scrapling/bin/python`). Secrets stay server-side. Engines: plain HTTP, static HTML, Scrapling, Camoufox, Chromium (CloakBrowser) and Webtop; extraction must satisfy the same semantic contract on every path.

Compatibility: old skill scripts and universal-scraper wrapper point here. hermes_adapter.py is a legacy diagnostic adapter and is excluded from the runtime-independent import boundary; normal calls do not import it. Existing fallback and extraction behavior is preserved.

Test: python -m pytest runtime/test_*.py tests -q. Set WALTER_BROWSE_STATE_DIR to an isolated test directory. No real account needed.

## Network exits

`network/wg-exit/`: scoped WireGuard exits (container + loopback HTTP proxy) for browser sessions, `walter-wg-exit` on the PATH. See its README.

Since 2026-11-11 the same tool also opens **NordVPN exits per country** (`nordvpn-<cc>`, connectivity from
`/services/nordvpn-proxy`, token through the Walter Secrets grant `nordvpn`, reader `browse`). Browse alone chooses the
route: `walter-browser -s S exit nordvpn-jp`, `walter_browse(exit_country="jp")`, `universal-scraper --network vpn
--country jp`. Never a default, never a fallback: an exit that cannot open (no token, unknown country, tunnel not
protected, tunnel down) is a clear refusal. A NordVPN session gets its own Camoufox process (identity from the exit
IP, fresh fingerprint, no owner cookies — `/session/cookies` answers 409 —, WebRTC proxy-only, no DNS outside the
proxy), stays bound to its exit (a change is refused, even after expiry), and its page reads leave by the same exit.
Owner exits are declared to the browsers (`CAMOFOX_OWNER_EXITS`, `ops/camoufox-max-owner-exits.conf`); Chromium
refuses third-party exits; `network=proxy` and `vpn` without a country are refused.

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

## Sorties réseau par type de trafic (décision du propriétaire, 28/10/2026)

Aucune sortie Browse par l'IP nue du serveur. Trois sorties, chacune fermée par défaut (plus, sur demande explicite seulement, une sortie NordVPN par pays : voir « Network exits ») :

| Trafic | Sortie | Port |
|---|---|---|
| Chromium (CloakBrowser) : profil des démarches lancées en France | IP résidentielle de la sortie France de l'instance (`walter-exit-default` : machine sur son tunnel France ou la sortie WireGuard France, même IP) | `:1083` |
| Camoufox + lectures sans navigateur de `walter_browse` (sonde HTTP, HTML statique, Scrapling) | IP réelle locale du propriétaire (machine **hors** de son tunnel France) ; refus si la machine est sur son tunnel France, endormi ou hors ligne ; budget par site (`[local]` de `network.toml`) | `:1084` (`walter-exit-local`, SOCKS5 + proxy HTTP) |
| Recherche par API authentifiée par clé (Brave) | serveur (pas d'antibot, l'IP du propriétaire reste hors du volume de recherche) | — |

Le facade pose le proxy dans l'environnement du sous-processus de lecture (`_router_env`) et Scrapling le reçoit
explicitement (`WALTER_BROWSE_PROXY`, fixé à la création de sa session). Le repli Webtop (qui sort par le serveur)
est désactivé sauf `WALTER_BROWSE_WEBTOP=on`. Contrôle : `walter-exit-local probe` (JSON, code 1 en cas d'écart) ;
état : `walter-exit-local status`, journal `/var/log/walter-exit-local.log`. Fichiers : `network/exit-local/`,
`ops/walter-exit-local.service`, `ops/camoufox-max-local-exit.conf`, `/etc/walter/browse-identity-camoufox.env`.

## Capacités conversationnelles (2026-11-08)

Une interface web de conversation (chat) utilisée comme un service : un message entre, la réponse de ce message sort.
La recette est une capacité ordinaire du registre (`ProfileIndex`, `implementation.kind = "conversation"`) : page de
départ, moteur, site de connexion éventuel (`browser_sites`), sélecteurs structurels de la saisie, des tours
utilisateur, des réponses, de l'indicateur « en cours » et du signal d'erreur ; versionnée, notée (confiance),
réparée par `bump_capability_version`. Code : `runtime/conversation.py` (stdlib), client public in-process
`walter_browse.converse` / `cancel_conversation` / `close_conversation` ; `CapabilityEngine.execute` aiguille aussi
une capacité conversationnelle vers lui.

Chemin d'une recette validée, sans LLM ni processus (hors presse-papiers) : verrou de la conversation → idempotence
par `request_id` (une réponse déjà obtenue est rendue telle quelle ; après un envoi, une relance reprend l'attente
sans renvoyer) → onglet réutilisé (vérification 2 ms ; recréé à l'URL de la conversation si la session du moteur a
expiré, avec la connexion du site) → collage clavier réel Ctrl+V sous verrou du presse-papiers (contenu précédent
restauré ; secours : frappe clavier rapide, jamais au rythme humain) → `MutationObserver` armé avant l'envoi → envoi
→ attente événementielle (fin = indicateur « en cours » disparu puis 150 ms sans mutation ; sans indicateur connu,
2 s de calme) → réponse = premier tour du service qui suit l'écho exact du message. Sans recette, ou si elle ne
correspond plus, la même observation apprend les sélecteurs (découverte → v1, réparation → version suivante).
État des conversations : `state/browse/conversations/` (0600 ; URL de conversation, onglet, 20 dernières requêtes ;
aucun cookie). Délai, annulation (clic sur l'élément « en cours »), réponse incomplète, erreur du service : statuts
`done | incomplete | cancelled | error | failed`, jamais de renvoi sous le même `request_id`.

Le routage (quel service, quelle recette, quelle session) appartient au Walter Router : passerelle walter-llm
`POST /v1/web/converse` (table `web_services`), commande Telegram `/gpt` du plugin Router. Tests réels :
`tests/test_conversation_live.py` (Camoufox réel, interface de chat locale `tests/fixtures/chat_fixture.py` à
génération progressive) — ils valident le mécanisme, pas un service externe. ChatGPT : recette apprise et rejouée sur le
vrai site (activé par le propriétaire malgré l'interdiction d'extraction des conditions d'OpenAI, DECISIONS 2026-11-08).
L'écho est toujours un élément apparu après l'armement, jamais un comptage : les interfaces démontent les anciens tours.
La réponse rendue est ce qui reste affiché à la fin : tous les éléments réponse visibles entre l'écho et le tour
utilisateur suivant (un tour avec outil de ChatGPT affiche d'abord un message d'étape, replié une fois la réponse écrite
dans un second élément).

Contrôles facultatifs déclarés dans la recette (une recette sans eux reste valide ; chaque champ est conservé par la
découverte et la réparation) :
- `model` = `{open, option, effort, effort_attr}` : choix du modèle et du niveau de réflexion. **Facultatif à l'appel** :
  sans `model=`, rien n'est cliqué et le modèle déjà sélectionné dans le service est utilisé. Avec `model="<mots>"`,
  les mots trouvés dans le nom d'une option choisissent le modèle, le reste nomme le niveau (atteint par de vraies
  flèches clavier sur le curseur `effort`, confirmé quand valeur ET libellé ont changé). Nom inconnu ou ambigu :
  erreur listant les modèles et niveaux, niveau de départ remis en place, aucun message envoyé. Le choix persiste
  dans le compte du service.
- `attach` : champ fichier général de la page (jamais une entrée caméra). `files=[chemins]` : octets transmis par
  tranches base64 de 3 Mo (limite 50 Mo par fichier), posés par `DataTransfer` après le collage du texte ; envoi
  quand les boutons désactivés et barres de progression nouvelles ont disparu. Le temps de téléversement du service
  compte comme externe (`upload_ms`).
- `download` : contrôle de téléchargement d'un fichier produit. La page télécharge elle-même (son propre
  `a.click` / `window.open` / `URL.createObjectURL` interceptés le temps de l'appel) ; les images produites (≥ 128 px)
  sont lues directement. Résultat `files = [{name, mime, size, path, kind}]`, écrits en 0600 sous
  `state/browse/conversations/files/<conversation>/<request_id>/`, purgés après 7 jours ; une réponse faite d'une
  image seule est une réponse valide. Le temps où la page attend que le service livre un fichier (`download_ms`) compte
  comme externe. Limite : sur ChatGPT ce contrôle n'a pas d'attribut stable, la recette retient
  son libellé `aria-label` dans la langue de l'empreinte (thaï) ; si elle change, déclarer le nouveau libellé.

