# Dashboard Themes

## Theme locations

| What | Where |
|------|-------|
| User themes (YAML) | `~/.hermes/dashboard-themes/*.yaml` |
| Built-in presets (web) | `web/src/themes/presets.ts` |
| Built-in presets (desktop) | `apps/desktop/src/themes/presets.ts` |
| Desktop user themes | `apps/desktop/src/themes/user-themes.ts` |
| Theme context / loader | `web/src/themes/context.tsx` |
| ThemeSwitcher UI | `web/src/components/ThemeSwitcher.tsx` |
| Backend normalisation | `hermes_cli/web_server.py` → `_normalise_theme_definition` |

## User theme schema (YAML)

```yaml
name: my-theme
label: My Theme
description: Description montrée dans le sélecteur.
palette:
  background: "#000000"              # fond principal
  midground: "#e8e0d5"               # surfaces secondaires
  foreground: "#ffffff"              # couleur du texte
  warmGlow: "rgba(200,170,110,0.25)" # overlay d'accent
```

Les 4 clés de `palette` sont obligatoires. Valeurs en syntaxe CSS (hex, rgba, etc.).

Le backend découvre automatiquement tous les `*.yaml` dans `~/.hermes/dashboard-themes/`
et les expose via l'API. Pas besoin de redémarrer — le dashboard les charge au prochain F5.

## Activation

La clé `dashboard.theme` dans la config pointe sur le `name` du thème YAML.

## Code

- `_normalise_theme_definition()` dans `hermes_cli/web_server.py` normalise les thèmes YAML.
- L'app desktop applique la même palette via les propriétés CSS `--dt-background`, `--dt-midground`, etc.
- Les presets frontend (`presets.ts`) servent de fallback avant que les thèmes YAML utilisateur soient chargés.
