# Runtime polish beyond desktop palette tokens

Use this when a valid Hermes Desktop user theme still leaves non-palette visuals that the user rejects (background artwork, a conspicuous status item, or other component chrome).

## Decision order

1. Inspect the current renderer/source and determine whether the visual has its own persisted state.
2. Use that native preference if it exists.
3. If the problem is a palette token, adjust the correct theme token and verify the component's computed style.
4. Only for component-specific polish, attach narrowly scoped CSS to the user theme.

Do not rebuild or edit `app.asar` for a runtime-only customization.

## Conversation backdrop

The faint statue/pattern behind the transcript is a separate feature, not part of `DesktopThemeColors`:

- localStorage key: `hermes.desktop.backdrop.v1`
- enabled value: `true`
- disabled value: `false`

Write the raw string `false`, reload the renderer, and verify both:

```js
localStorage.getItem('hermes.desktop.backdrop.v1') === 'false'
!document.querySelector('img[src*="filler-bg0"]')
```

This is preferable to hiding the image with CSS because it follows the app's own state model.

## Status-bar connection token split

The bottom-left connection item does not always use `primary`:

- SSH connection: `bg-primary text-primary-foreground`
- generic remote or cloud connection: `bg-accent text-accent-foreground`

Therefore, changing `colors.primary` will not affect a generic `Remote: …` block. Inspect `connection.remoteKind`, the element classes, or computed styles before changing tokens. Avoid broad token changes when the complaint concerns one component; they alter buttons and other surfaces too.

## Exact-color trap: palette seeds are not rendered pixels

`colors.background: '#000000'` and `colors.userBubble: '#000000'` are only seeds. In dark mode, `applyTheme()` and `styles.css` mix them with the hard-coded neutral chrome (`#0d0d0e`), so the rendered conversation surface can become `#030304` even though localStorage says `#000000`.

When the user requires an exact pixel color, do not validate the stored seed alone. Inspect the actual elements and derived variables with `getComputedStyle()`:

- conversation: `[data-chat-surface]` / `--ui-chat-surface-background`
- user bubble and inline edit bubble: `.composer-human-message` / `--dt-user-bubble`
- composer: `[data-slot='composer-surface'] > div[aria-hidden]` / `--composer-fill`

If the mix chain prevents the requested literal, use a theme-scoped override for those semantic variables/selectors. A hard-coded color is appropriate here only because exact color identity is the explicit requirement; keep all unrelated accents on theme variables. Verify the final values are `rgb(0, 0, 0)`, not merely visually dark.

## Decorative sidebar dither markers

`SidebarPanelLabel` prepends an `aria-hidden` `.dither` square to section headings. It is decorative, not a status signal. If a custom theme should remove it, scope the override to sidebar section labels (for example, the `.dither` child of the uppercase `tracking-[0.16em]` label under `[data-slot='sidebar']`) instead of hiding `.dither` globally: the same class is also used for meaningful loading, streaming-stall, timeline, and onboarding indicators. Verify the targeted markers compute to `display: none` while session dots and platform icons remain visible.

## Sidebar labels and pane tab strips

The sidebar section labels (`PINNED`, `SESSIONS`, messaging platforms, `CRON JOBS`) use `--theme-primary` directly through `SidebarPanelLabel`. Do not darken `colors.primary` to tame one status-bar component: it makes every section label nearly disappear. Keep the brand primary at the intended neon value and polish the status item with a component-scoped selector instead.

The pane tab-strip gutter does not use the conversation background. Each `[data-zone-tabstrip]` sets `--pane-tab-strip-bg` from `--theme-card-seed`, so a black conversation can still leave a tinted tab bar. For an exact-black theme, override both `--pane-tab-strip-bg` and the strip's computed background on `[data-zone-tabstrip]`, then verify `backgroundColor === 'rgb(0, 0, 0)'`. Preserve the active-tab and inset-stroke rules so selection remains legible.

## Pane seams after the tree-sash update

The pane tree renders each boundary as a 9 px draggable `[role='separator']`, but the persistent visual line is its first child: `--ui-stroke-secondary` at `opacity: 0.1` and one CSS pixel. On an exact-black theme, the token's own alpha compounds with that opacity (observed effective alpha about 2.2%), making the seam practically invisible.

If a rounded composer still rasterizes vertical sides as two dim pixels while horizontal sides are one exact pixel, the cause is fractional x-position, not a second shadow: `getComputedStyle()` can report equal widths while screenshot rasterization differs by orientation. Snap the surface by a tiny subpixel translation derived from a CDP screenshot sweep (on this Mac scale, `translateX(-0.32px)` produced one exact `(81,182,249)` pixel on both sides), then verify top, bottom, left, and right pixel runs. Keep the shift scoped to the bordered surface; do not replace it with a wide border or pseudo-element halo.

## Uniform border system

