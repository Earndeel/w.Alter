# Example: pure black theme for Web Dashboard

Save as `~/.hermes/dashboard-themes/walter.yaml`, then set
`dashboard.theme: walter` in config and hard-refresh.

```yaml
name: walter
label: W.Alter
description: Fond noir profond — sobre, élégant, efficace.
palette:
  background: "#000000"
  midground: "#e8e0d5"
  foreground: "#ffffff"
  warmGlow: "rgba(200, 170, 110, 0.25)"
customCSS: |
  html, body, #root, .app-shell, [class*="bg-"] {
    background-color: #000000 !important;
  }
```

The `customCSS` block is a belt-and-suspenders fallback in case the
palette's `background` key doesn't propagate to all CSS selectors.
