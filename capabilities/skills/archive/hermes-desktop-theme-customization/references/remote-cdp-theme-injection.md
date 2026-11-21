# Remote CDP Theme Injection

Use this procedure when Hermes Desktop runs on a Mac reachable over SSH and the theme must be installed without manual DevTools interaction.

## Safety contract

- Inspect the installed/current `DesktopTheme` schema first; the desktop binary and source checkout may be on different versions.
- Quit with AppleScript and reopen normally when finished. Do not leave a remote-debugging port enabled.
- Bind the temporary SSH forward to loopback only.
- Never edit Chromium LevelDB while Electron is running.
- Back up only the appearance keys below; do not dump unrelated localStorage values that may contain private state.
- Merge records. Never replace the full user-theme or per-profile maps.

## Persistence keys

| Key | Shape | Purpose |
|---|---|---|
| `hermes-desktop-user-themes-v1` | JSON record keyed by theme slug | Installed custom themes |
| `hermes-desktop-theme-v2` | raw string | Default/global theme |
| `hermes-desktop-mode-v1` | raw `light`, `dark`, or `system` | Default/global mode |
| `hermes-desktop-profile-themes-v1` | JSON record keyed by profile | Named-profile theme assignments |
| `hermes-desktop-profile-modes-v1` | JSON record keyed by profile | Named-profile mode assignments |
| `hermes-desktop-active-profile-v1` | raw string | Last active profile; missing means `default` |
| `hermes-boot-background` | raw color | Pre-React first paint, updated by `applyTheme` |
| `hermes-boot-color-scheme` | raw mode | Pre-React first paint, updated by `applyTheme` |

`default` is the legacy/global slot. Assign it through `hermes-desktop-theme-v2` and `hermes-desktop-mode-v1`. For a named profile, merge only that profile into the profile records unless changing the global inheritance fallback is intentional.

## CDP sequence

1. Gracefully quit Hermes by bundle identifier (`osascript -e 'tell application id "com.nousresearch.hermes" to quit'`) and wait for the main process to exit. The installed app path may still be named `Hermes V2.app`, while its bundle/display/process name is `Hermes`; addressing `Hermes V2` can silently leave the old process alive and prevent the debug instance from starting.
2. Start the app temporarily with `--remote-debugging-port=9223 --remote-allow-origins=*`.
3. Create a temporary SSH local forward, for example local ephemeral port → Mac `127.0.0.1:9223`.
4. Poll `http://127.0.0.1:<local-port>/json/list` until a page target appears.
5. Connect to its `webSocketDebuggerUrl` and call `Runtime.evaluate`.
6. Read and save the appearance-key backup.
7. Parse records defensively (`{}` on missing/invalid JSON), merge the theme by its unique slug, then assign theme/mode at the correct profile scope.
8. Call `Page.reload` with `ignoreCache: true` and reconnect after the page reload closes the first socket.
9. Verify the rendered state and take `Page.captureScreenshot`.
10. Close the SSH forward, quit gracefully, and reopen Hermes without debugging flags.

## Runtime validation

A successful storage write is insufficient. Evaluate the live renderer and require all of these relationships:

```js
const root = document.documentElement
const style = getComputedStyle(root)

({
  theme: root.dataset.hermesTheme,
  mode: root.dataset.hermesMode,
  background: style.getPropertyValue('--theme-background-seed').trim(),
  primary: style.getPropertyValue('--theme-primary').trim(),
  composerRing: style.getPropertyValue('--dt-composer-ring').trim(),
  readyState: document.readyState
})
```

Expected invariants:

- `theme` equals the installed slug.
- `mode` matches the intended rendered mode.
- CSS variables equal the palette seeds, not merely non-empty values.
- `readyState` is `complete` and the React root contains rendered children.
- The normal relaunch command line contains no `remote-debugging` flag.

## Visual QA checklist

Prefer CDP `Page.captureScreenshot` because it captures the actual Electron page regardless of the active macOS Space.

Check:

- main background and sidebar match the intended dark surface;
- active-session markers, borders, focus rings, and composer ring use the accent consistently;
- foreground and muted text remain readable;
- user bubbles and cards are distinguishable without turning into bright slabs;
- destructive, success, diff, and syntax colors remain semantically distinct from the brand accent;
- no light surface survives in popovers, cards, titlebar, or composer;
- integrated terminal ANSI colors harmonize with the palette when the schema supports them.

## Rollback

Restore each backed-up appearance key exactly:

- if the saved value was `null`, remove the key;
- otherwise restore the raw saved string with `localStorage.setItem`.

Reload, verify the previous dataset/CSS values, then relaunch normally.