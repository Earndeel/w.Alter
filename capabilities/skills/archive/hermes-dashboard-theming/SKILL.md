---
name: hermes-dashboard-theming
description: Create and debug custom dashboard themes for Hermes. Covers the YAML schema, palette vs customCSS, debugging theme loading, and the user-theme directory.
---

# Hermes Dashboard Theming

Custom dashboard themes live in `~/.hermes/dashboard-themes/`. Each is a YAML file `<name>.yaml`.

## File structure

```yaml
name: my-theme
label: My Theme
description: A custom dashboard theme.
palette:
  background: "#000000"
  midground: "#e8e0d5"
  foreground: "#ffffff"
  warmGlow: "rgba(200, 170, 110, 0.25)"
```

The active theme is selected by the `dashboard.theme` key in `config.yaml`.

## Palette keys

| Key | Purpose |
|-----|---------|
| `background` | Main background colour (hex or `rgba()`) |
| `midground` | Card/panel backgrounds |
| `foreground` | Primary text colour |
| `warmGlow` | Accent glow (cards, highlights) |

Hex strings are normalised to `{hex, alpha}` objects by `_normalise_theme_definition` in `hermes_cli/web_server.py`. `rgba()` strings pass through as-is.

## When palette alone doesn't work — customCSS

If a palette change doesn't render after restart, the frontend may not be applying it to every element. Add a `customCSS` field with `!important` rules:

```yaml
customCSS: |
  :root, html, body, #root {
    background-color: #000000 !important;
  }
```

The frontend injects this as a `<style>` tag with id `hermes-theme-custom-css` — it fires on every theme change and overrides any other stylesheet.

## Debugging

Verify the API discovers the theme correctly:

```python
import json, sys
sys.path.insert(0, '.')
from hermes_cli.web_server import _discover_user_themes

for t in _discover_user_themes():
    print(f"{t['name']}: bg={t['palette']['background']} customCSS={bool(t.get('customCSS'))}")
```

## Pitfalls

- **Name collision with built-in themes** — user themes sharing a name with any theme in `_BUILTIN_DASHBOARD_THEMES` are skipped silently. Use a unique name.
- **TUI themes are separate** — this covers the web dashboard only. TUI theming is in `ui-tui/src/theme.ts`.
- **Electron/desktop caching** — a hard refresh (Ctrl+Shift+R) or full app quit+relaunch may be needed after changing a theme file.
- **Foreground `alpha: 0.0` on bare hex** — bare hex strings for `foreground` can normalise to fully transparent. If text disappears, use `rgba()` notation instead.
