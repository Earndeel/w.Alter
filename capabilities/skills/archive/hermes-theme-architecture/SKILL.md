---
name: hermes-theme-architecture
description: >
  Two separate theme systems in Hermes v2 — dashboard (web, YAML files)
  vs desktop (Electron, localStorage). How each works, how to add themes,
  and critical pitfalls around BUILD vs YAML vs localStorage injection.
---

# Hermes Theme Architecture

## The Two Systems

Hermes v2 has **two completely separate** theme systems with zero overlap:

| | **Dashboard** (web app) | **Desktop** (Electron app) |
|---|---|---|
| Storage | `~/.hermes/dashboard-themes/*.yaml` | `localStorage` key `hermes-desktop-user-themes-v1` |
| Built-in defs | `hermes_cli/web_server.py` `_BUILTIN_DASHBOARD_THEMES` | `apps/desktop/src/themes/presets.ts` `BUILTIN_THEMES` |
| API | `/api/dashboard/themes` → normalized palette | N/A — client-side only |
| Add without rebuild | ✅ write YAML → auto-discovered | ✅ localStorage injection |
| Add in source | `_BUILTIN_DASHBOARD_THEMES` dict | `presets.ts` → requires Electron binary rebuild |

## Desktop Theme System (Electron)

### Storage keys

```
hermes-desktop-theme-v2        → current skin (active theme name)
hermes-desktop-user-themes-v1  → user-installed themes (JSON, persisted)
hermes-desktop-profile-themes-v1 → per-profile skin preferences
```

### Shape of a DesktopTheme

```ts
interface DesktopTheme {
  name: string        // machine key (e.g., 'walter')
  label: string       // display name in UI (e.g., 'W.Alter')
  description: string
  colors: {
    background, foreground, card, cardForeground,
    muted, mutedForeground, popover, popoverForeground,
    primary, primaryForeground, secondary, secondaryForeground,
    accent, accentForeground, border, input, ring, midground,
    destructive, destructiveForeground,
    sidebarBackground, sidebarBorder,
    userBubble, userBubbleBorder
  }
}
```

### Ways to add a theme to desktop

1. **localStorage injection** (no rebuild, immediate):
   ```js
   localStorage.setItem('hermes-desktop-user-themes-v1', JSON.stringify({
     walter: { /* DesktopTheme shape */ }
   }))
   ```
   Restart the app. Theme appears in Settings → Appearance.

2. **Built-in** (requires full Electron rebuild from source):
   Add to `BUILTIN_THEMES` in `apps/desktop/src/themes/presets.ts`, then rebuild the binary.

3. **VS Code marketplace import**:
   Install via Command Center → imports a `.vsix` theme, converted to DesktopTheme palette.

### Critical pitfall: BUILTIN_THEMES override

If a theme with the same `name` exists in both BUILTIN_THEMES and user themes,
the built-in wins (see `user-themes.ts:64`). Rename user themes to avoid collision.

### Source code on server is separate from running app

The desktop app is a **compiled Electron binary**. Editing `presets.ts` on the
server does NOT change the running app's behavior. Two paths to deliver changes
to the user:
- localStorage injection via DevTools Console (always works, no toolchain needed)
- Full rebuild from source (requires Electron toolchain and source checkout)

## Dashboard Theme System (Web)

### Format (`~/.hermes/dashboard-themes/<name>.yaml`)

```yaml
name: theme-name
label: Display Name
description: Short description
palette:
  background: "#000000"
  # ... other colors
customCSS: |    # optional, injected directly
  html, body, #root, .app-container {
    background-color: #000000 !important;
  }
```

### Adding

Write YAML → auto-discovered by `_discover_user_themes()` in `web_server.py`.
Served via `/api/dashboard/themes`. No rebuild needed.

## Pitfalls

- **`dashboard-themes/walter.yaml` has no effect on the desktop app.** The desktop
  uses localStorage, not YAML file discovery. Two independent systems.
- **Editing `presets.ts` on the server does not change a compiled desktop binary.**
  The user's running app is a pre-built Electron binary, not reading source files
  from the repo.
- **When a user asks to add a theme to "the app" or "Hermes v2", clarify which
  app:** the web dashboard or the Electron desktop — they use different mechanisms.

## Reference Files

- `references/localstorage-injection.js` — ready-to-paste localStorage snippet for desktop themes
- `references/dashboard-theme-template.yaml` — YAML template for dashboard themes