When the user explicitly requires every *visible* border to use one literal color and width, update both the theme border tokens (`border`, `input`, `ring`, `sidebarBorder`, `userBubbleBorder`, `composerRing`) and a theme-scoped CSS override. Cover the existing Tailwind border utilities: `.border`, `.border-2`, directional `.border-t/.border-r/.border-b/.border-l`, `.border-x/.border-y`, and numbered directional variants actually found in the source such as `.border-l-2`. Exclude `.border-transparent` so structural spacing borders do not become new visible boxes. Explicitly cover `[data-slot='composer-surface']`, `.composer-human-message`, `.desktop-input-chrome`, pane sash line children, and any shadow-based tab-strip seam.

Hermes Desktop applies different scale paths: an authored `2px` component border was observed by `getComputedStyle()` as about `1.607px`, while an authored `1px` border was quantized to about `0.536px`. Do not assume the pane sash is the seam: the sidebar already owns a `border-r`, while the adjacent draggable separator overlays both a persistent first span and a 4 px hover span. Styling that first span creates a doubled/antialiased seam. For a flat one-pixel sidebar edge, keep the sidebar border, hide both visual spans of that specific adjacent separator (including hover), and leave the 9 px draggable parent intact.

The active pane tab has its own `inset 0 -2px` shadow. Never add a second shadow to the whole `[data-zone-tabstrip]`: that creates a 3-pixel intersection. For a flat hairline, clear the strip and active-tab shadows and render the active underline as an absolutely positioned `::after` background. At the observed Electron scale, `height: 0.5px` produced exactly one screenshot row, matching the `h-px` rule after `YESTERDAY`; `height: 1px` produced two rows. Remove `box-shadow`, `filter`, and `outline` from the explicitly targeted bubbles/inputs when the requirement is “one pixel without effects.” Verify actual screenshot pixel runs as well as computed styles—nominal CSS widths alone miss overlaps and rasterization.

## Reliable graceful quit after CDP work

`tell application id "com.nousresearch.hermes" to quit` can leave an active renderer running. Do not kill the process. Use the macOS menu command through System Events instead:

```applescript
tell application "System Events"
  tell process "Hermes"
    click menu item "Quit Hermes" of menu 1 of menu bar item "Hermes" of menu bar 1
  end tell
end tell
```

Wait for every `/Applications/Hermes V2.app/Contents/` process to exit, then launch with `open -g -a "Hermes V2"`. Verify the main process has no `--remote-debugging-port` argument and the CDP port is closed.

## Theme-scoped persistent CSS escape hatch

`applyTheme()` injects `theme.typography.fontUrl` as a stylesheet link on every boot. A percent-encoded `data:text/css` URL can therefore carry a small theme-specific override without rebuilding the Electron binary or installing a global plugin.

Example shape:

```js
const css = `
footer[data-slot='statusbar'] > div:first-child > button:first-child:is([class~='bg-accent'], [class~='bg-primary']) {
  background: transparent !important;
  color: var(--ui-text-secondary) !important;
  margin-left: 0 !important;
  padding-inline: 0.375rem 0.5rem !important;
  border-right: 1px solid var(--ui-stroke-tertiary) !important;
}
footer[data-slot='statusbar'] > div:first-child > button:first-child:is([class~='bg-accent'], [class~='bg-primary']) > svg {
  color: var(--ui-accent) !important;
  opacity: 0.9;
}`.trim()

const themesKey = 'hermes-desktop-user-themes-v1'
const themes = JSON.parse(localStorage.getItem(themesKey) || '{}')
const theme = themes['your-theme-name']
theme.typography = {
  ...(theme.typography || {}),
  fontUrl: `data:text/css;charset=utf-8,${encodeURIComponent(css)}`
}
localStorage.setItem(themesKey, JSON.stringify(themes))
location.reload()
```

### Guardrails

- Back up the full theme record and relevant preference keys first.
- Prefer stable semantic attributes (`data-slot`) plus structural/class guards; never use generated hashed class names.
- Keep selectors narrow enough that an absent connection item does not restyle an unrelated first button.
- Preserve existing `typography` fields with object spread.
- Use theme variables inside the override; do not hardcode a second palette.
- Treat this as a theme-local escape hatch. If many components need overrides, build/adopt a proper desktop plugin or change the source and rebuild.

## Verification contract

After reload, verify behavior and visuals, not merely localStorage:

```js
const link = [...document.querySelectorAll('link[data-hermes-theme-font="true"]')]
  .find(node => node.href.startsWith('data:text/css'))

({
  stylesheetPresent: Boolean(link),
  ruleCount: link?.sheet?.cssRules?.length ?? null,
  backdropPresent: Boolean(document.querySelector('img[src*="filler-bg0"]'))
})
```

For the connection item, locate the button by visible connection label and inspect `backgroundColor`, `color`, border, margin, and padding via `getComputedStyle()`. Capture the Electron renderer with CDP `Page.captureScreenshot`; generic macOS screen capture can show the wrong Space or window. Finally quit gracefully and relaunch Hermes normally, confirming the main process no longer carries `--remote-debugging-port`.
