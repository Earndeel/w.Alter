# Hermes Desktop build and UI reference

Use this reference for custom builds, backend resolution, themes, plugin inventory, CDP, and live renderer inspection. Keep build-time facts separate from runtime state.

## Build and backend resolution

The official Electron app resolves a backend through a managed install, a verified `hermes` executable, system Python/import checks, or a bootstrap path before spawning a loopback `hermes serve`/legacy dashboard process. A remote deployment normally needs the supported remote URL/token contract rather than a source fork.

For Intel or other custom Mac builds:

- Build on the target architecture when native modules and packaging require it.
- Use the repository's supported Node/npm and platform build prerequisites.
- Distinguish the installer/setup bundle from the desktop application bundle.
- Verify the packaged renderer entry point and the absolute executable path after installation.
- Do not treat a successful build or fresh-process import as proof that a running Dashboard or Electron process reloaded the change.

When environment variables are used for a GUI launch, remember that macOS `open` uses LaunchServices rather than the invoking shell. Use saved connection state or launch the intended binary with explicit environment, then fully quit before testing a new configuration.

## Theme and renderer state

Dashboard themes and Electron desktop themes are separate systems. Built-in desktop presets in the source require a rebuild; user themes can be merged into the desktop user-theme local-storage record at `hermes-desktop-user-themes-v1`.

When installing a user theme:

1. Read the installed schema, not only a source checkout.
2. Back up the appearance keys and preserve unrelated records.
3. Merge by a unique theme slug; built-ins win on name collisions.
4. Resolve the active profile (`hermes-desktop-active-profile-v1`, defaulting to `default`). Write global theme/mode keys for the default profile and profile maps for named profiles unless changing inherited fallback is intentional.
5. Reload the renderer and verify `document.documentElement.dataset.hermesTheme`, `dataset.hermesMode`, relevant CSS variables, and `document.readyState`.
6. Capture the actual Electron page with CDP for visual QA, then close the temporary port and relaunch without debug flags.

Use native preferences before CSS for separate features such as the conversation backdrop (`hermes.desktop.backdrop.v1`). Stored palette seeds are not rendered pixels: inspect semantic surfaces and computed styles for exact-color requirements. If a narrow CSS escape hatch is necessary, persist it through the user theme's existing typography field, use stable semantic attributes rather than hashed classes, preserve the full record, and verify the injected stylesheet and screenshot.

Never edit Chromium LevelDB while Electron is running, dump complete local storage, or erase layout and theme records as a first response. A temporary CDP port must bind to loopback and be closed after use.

## Plugin inventory

Report three buckets:

1. **Bundled:** registry entries shipped inside the real packaged `app.asar`; consider the companion `app.asar.unpacked` directory during extraction.
2. **Disk/runtime:** child plugin directories with entry files under the active profile's `desktop-plugins` path; inspect named profiles when relevant.
3. **Active:** apply persisted enable/disable decisions to bundled and disk entries, using current keys before legacy fallbacks.

Do not infer inventory from the source checkout, an empty external directory, a single asset filename, or an Electron `Helper (Plugin)` process. Read only narrowly filtered local-storage keys because the profile may contain credentials and sessions.

## Live DOM and CDP

Use CDP for factual questions—presence, selectors, computed styles, geometry, console errors, and rendered screenshots—not for aesthetic judgment. Check the documented development port first and match the main renderer target. If no port exists, do not relaunch the user's app; use an isolated app instance with a temporary `HERMES_HOME`, user-data directory, and port.

Project evaluations down to small JSON objects. Prefer stable `data-slot` selectors. If a style appears not to apply, inspect the node's own classes, ancestors, inherited values, and winning computed rule before sweeping call sites. Verify both required inclusion and exclusion behavior, not merely that a value is non-empty.

## Reload ownership map

| Layer | Reloads | Does not reload |
|---|---|---|
| Electron process | renderer bundle, GUI environment, local Electron state | remote Python modules |
| Dashboard service | server modules, provider registry, shared API | independent TUI sessions |
| TUI/session worker | its own UI or conversation worker | shared Dashboard registry and other sessions |

Always compare process start time with the edit time and check cgroups before restarting. Verify the actual live picker, DOM, API, or screenshot after the correct owner reloads.

## Verification checklist

- [ ] Build artifacts and active bundle path are known.
- [ ] Remote readiness, protected API, and WebSocket behavior are live-tested.
- [ ] Appearance writes are scoped, merged, backed up, and reversible.
- [ ] Exact rendered surfaces—not only stored theme seeds—were checked.
- [ ] Bundled, disk/runtime, and effective plugin counts are separate.
- [ ] CDP was isolated or matched to the intended renderer and is closed afterward.
