# dsh-web-ui — Walter's face for the DSH web GUI

A DSH plugin (host + browser halves) that gives the DeepSeek Harness web interface Walter's look, inspired by
Hermes Desktop: the instance's name and mark in the sidebar, a large serif title and a greeting on the blank
session, pure black surfaces (#000000) with neon-blue contrast (#01B7FF), a 2px neon-blue frame around the input
area and the owner's message bubbles, uppercase blue section labels, and a full French interface. Nothing in DSH is patched: every change goes through DSH's public extension
points, so `npm update` of DSH keeps working (check the result after an update; the CSS uses DSH class names).

| File | Role |
|---|---|
| `index.js` | Host half. Reads `locales/fr.json` and `style.css`, publishes `window.__WALTER_UI__` (name, greeting, defaults, French dictionaries), the stylesheet before first paint, and a script that renames the tab and its icon (`webserver/index-inject`). |
| `client.js` | Browser half (hand-written factory bundle, no build). Fills the slots `sidebar.brand.mark`, `sidebar.brand.name`, `conversation.hero.brand.mark`; shadows DeepSeek's `welcome-notice` onboarding step; registers the `fr` language and its dictionaries; stacks the colour layer (`ctx.theme.overrideTokens`); applies the default language/appearance and remembers the browser's own later choices (tailnet pages are not persisted by the Host). |
| `style.css` | Typography and layout touches. Selectors use slot attributes and the semantic part of DSH's hashed class names (`[class*="_headline"]`…). |
| `locales/fr.json` | French dictionaries per DSH namespace (2 100+ keys, machine-translated through walter-llm then reviewed). `%BRAND%` = the configured name. A missing key falls back to English. |

## Mounting (instance side)

In the DSH profile patch (`$DSH_HOME/profiles/web/cordis.patch.yml`), outside Walter's managed block:

```yaml
- insert:
    - id: walter-ui
      name: <walter root>/core/ports/dsh-web-ui/index.js
      config:
        name: <displayed name>
        tagline: '<greeting on the blank session>'
        # defaultLocale: fr     defaultTheme: dark   (defaults)
- id: ui-brand-official   # DSH's own brand occupies the same slots
  disabled: true
```

Then restart the web service. Edit `locales/fr.json` or `style.css` and restart to apply.

## Updating the translations after a DSH update

New DSH strings show in English until translated. Dump the live English dictionaries from a page (the locale
runtime keeps them per namespace), translate only the missing keys, keep `{placeholders}` intact.

## Limits

- The layout is DSH's (sessions grouped by workspace, settings dialog); this plugin restyles and renames, it does
  not add Hermes Desktop screens (messaging, scheduled jobs, kanban…).
- The display font is the system's Bodoni/Didot (macOS, iOS), else Georgia.
