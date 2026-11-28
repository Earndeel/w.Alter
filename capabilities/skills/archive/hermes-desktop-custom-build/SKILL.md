---
name: hermes-desktop-custom-build
description: "Build and adapt the official Hermes Desktop Electron app for custom deployments — Intel Mac, VPS-only backends (SSH tunnel instead of local hermes serve), and non-standard architectures."
version: 1.0.0
author: walter
metadata:
  hermes:
    tags: [hermes-desktop, electron, mac, intel, vps, ssh, build]
---

# Hermes Desktop Custom Build

Build and adapt the official Nous Research Hermes Desktop app (Electron + React) for environments the pre-built binaries don't cover: Intel Mac, VPS-only backends, custom connection methods.

## When to use

- Building the desktop app for **Intel Mac** (official builds are Apple Silicon only)
- Adapting the app for a **remote/VPS backend** (app normally expects local `hermes serve`)
- Custom connection methods (SSH tunnel instead of local process spawn)

## Architecture

L'app officielle (`apps/desktop` dans `hermes-agent`) :

```
Electron (main.cjs, ~7600 lignes)
  ├── resolveHermesBackend() → choisit comment lancer hermes
  │   ├── Bootstrap managed install (prioritaire)
  │   ├── hermes on PATH (fallback)
  │   └── System Python + hermes_cli (dernier recours)
  ├── spawn: hermes serve --host 127.0.0.1 --port 0
  ├── waitForDashboardPortAnnouncement() → lit le port du dashboard
  └── BrowserWindow → http://127.0.0.1:<port>
```

Fichiers clés du backend resolver :

| Fichier | Rôle |
|---|---|
| `electron/backend-command.cjs` | Construit l'argv `hermes serve --host 127.0.0.1 --port 0` |
| `electron/backend-probes.cjs` | Vérifie si un binaire hermes fonctionne (`--version`, import probe) |
| `electron/backend-env.cjs` | Construit PATH et PYTHONPATH pour le process hermes |
| `electron/backend-ready.cjs` | Attend l'annonce du port dashboard |
| `electron/dashboard-token.cjs` | Récupère le token d'accès dashboard |
| `electron/bootstrap-runner.cjs` | Lance le bootstrap managed install si nécessaire |

## Build pour Intel Mac

```bash
cd hermes-agent/apps/desktop
npm install
npm run dist:mac    # produit Hermes-0.17.0-darwin-x64.dmg dans release/
```

**Prérequis** : Xcode CLT, Node ≥20, npm ≥10. Le build produit automatiquement les binaires pour l'arch de la machine hôte.

## Stratégie d'adaptation VPS (backend distant)

L'app Electron supporte **nativement** le mode remote via deux variables d'environnement.
**Aucune modification du code source n'est nécessaire.**

### Mécanisme officiel (env vars)

```
HERMES_DESKTOP_REMOTE_URL=http://127.0.0.1:9119
HERMES_DESKTOP_REMOTE_TOKEN=<any-value>
```

Dans `main.cjs`, `resolveRemoteBackend()` (ligne 4945) vérifie ces variables avant de tomber en mode local. Si les deux sont présentes → l'app se connecte au dashboard distant. Sinon → fallback local (`resolveHermesBackend` → spawn `hermes serve`). Voir `references/remote-backend-code-analysis.md` pour le détail du flux.

Ordre de résolution dans `resolveRemoteBackend()` :
1. Override par profil (connection.json `profiles[name]`)
2. **Env override** (`HERMES_DESKTOP_REMOTE_URL` + `HERMES_DESKTOP_REMOTE_TOKEN`)
3. Global remote (connection.json `mode: "remote"`)

### Approche tunnel SSH

Le launcher complet est dans `scripts/hermes-v2-launcher.sh`. Principe :

