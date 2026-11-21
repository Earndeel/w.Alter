# Hermes Desktop navigation and browser shortcuts

Use this reference for shortcut questions or when a user asks to open a visible browser/panel in Hermes Desktop.

## Surface map

| Intent | macOS | Windows/Linux | Desktop action |
|---|---:|---:|---|
| Open embedded browser tab | `⌘⇧L` | `Ctrl+Shift+L` | `view.showBrowser` → `openBrowserTab` |
| Toggle right sidebar | `⌘J` | `Ctrl+J` | `view.toggleRightSidebar` |
| Toggle left sidebar | `⌘B` | `Ctrl+B` | `view.toggleSidebar` |
| Open command palette | `⌘K` or `⌘P` | `Ctrl+K` or `Ctrl+P` | `nav.commandPalette` |
| Open keybind settings | `⌘/` | `Ctrl+/` | `keybinds.openPanel` |
| Close the focused tab/pane | `⌘W` | `Ctrl+W` | `view.closeTab` |

The right sidebar can contain different panes depending on the current layout; `⌘J` is a side toggle, not the browser opener. `⌘⇧L` opens the in-app browser, not Safari/Brave. A `⌘`/`Ctrl`-click on a web link is the escape hatch to the native OS browser.

## Verification procedure

1. Ask which surface is intended: embedded browser, right sidebar, or native OS browser.
2. Prefer the current Desktop documentation's **Windows, tabs & panes** section for the user-facing map.
3. If a source checkout is available, verify the action defaults in `apps/desktop/src/lib/keybinds/actions.ts` and the handlers in `apps/desktop/src/app/hooks/use-keybinds.ts`; do not infer Desktop shortcuts from TUI documentation.
4. If the agent is asked to open a visible page, call the Desktop preview operation with the URL, then read the preview back. A successful remote/headless browser call alone does not prove that the Desktop pane is visible.
5. If a shortcut has been rebound, use the keybind panel (`⌘/` on macOS) or the live binding state instead of reporting the shipped default as the active binding.

## Common confusion

- `Ctrl+J` is documented as TUI multiline input; in Desktop on Windows/Linux it is the right-sidebar toggle because Desktop uses the `mod` convention for that action.
- The embedded browser/preview belongs to the Desktop renderer. Camoufox, Browserbase, Chromium CDP, and other backend browser sessions are separate surfaces unless explicitly bridged into Desktop preview.
- Do not claim that a side-panel shortcut opened a browser tab. Report the exact surface that changed and verify it when performing the action.
