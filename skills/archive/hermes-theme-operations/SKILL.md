---
name: hermes-theme-operations
description: Use for Hermes dashboard, desktop, or TUI theme changes.
tags: [hermes, themes, dashboard, desktop, tui]
metadata:
  hermes:
    tags: [hermes, themes, dashboard, desktop, tui]
---

# Hermes Theme Operations

Use this class-level skill for theme changes and diagnosis across Hermes' web dashboard, Electron desktop, and TUI. These are separate renderers and storage systems; identify the surface before editing so a valid change is not applied to the wrong application.

## Surface contracts

- **Web dashboard:** user themes live in `~/.hermes/dashboard-themes/<name>.yaml`; the Python server discovers them through `_discover_user_themes()` and exposes normalized palettes through `/api/dashboard/themes`. A YAML change needs a refresh, not an Electron rebuild.
- **Electron desktop:** built-ins are compiled from `apps/desktop/src/themes/presets.ts`; user themes use `hermes-desktop-user-themes-v1` in localStorage. Source changes require an Electron rebuild, while localStorage injection does not. Built-ins win on name collisions, so choose a unique user key.
- **TUI:** `ui-tui/src/theme.ts` and the Ink/React components define a separate theme/display contract. Dashboard YAML and desktop presets do not affect it.

## Always-on rules

1. Ask which surface is being changed before choosing a file, because Hermes has no theme bridge.
2. Verify the active surface after a change, because editing source on a server does not alter a compiled desktop binary.
3. Give dashboard themes unique names and inspect normalized API output, because collisions can be skipped silently.
4. Add `customCSS` with `!important` only when the palette does not reach the needed selectors, because CSS injection is a fallback rather than a second palette source.
5. Treat transparent foreground normalization as a theme-schema defect, because a loaded theme can still make text disappear.
6. Keep exact examples and surface-specific commands in the routed archives, because a short class-level procedure should not duplicate every historical recipe.

## Verification

For dashboard changes, verify discovery, selected `dashboard.theme`, normalized palette, and rendered CSS. For desktop changes, verify the localStorage or rebuilt preset is present after a full relaunch. For TUI changes, build or run the TUI and inspect the affected role, reasoning, and tool rendering. Never claim cross-surface propagation without checking each renderer.

Exact historical procedures are routed in `references/curator-theme-archive-routes.md`.
