# Walter Browse

Shared extraction/search engine, session manager and request validation. Hermes is a thin adapter in ports/hermes; MCP calls walter_browse.browse from the same package. No core import from Hermes. The runtime uses its existing isolated Scrapling Python environment, declared as a dependency.

State: WALTER_BROWSE_STATE_DIR (default: the active instance's `state/browse`, from `walter instance path`); shared across harnesses. Search credentials: WALTER_BROWSE_ENV_FILE (default: the instance's `bootstrap/browse-search.env`, mode 0600). Scrapling interpreter: WALTER_SCRAPLING_PYTHON (default `~/.venv/scrapling/bin/python`). Secrets stay server-side. Engines: plain HTTP, static HTML, Scrapling, Camoufox and Webtop; extraction must satisfy the same semantic contract on every path.

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

Une session sans route propre sort par la machine du propriétaire (`walter-exit-mac` : tunnel SOCKS
`127.0.0.1:1082` par `ssh mac`) et se présente avec son système, son fuseau et ses langues (`/etc/walter/browse-identity.env`,
valeurs de l'instance : `config/browse/network.toml [default]`) ; WebRTC est fermé (le tunnel ne le transporte pas).
Si la sortie est injoignable, la session s'ouvre sans les cookies du propriétaire, depuis l'IP du serveur. Une session
peut toujours choisir une autre sortie (`walter-browser exit`). Fichiers : `ops/walter-exit-mac.service`,
`ops/camoufox-max-identity.conf`.

