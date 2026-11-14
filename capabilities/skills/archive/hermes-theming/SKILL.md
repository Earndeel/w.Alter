---
name: hermes-theming
description: Hermes dual theme system — dashboard (YAML/API) vs desktop (TypeScript/Electron). Pitfalls, file locations, and how to add or modify themes for each surface.
---

# Hermes Theming — Dual System Architecture

Hermes has **two separate, non-communicating theme systems**. This is the #1 pitfall
when a user says "change the background color" and it doesn't take effect.

## Surface → System Mapping

| Surface | Theme source | Format | Location |
|---------|-------------|--------|----------|
| **Web dashboard** (`/dashboard`) | `_BUILTIN_DASHBOARD_THEMES` + user YAML files | YAML via Python API | `~/.hermes/dashboard-themes/<name>.yaml` |
| **Desktop app** (Electron, "Hermes v2") | `BUILTIN_THEMES` in TypeScript + VS Code import | TypeScript constants | `apps/desktop/src/themes/presets.ts` |
| **TUI** (`hermes tui`) | `ui-tui/src/theme.ts` | TypeScript | Separate TUI theme structure |

**There is no bridge.** A YAML file in `dashboard-themes/` never reaches the
desktop app. A theme added to `presets.ts` never reaches the web dashboard.

## Desktop Themes (Electron App)

### File: `apps/desktop/src/themes/presets.ts`

Each theme is a `DesktopTheme` object with `name`, `label`, `description`,
`colors` (object with ~20 color keys), and optional `typography`.

Register new themes in the `BUILTIN_THEMES` record at the bottom of the file.

### Rebuild required

Desktop themes are **compiled into the Electron bundle**. After editing
`presets.ts`, rebuild:

```bash
cd apps/desktop && npm run build   # production
cd apps/desktop && npm run dev     # dev with HMR
```

Without a rebuild, the theme won't appear in Settings → Appearance.

### VS Code theme import

The desktop app can also import VS Code themes via localStorage
(see `apps/desktop/src/themes/vscode.ts`). These are loaded at runtime
and don't require a rebuild.

## Dashboard / Web Themes (YAML)

### File: `~/.hermes/dashboard-themes/<name>.yaml`

Schema: `name`, `label`, `description`, `palette` (object with `background`,
`midground`, `foreground`, `warmGlow`), and optional `customCSS` (string
of raw CSS injected into the dashboard).

### Activation

The config key `dashboard.theme` controls which theme is active on the
web dashboard. Changing it + refreshing (F5) applies the new theme.
**No rebuild needed** — the Python backend discovers and serves YAML
files from `~/.hermes/dashboard-themes/` on every API call.

### Backend: `hermes_cli/web_server.py`

- `_BUILTIN_DASHBOARD_THEMES` — hardcoded fallback themes
- `_discover_user_themes()` — scans `~/.hermes/dashboard-themes/` for `*.yaml`
- `_normalise_theme_definition()` — validates and normalises the palette
- API endpoint serves themes to the web frontend

## Checklist: "I changed the background and nothing happened"

1. **Which surface?** Ask the user: desktop Electron app, web dashboard, or TUI?
2. If desktop → edit `apps/desktop/src/themes/presets.ts` → rebuild
3. If web → create/edit `~/.hermes/dashboard-themes/<name>.yaml` → F5
4. If TUI → edit `ui-tui/src/theme.ts`
