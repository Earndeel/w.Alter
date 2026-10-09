# Hermes Desktop sidebar restoration — verified pattern

## Baseline used

The known-good Hermes Desktop screen had:

- the sessions/navigation pane on the **left**;
- the `HERMES-AGENT` project/file tree on the **right**;
- both panes visible;
- no layout editor or other transient overlay.

Useful AX anchors from the baseline were `SESSIONS` near the left edge, `New session` in the left pane, `Show projects` beside the sessions controls, and `Hide right sidebar` in the titlebar. These anchors support the visual comparison; the labels alone do not prove orientation.

## What caused the false positive

The first verification accepted `Hide sidebar` / `Hide right sidebar` labels as proof of restoration. That was wrong: the layout could still be mirrored while the labels remained semantically plausible. A fresh screenshot showed the navigation pane on the right, so the visual geometry contradicted the AX-only conclusion.

A second trap was treating a CuaDriver result of `unverifiable` as a successful mutation. `unverifiable` means that the input was delivered but no postcondition was proven. It requires a new snapshot and screenshot, not a confident summary.

## Source-level reset facts

In the Hermes Desktop source:

- `apps/desktop/src/store/layout.ts` defines the persisted `$panesFlipped` flag and `togglePanesFlipped()`.
- `apps/desktop/src/app/contrib/controller.tsx` derives the flip state from the layout tree and defines `DEFAULT_TREE` with `sessions` before `workspace` and the right-side file rail.
- `apps/desktop/src/app/shell/titlebar-controls.tsx` maps `Swap sidebar sides` to `togglePanesFlipped()` and the `Layout editor` control to the layout editor; its modifier path is intended to call `resetLayoutTree()`.

Therefore a layout reset/default path is preferable to guessing how many sidebar and visibility toggles are needed to undo prior actions.

## Verified readback pattern

1. Bind to the exact Hermes pid/window and start a named CuaDriver session.
2. Capture `get_window_state` with a real PNG and an AX snapshot from the same state.
3. Record both semantic anchors and physical geometry. For CuaDriver pixel actions, read `x,y` directly from the PNG returned by `get_window_state`; do not scale AX logical frames manually. If necessary, request `debug_image_out` and inspect the crosshair.
4. Use the newest `element_token` for AX actions. Re-snapshot after every mutation.
5. If a modifier click on `Layout editor` opens the editor instead of performing a transparent reset, do not infer that the modifier reached the renderer. Use the visible `Reset`/`Default` route explicitly, close the editor with `Done`, and verify the normal screen again.
6. The final screenshot must visibly show sessions left and the project/file tree right, both open, with no editor overlay. Confirm the AX anchors agree, then end the CuaDriver session.

## Minimal evidence to report

Report restoration only after a fresh screenshot and fresh AX readback agree. The useful final evidence is:

- sessions/navigation visibly left;
- `HERMES-AGENT` project/file tree visibly right;
- both panes visible;
- no transient overlay;
- CuaDriver session inactive after cleanup.

Do not include chat content in visual analysis or the user-facing report; inspect layout geometry only.