```bash
# 1. Établir le tunnel (le dashboard tourne sur le VPS:8787)
ssh -f -N -M -S /tmp/hermes-ssh-ctrl \
    -L 9119:127.0.0.1:8787 \
    walter-ts

# 2. Attendre que le dashboard réponde
curl -s http://127.0.0.1:9119/api/status

# 3. Lancer l'app Electron avec les env vars
#    ⚠️ JAMAIS `open` (voir pitfalls)
exec env \
  HERMES_DESKTOP_REMOTE_URL=http://127.0.0.1:9119 \
  HERMES_DESKTOP_REMOTE_TOKEN="no-auth" \
  "/Applications/Hermes V2.app/Contents/MacOS/Hermes"
```

### Config SSH attendue

```
Host walter-ts
    HostName <vps-tailscale-ip>
    Port 22
    User root
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 10
```

## Référence : setup W.Alter (Lucas)

- **Mac** : Intel i9-9880H, macOS 15.7.7, Node v24.3 à `/usr/local/bin/node`
- **V1 existante** : `HermesDesktop.app` (Swift, universal binary, v0.9.0, bundle `com.hermesdesktop.app`)
- **Installer officiel** : `Hermes.app` (Hermes-Setup v0.0.1, `com.nousresearch.hermes.setup` — pas l'app desktop)
- **Configuration SSH** : `connections.json` → `sshAlias: walter-ts`, `sshUser: root`

## Pitfalls

- **Node PATH en SSH** : `/usr/local/bin/node` existe mais n'est pas dans le PATH par défaut des sessions SSH macOS. Toujours utiliser le chemin absolu ou `export PATH="/usr/local/bin:$PATH"` avant les commandes npm/node.
- **Build Intel** : doit être fait sur une machine Intel — electron-builder compile les modules natifs (node-pty) pour l'arch hôte. Pas de cross-build Linux→Mac fiable.
- **Hermes.app vs HermesDesktop.app** : ce sont deux apps différentes. `Hermes.app` (bundle `com.nousresearch.hermes.setup`) est l'**installer** — il télécharge et configure hermes. `HermesDesktop.app` est l'app bureau elle-même. Ne pas confondre.
- **`hermes serve` vs `hermes dashboard`** : `serve` est le nom moderne, `dashboard --no-open` est le fallback legacy. Le backend-command.cjs gère les deux automatiquement.
- **`open` sur macOS ne passe PAS les variables d'environnement** : `open` utilise LaunchServices qui lance l'app avec l'environnement de `launchd` (vierge), ignorant les `export` du shell. TOUJOURS lancer le binaire directement : `exec env VAR=val "$APP/Contents/MacOS/Hermes"`. Utiliser `open` fait croire que l'app fonctionne mais elle tombe en mode local (bootstrap/install) sans les env vars remote.
  - **Alternative hybride** : écrire `connection.json` avec `mode: "remote"` avant de lancer via `open`. Le launcher `scripts/hermes-v2-launcher.sh` utilise cette approche pour éviter les problèmes de SingletonLock avec `exec`.
- **Les DEUX variables sont obligatoires** : même si le dashboard est configuré avec `auth_required: false`, l'Electron exige `HERMES_DESKTOP_REMOTE_TOKEN` (valeur quelconque, ex: `"no-auth"`). Si seul `REMOTE_URL` est défini, `resolveRemoteBackend()` throw `"HERMES_DESKTOP_REMOTE_URL is set but HERMES_DESKTOP_REMOTE_TOKEN is not"` (ligne 4961-4965 de main.cjs).
- **Token arbitraire = 401 silencieux après `/api/status`** : `waitForHermes()` appelle `/api/status` qui est public (200 même avec un faux token), donc le check passe. Mais tous les appels API suivants échouent en 401 car le gateway exige un vrai token de session. Symptôme : l'app affiche "Could not connect to Hermes gateway" alors que le dashboard répond. Le vrai token est dans `window.__HERMES_SESSION_TOKEN__` du HTML du dashboard. Voir `references/remote-backend-code-analysis.md` pour le détail.
