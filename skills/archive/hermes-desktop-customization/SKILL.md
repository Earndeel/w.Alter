---
name: hermes-desktop-customization
description: Customize the Hermes V2 desktop app on macOS — themes, colors, and UI modifications via direct file edits on unpacked ASAR assets. No CDP / LevelDB / localStorage needed.
---

# Hermes Desktop Customization

Customize the Hermes V2 desktop app (macOS) by directly editing the unpacked ASAR JavaScript bundles. This is the simplest path — skip CDP injection, LevelDB parsing, or localStorage hacks unless direct file editing fails.

## Architecture

Hermes V2 on macOS uses Electron with ASAR packaging:

```
/Applications/Hermes V2.app/Contents/Resources/
├── app.asar              ← Packed ASAR (binary, not directly editable)
├── app.asar.unpacked/    ← Unpacked large files — DIRECTLY EDITABLE
│   └── dist/assets/
│       └── index-<hash>.js                   ← Main JS bundle (~28MB)
│       └── index-<hash>.css                  ← CSS bundle
│       └── ... other assets
├── icon.icns
└── native-deps/
```

**Key insight**: The unpacked JS files can be edited in-place with no code signing issues. No need for ASAR extraction/re-packaging.

## Theme Editing

### Finding the built-in themes

Themes are defined as JavaScript objects in the main bundle. To find them:

```bash
grep -o "cyberpunk[^}]*}" "/Applications/Hermes V2.app/Contents/Resources/app.asar.unpacked/dist/assets/index-*.js" | head -5
```

Each theme is a JS object literal with:
- `name` — internal slug
- `label` — display name
- `description` — shown in settings
- `colors` — object with 20+ color keys (background, foreground, card, primary, secondary, accent, border, ring, sidebar*, userBubble*, destructive*, muted*)

### Editing a theme

1. **Backup first**:
   ```bash
   cp "/Applications/Hermes V2.app/Contents/Resources/app.asar.unpacked/dist/assets/index-<HASH>.js"{,.backup}
   ```

2. **Find the exact theme string** with `grep -o` or Python `find()`.

3. **Replace the colors** using Python string replacement. The theme object is a single long string in the JS — do a direct `str.replace(old, new)`.

4. **Verify uniqueness** — each theme object should appear exactly once.

5. **Restart the app** — kill `Hermes` process, `open -a "Hermes V2"`. No cache invalidation needed.

### Example: Cyberpunk green → electric blue

```python
JS = '/Applications/Hermes V2.app/Contents/Resources/app.asar.unpacked/dist/assets/index-BJsuVyz2.js'

with open(JS, 'r') as f:
    content = f.read()

# Theme colors are in template-literal format: background:`#000a00`
old = "cyberpunk...,colors:{background:`#000a00`,foreground:`#00ff41`,..."
new = "cyberpunk...,colors:{background:`#000a14`,foreground:`#0088ff`,..."

content = content.replace(old, new)
with open(JS, 'w') as f:
    f.write(content)
```

### Adding a custom theme

To add a brand-new theme (like "W.Alter" black theme):
1. Find an existing theme object in the JS
2. Duplicate and modify the full object string
3. Insert it into the themes array/object in the JS
4. Restart the app

## Runtime preferences (LevelDB)

Theme *selection* (which theme is active) is stored in LevelDB:
```
~/Library/Application Support/Hermes/Local Storage/leveldb/
```
Key: `hermes-desktop-theme-v2`, value: theme slug (e.g., `cyberpunk`).

This can be read/written via CDP `localStorage.getItem/setItem` but **don't bother** — just change it in the Settings UI after editing the theme definition.

## Pitfalls

- **Don't use CDP/WebSocket for theme editing** — it's overkill. CDP is for runtime state (which theme is selected, localStorage), not theme definitions.
- **Don't parse LevelDB directly** — theme definitions are in the JS bundle, not in LevelDB. LevelDB only stores the selection key.
- **Don't extract/repackage ASAR** — the relevant files are already unpacked into `app.asar.unpacked/`.
- **App may need `killall Hermes` + reopen** for changes to take effect. The app reads JS at launch.
- **Code signing**: Editing unpacked files does NOT trigger macOS code signing errors. Only the packed `app.asar` is signed.