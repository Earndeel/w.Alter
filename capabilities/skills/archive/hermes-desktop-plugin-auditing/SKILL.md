---
name: hermes-desktop-plugin-auditing
description: "Use when auditing Hermes Desktop plugin inventory or state."
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [hermes, desktop, plugins, electron, audit, app-asar]
    category: devops
    related_skills: [hermes-desktop-plugins, inspecting-hermes-desktop-dom]
---

# Hermes Desktop plugin auditing

Determine which plugins are actually present and active in a Hermes Desktop
installation. This skill is for **inventory and verification**, not for
writing a plugin. The central distinction is:

- **Bundled plugins** live inside the packaged Electron application, usually
  in `Contents/Resources/app.asar` on macOS.
- **Disk/runtime plugins** live under the active Hermes home/profile,
  normally `$HERMES_HOME/desktop-plugins/<name>/plugin.js`.
- **Active plugins** are the union of those sources after persisted enable /
  disable decisions are applied.

An empty `desktop-plugins` directory therefore does not justify saying “there
are no plugins”. It only proves that no external disk plugin was found there.

## When to use

- The user asks which plugins are installed in Hermes Desktop.
- Settings → Plugins shows entries that are not visible under
  `~/.hermes/desktop-plugins`.
- A packaged app and the source checkout appear to disagree about available
  plugins.
- You need to distinguish a bundled plugin, an external plugin, and an
  Electron helper process before reporting the inventory.

## Procedure

### 1. Establish the real installation and profile

Do not inspect only the repository checkout. Identify the running or installed
application bundle and the active Hermes home/profile first.

- macOS: locate the actual `Hermes*.app`, then inspect
  `<app>/Contents/Resources/`.
- Linux: inspect the installed AppImage / Electron resources directory or the
  actual packaged app path.
- Windows: inspect the installed app’s `resources/` directory.
- Resolve profile-aware paths through the active `HERMES_HOME`; do not assume
  the default profile when the app can select a named profile.

Keep the audit read-only. Do not relaunch, replace, or patch the user’s app.

### 2. Inventory disk/runtime plugins

Inspect the active profile’s `desktop-plugins` directory. A valid runtime
plugin is normally a child directory containing `plugin.js`; report the child
name and whether the entry file exists. Also check named profile paths when the
active profile is not `default`.

Do not count the directory itself as a plugin. Do not treat unrelated files,
Electron helper processes, or the general Python plugin directory
`$HERMES_HOME/plugins/` as Hermes Desktop plugins.

### 3. Inspect the packaged Electron bundle

Read the app’s `app.asar` and, when present, its adjacent
`app.asar.unpacked` directory. Use an ASAR-aware reader rather than relying on
filesystem directory names; bundled source is commonly archived and compiled.

Useful read-only approaches:

```bash
npm exec --yes --package=@electron/asar@3.4.1 -- asar list /path/to/app.asar
npm exec --yes --package=@electron/asar@3.4.1 -- asar extract /path/to/app.asar /tmp/hermes-app
```

If extraction reports missing files under `*.asar.unpacked`, obtain the
adjacent unpacked directory too and place it beside the copied archive with the
exact expected name (`app.asar.unpacked`) before retrying. This is an archive
layout issue, not proof that the app is corrupt.

Search the extracted compiled renderer for the bundled registry and plugin
exports. Minified builds often retain useful markers such as:

- `../plugins/.../plugin.tsx`
- `kind:\`bundled\``
- `id:\`...\`` and `name:\`...\``
- `defaultEnabled:false`
- `register(ctx)`

Prefer extracting the plugin’s `id`, `name`, default state, and registration
contributions from the registry / export. Do not infer the inventory from one
asset filename or from the current source tree.

### 4. Resolve effective enablement

Bundled and disk plugins can be listed even when disabled. Inspect the
renderer’s persisted plugin decisions in the app’s local storage:

- current key: `hermes.desktop.pluginDecisions.v2`
- legacy fallback: `hermes.desktop.disabledPlugins.v1`

Resolve each plugin as follows:

```text
if an explicit decision exists:
    enabled = persisted decision
else:
    enabled = defaultEnabled ?? true
```

On Chromium/Electron installations, local storage may be LevelDB rather than
SQLite. Read only narrowly filtered keys and values; never dump the complete
profile because it may contain session or credential data. Treat local storage
as evidence of the app’s current choice, not as a replacement for the bundle
registry.

### 5. Report separate buckets

The final report must distinguish:

1. **Bundled** — shipped inside the app bundle.
2. **Disk/runtime** — found under the active profile’s `desktop-plugins`.
3. **Active** — enabled after applying explicit decisions and defaults.

For each plugin include `id`, display name, source, default state when known,
and effective state. State clearly when an empty external directory coexists
with bundled plugins.

A process called `Helper (Plugin)` in Activity Monitor is normally an
Electron/Chromium utility process (for example video capture), not evidence of
a Hermes plugin. Confirm through the registry and plugin settings instead.

## Verification checklist

- [ ] The real packaged app was inspected, not only the repository.
- [ ] `app.asar` and `app.asar.unpacked` were considered.
- [ ] The active profile’s disk-plugin directory was checked.
- [ ] The bundled registry yielded plugin IDs/names rather than guessed names.
- [ ] `hermes.desktop.pluginDecisions.v2` was checked narrowly for overrides.
- [ ] Bundled, disk/runtime, and active counts were reported separately.
- [ ] No app bundle, local storage, or user plugin file was modified.

## Pitfalls

- **Empty external directory ≠ no plugins.** Packaged plugins are not stored
  there.
- **Source checkout ≠ installed app.** A versioned source tree can differ from
  the user’s signed or packaged build.
- **Default state matters.** A plugin with `defaultEnabled: false` can be
  bundled but inactive until explicitly enabled.
- **ASAR extraction needs its companion directory.** Missing
  `app.asar.unpacked` causes misleading ENOENT errors during extraction.
- **Do not use a stale CDP assumption.** Packaged builds may not expose the
  development CDP port; inspecting the bundle and local state is safer and
  does not disturb the user’s session.

## References

- `references/bundled-plugin-audit.md` — reproducible extraction recipe and a
  version-scoped example of the bundled registry pattern.
