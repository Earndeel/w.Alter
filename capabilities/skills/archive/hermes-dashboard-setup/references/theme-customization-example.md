# Dashboard Theme Customization — W.Alter Example

## W.Alter Theme (Deep Black + Cyan)

Ported from the TUI `walter-blue` skin (`~/.hermes/skins/walter-blue.yaml`).

```typescript
// web/src/themes/presets.ts
export const walterTheme: DashboardTheme = {
  name: "walter",
  label: "W.Alter",
  description: "Deep navy black with electric cyan — the butler look",
  palette: {
    background: { hex: "#000000", alpha: 1 },
    midground: { hex: "#03DFE8", alpha: 1 },
    foreground: { hex: "#D0FBFE", alpha: 0 },
    warmGlow: "rgba(0, 0, 0, 0)",    // no tint overlay
    noiseOpacity: 0,                   // no grain texture
  },
  typography: {
    ...DEFAULT_TYPOGRAPHY,
    fontSans: `"Inter", "JetBrains Mono", ${SYSTEM_SANS}`,
    fontMono: `"JetBrains Mono", "SF Mono", ${SYSTEM_MONO}`,
    fontUrl: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap",
    baseSize: "14px",
    letterSpacing: "-0.005em",
  },
  layout: { ...DEFAULT_LAYOUT, radius: "0.375rem" },
  terminalBackground: "#0a0a2e",
  colorOverrides: {
    primary: "#03DFE8",
    accent: "#03DFE8",
    muted: "#029BA8",
    border: "#029BA8",
    card: "#0a0a2e",
    destructive: "#ef5350",
    success: "#4caf50",
    warning: "#ffa726",
  },
  swatchColors: ["#000000", "#03DFE8", "#D0FBFE"],
};
```

## TUI Skin Colors (walter-blue.yaml)

```yaml
colors:
  banner_border: "#03DFE8"
  banner_title: "#03DFE8"
  banner_accent: "#03DFE8"
  banner_dim: "#029BA8"
  banner_text: "#D0FBFE"
  ui_accent: "#03DFE8"
  ui_label: "#6DD8E0"
  status_bar_bg: "#0a0a2e"
  completion_menu_bg: "#0a0a2e"
  completion_menu_current_bg: "#1a2a66"
```

## Lessons Learned

- Initial attempt used `#060612` as background — still appeared slightly bluish due to `warmGlow` cyan tint
- Setting `warmGlow: "rgba(0,0,0,0)"` + `noiseOpacity: 0` + `background: "#000000"` gives a pure flat black
- The CSS derives `--color-card`, `--color-muted`, `--color-border` from `midground` via `color-mix()` — a bright midground will tint derived surfaces
