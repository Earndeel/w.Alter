# Official Hermes Desktop — Architecture Reference

> Condensed from exploring `apps/desktop` in `NousResearch/hermes-agent` (July 2026, v0.17.0).

## Stack

- **Runtime** : Electron 40.10.2
- **Renderer** : React 19 + Vite 8 + Tailwind 4
- **State** : nanostores + @tanstack/react-query
- **Editor** : CodeMirror 6 + xterm.js 6
- **UI primitives** : Radix UI + @nous-research/ui + motion (framer-motion fork)
- **Markdown** : streamdown + shiki + katex + mermaid
- **Build** : electron-builder 26, TypeScript 6
- **Node** : ≥20.19 || ≥22.12

## Directory map

```
apps/desktop/
  electron/         # Main process (CJS — ~30 files)
    main.cjs         # Entry point (~7600 LOC), resolveHermesBackend, window mgmt
    backend-*.cjs    # Backend discovery, spawn, probes, env, readiness
    bootstrap-*.cjs  # Managed install / first-run bootstrapping
    session-*.cjs    # Multi-window session management
    gateway-*.cjs    # WebSocket probe for dashboard
    dashboard-token.cjs  # Token handshake
    hardening.cjs    # Security hardening
    update-*.cjs     # Auto-update machinery
  src/              # Renderer process (React/TSX)
    store/           # nanostores (~60 stores)
    lib/             # Utilities, hooks, keybinds
    themes/          # Theme engine (VS Code + custom presets)
    components/      # UI components
  scripts/          # Build scripts (before-build, after-pack, notarize, etc.)
  assets/           # Icons, installer images
  package.json      # electron-builder config embedded
```

## Backend resolution ladder

`resolveHermesBackend()` in `main.cjs` walks this ladder (first success wins) :

1. `HERMES_DESKTOP_HERMES_ROOT` env var → managed install path
2. Bootstrap-completed marker (`build/install-stamp.json`)
3. `hermes` on PATH (verified via `verifyHermesCli()` → `hermes --version`)
4. System Python + `hermes_cli` installed (verified via `canImportHermesCli()`)
5. Sentinel: needs bootstrap → launches first-run installer

## Backend spawn

Once resolved, the app runs :

```
hermes serve --host 127.0.0.1 --port 0
```

`--port 0` lets the OS pick a free port. The port is communicated back via stdout announcement, read by `waitForDashboardPortAnnouncement()`.

If the resolved runtime predates `serve`, `dashboardFallbackArgs()` rewrites to :

```
hermes dashboard --no-open --host 127.0.0.1 --port 0
```

## Dashboard token

The dashboard writes a token file at `~/.hermes/dashboard.token`. `adoptServedDashboardToken()` in `dashboard-token.cjs` reads it and injects it as a cookie into the Electron session before navigating to the dashboard URL.

## Electron security

- `hardenedRuntime: true` on macOS (notarization required)
- `sandbox: true` for renderer (configured in `electron/hardening.cjs`)
- ASAR packaging with `node_modules/**/*.node` unpacked
- Custom protocol handler: `hermes://` → deep links

## macOS specifics

- `electron/entitlements.mac.plist` — hardened runtime entitlements
- `electron/entitlements.mac.inherit.plist` — child process entitlements
- `scripts/notarize.cjs` — Apple notarization (requires Developer ID)
- Gatekeeper assessment disabled (`gatekeeperAssess: false`)
- DMG + ZIP targets

## W.Alter V1 vs Official comparison

| Aspect | V1 (HermesDesktop.app) | Official (Hermes.app bundle) |
|---|---|---|
| **Runtime** | Swift native | Electron |
| **Backend** | SSH tunnel → VPS | Local `hermes serve` |
| **Config** | `connections.json` (SSH alias + user) | Managed install or PATH probe |
| **Version** | 0.9.0 | 0.17.0 |
| **Bundle ID** | `com.hermesdesktop.app` | `com.nousresearch.hermes` |
| **Arch** | Universal (x86_64 + arm64) | Apple Silicon only (pre-built) |
| **UI** | Native WebView | React + Tailwind (rich) |
