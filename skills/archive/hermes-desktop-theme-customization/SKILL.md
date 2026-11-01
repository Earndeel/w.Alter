---
name: hermes-desktop-theme-customization
description: Customize the Hermes v2 desktop app (Electron) theme — understand the dual-theme architecture, inject custom themes via localStorage without rebuilding, and avoid the common pitfall of editing source code expecting it to affect a running binary.
tags: [hermes, desktop, electron, theme, customization, localStorage]
---

# Hermes Desktop Theme Customization

## Architecture — Two Separate Theme Systems

Hermes has **two completely independent theme systems** with zero bridge between them:

| System | Location | Applies to | Persistence |
|--------|----------|------------|-------------|
| **Dashboard themes** | `~/.hermes/dashboard-themes/*.yaml` → `web_server.py` API | Web dashboard (browser) | YAML files, picked up at API request time |
| **Desktop themes** | `apps/desktop/src/themes/presets.ts` (built-in) + `localStorage` key `hermes-desktop-user-themes-v1` (user-installed) | Hermes v2 desktop app (Electron) | Built-ins require rebuild; user themes persist in localStorage |

**Critical pitfall**: Editing `apps/desktop/src/themes/presets.ts` on the server does NOT affect a running Hermes desktop app on a Mac. The desktop app is a compiled Electron binary — source changes only take effect after a full rebuild. The user will restart the app, see no change, and be confused.

## The localStorage Injection Path (No Rebuild Required)

Desktop user themes are stored in `localStorage` under the key `hermes-desktop-user-themes-v1`. This is the **only runtime-modifiable path** — no rebuild, no server-side change needed.

### Step 1: Open DevTools in the Hermes Desktop App

Press `Cmd+Opt+I` or `View → Toggle Developer Tools`.

### Step 2: Inject the theme

Paste this into the Console tab:

```js
localStorage.setItem('hermes-desktop-user-themes-v1', JSON.stringify({
  "theme-name": {
    name: 'theme-name',
    label: 'Display Label',
    description: 'Short description shown in settings',
    colors: {
      background: '#000000',    // main app background
      foreground: '#e8e0d5',    // primary text
      card: '#0d0d0d',          // card/panel surfaces
      cardForeground: '#e8e0d5',
      muted: '#1a1a1a',
      mutedForeground: '#8a8075',
      popover: '#0f0f0f',
      popoverForeground: '#e8e0d5',
      primary: '#e8e0d5',
      primaryForeground: '#000000',
      secondary: '#1c1c1c',
      secondaryForeground: '#c8bda8',
      accent: '#1a1a15',
      accentForeground: '#d8ccb0',
      border: '#2a2a20',
      input: '#2a2a20',
      ring: '#c8aa6e',
      midground: '#c8aa6e',
      destructive: '#b94a3a',
      destructiveForeground: '#fef2f2',
      sidebarBackground: '#000000',
      sidebarBorder: '#1a1a10',
      userBubble: '#1a1a10',
      userBubbleBorder: '#3a3020'
    }
  }
}))
```

### Step 3: Restart the app

The new theme appears in **Settings → Appearance**.

### Step 4 (if the theme name collides with a built-in)

The `user-themes.ts` module skips user themes whose `name` matches a built-in. Use a **unique name** not present in `BUILTIN_THEMES` (currently: `nous`, `midnight`, `ember`, `mono`, `cyberpunk`, `slate`).

## Relevant Source Files

| File | Role |
|------|------|
| `apps/desktop/src/themes/presets.ts` | Built-in desktop themes (requires rebuild to change) |
| `apps/desktop/src/themes/context.tsx` | Theme context — merges built-in + localStorage user themes |
| `apps/desktop/src/themes/user-themes.ts` | Reads/writes `hermes-desktop-user-themes-v1` localStorage key |
| `apps/desktop/src/themes/types.ts` | `DesktopTheme` TypeScript type |
| `apps/desktop/src/themes/vscode.ts` | VS Code theme import/conversion |
| `hermes_cli/web_server.py` | Dashboard theme API (`_BUILTIN_DASHBOARD_THEMES`, `_discover_user_themes`) |
| `~/.hermes/dashboard-themes/*.yaml` | User dashboard themes (YAML, served by API, does NOT affect desktop app) |
| `web/src/themes/` | Web dashboard theme frontend code |

## Unattended Remote Installation (SSH + Electron CDP)

When Hermes Desktop is on a remote Mac and no one is present to paste into DevTools, use Electron's Chrome DevTools Protocol (CDP) rather than editing LevelDB directly:

1. Read the current theme schema from the installed app/source before composing the palette; optional fields such as `midground`, `composerRing`, and terminal ANSI colors improve consistency.
2. Quit the app gracefully with AppleScript, relaunch it temporarily with `--remote-debugging-port=<port> --remote-allow-origins=*`, and expose that localhost-only port through a temporary SSH local forward.
3. Connect to `/json/list`, evaluate JavaScript in the renderer, and **merge** the new object into `hermes-desktop-user-themes-v1` instead of replacing the record.
4. Back up the relevant appearance keys before writing. Read the active profile from `hermes-desktop-active-profile-v1` (fallback `default`), then respect the app's scope:
   - for `default`, write `hermes-desktop-theme-v2` and `hermes-desktop-mode-v1`;
   - for a named profile, merge into `hermes-desktop-profile-themes-v1` and `hermes-desktop-profile-modes-v1`;
   - only change the legacy global keys for a named profile when the user explicitly wants to change the fallback inherited by every unassigned profile.
5. Reload the renderer, then verify `document.documentElement.dataset.hermesTheme`, `dataset.hermesMode`, and computed CSS variables such as `--theme-background-seed`, `--theme-primary`, and `--dt-composer-ring`.
6. Capture the actual Electron renderer with CDP `Page.captureScreenshot` for visual QA. A generic macOS screen-capture bridge can show the wrong Space/window even when the renderer is correct.
7. Close the temporary tunnel and relaunch Hermes normally, without the debugging flag.

See `references/remote-cdp-theme-injection.md` for the persistence keys, validation contract, rollback shape, and QA checklist.

## Runtime polish beyond palette tokens

A desktop palette does not control every visual layer. Before reaching for CSS, inspect whether the app already persists the feature separately; for example, the faint conversation statue/backdrop is governed by `hermes.desktop.backdrop.v1`, not by the theme background color. Use the native preference first.

When one component still needs theme-specific polish in a compiled binary, a user theme can persist a narrowly scoped stylesheet through `typography.fontUrl` using a percent-encoded `data:text/css` URL. This is an escape hatch, not the default: back up the theme record, scope selectors to stable semantic attributes, verify the stylesheet loaded and computed styles changed, then relaunch without CDP flags.

See `references/runtime-polish-beyond-palette.md` for the backdrop key, status-bar token split, persistent CSS technique, and verification recipe. When the user requires a literal rendered color rather than merely a dark-looking seed, run `scripts/verify-exact-theme-surfaces.js` in DevTools or through CDP and require `exactBlackPass: true`.

## Common Pitfalls

1. **"I edited the YAML/presets.ts and restarted — nothing changed."** → The desktop app is a compiled binary. Use the localStorage injection path.
2. **"My theme doesn't appear in Settings."** → Check that the theme `name` doesn't collide with a built-in. Built-ins win over same-named user themes.
3. **"I want to change the dashboard (browser) theme."** → Edit `~/.hermes/dashboard-themes/<name>.yaml` and use `customCSS` for aggressive overrides. The dashboard picks it up via API — no rebuild.
