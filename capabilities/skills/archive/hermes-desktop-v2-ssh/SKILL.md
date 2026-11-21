---
name: hermes-desktop-v2-ssh
description: Hermes Desktop V2 — App Electron officielle (Mac x64) lancée en mode remote via tunnel SSH vers le VPS hermes.
---

# Hermes Desktop V2 — Architecture SSH Remote

## Principe

L'app Electron officielle (NousResearch/hermes-agent) supporte le mode **remote** natif via les variables d'environnement `HERMES_DESKTOP_REMOTE_URL` et `HERMES_DESKTOP_REMOTE_TOKEN`.

Au lieu de lancer `hermes serve` localement (problématique sur Mac Intel), on forwarde le dashboard qui tourne déjà sur le VPS via un tunnel SSH.

```
┌──────────────────────────────┐      SSH Tunnel       ┌─────────────────────┐
│  Mac Intel (Hermes V2.app)   │ ◄──────────────────► │  VPS Oracle          │
│                              │   localhost:9119      │  hermes dashboard    │
│  HERMES_DESKTOP_REMOTE_URL   │       →               │  127.0.0.1:8787      │
│  = http://127.0.0.1:9119     │                       │  auth_required:false │
└──────────────────────────────┘                       └─────────────────────┘
```

## Artefacts

| Fichier | Emplacement | Rôle |
|---------|-------------|------|
| `Hermes V2.app` | `/Applications/Hermes V2.app` | App Electron x64 (build officiel) |
| `hermes-v2` | `/usr/local/bin/hermes-v2` | Launcher (tunnel SSH + lancement) |
| DMG | `/tmp/hermes-agent/apps/desktop/release/Hermes-0.17.0-mac-x64.dmg` | Archive de distribution |

## Build

```bash
# Sur le Mac :
cd /tmp/hermes-agent/apps/desktop
npm install
npm run dist:mac    # Produit release/Hermes-0.17.0-mac-x64.dmg + release/mac/Hermes.app
```

## Installation V2

```bash
# 1. Copier l'app (ne pas écraser la V1 !)
cp -a /tmp/hermes-agent/apps/desktop/release/mac/Hermes.app "/Applications/Hermes V2.app"

# 2. Installer le launcher
cp hermes-v2-launcher.sh /usr/local/bin/hermes-v2
chmod +x /usr/local/bin/hermes-v2
```

## Utilisation

```bash
# Lancer depuis le terminal :
hermes-v2

# Ou double-cliquer sur le script dans Finder
```

Le launcher :
1. Tue tout tunnel SSH précédent sur le port 9119
2. Établit un tunnel SSH : `-L 9119:127.0.0.1:8787 walter-ts`
3. Attend que le dashboard réponde (max 20s)
4. Lance l'app Electron avec `HERMES_DESKTOP_REMOTE_URL=http://127.0.0.1:9119`

## Prérequis

- SSH configuré sur le Mac avec l'alias `walter-ts` (voir `~/.ssh/config`)
- Tailscale actif (le VPS est accessible via `100.91.35.121`)
- Le dashboard hermes doit tourner sur le VPS (`hermes dashboard`)

## Fermeture

```bash
# Fermer le tunnel SSH
kill $(cat /tmp/hermes-v2-tunnel.lock)
# Ou
ssh -S /tmp/hermes-v2-ssh-ctrl -O exit walter-ts
```

## Notes

- **Pas de token** : le dashboard est configuré avec `auth_required: false`
- **Pas de code signing** : build sans certificat Apple (avertissement au premier lancement → clic droit → Ouvrir)
- **Pas de notarization** : nécessiterait `APPLE_API_KEY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER`
- **Coexistence V1/V2** : la V1 (`/Applications/HermesDesktop.app`) n'est pas touchée
- **Port local** : 9119 (libre, pas de conflit avec la V1)
