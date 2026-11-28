---
name: computer-use-state-verification
description: Use when restoring or proving a desktop UI layout/state.
---

# Computer-Use State Verification and Reversible UI Restoration

Use this skill whenever a desktop action changes layout, panes, sidebars, dialogs, workspace zones, or another persistent UI state; especially when the user says that a previous restoration did not actually return to the initial state.

This is a class-level verification skill, not a recipe for one application. The central rule is simple: **semantic accessibility state is evidence of identity; the fresh screenshot is evidence of physical geometry and visual completion. Neither one replaces the other.**

## Non-negotiable success condition

Do not say that a UI state was restored until all of these are true:

1. A fresh screenshot shows the intended physical arrangement.
2. A fresh accessibility snapshot shows the expected semantic anchors and visibility labels.
3. The screenshot is compared with a known baseline or with an explicitly defined target state.
4. Any transient overlay, editor, tooltip, cursor artifact, or modal is absent from the final screenshot.
5. The action session is cleaned up and its end state is verified.

A click result of `confirmed` or a label changing from `Hide` to `Show` is not, by itself, proof that panels are on the correct sides. UI labels can remain semantically correct while the physical layout is mirrored, stale, or rendered by a different pane.

## Workflow

### 1. Establish a baseline before mutating the UI

- Identify the exact app pid and window id. Do not use a similarly sized auxiliary window.
- Capture a screenshot and an AX tree from the same window state.
- Record a small set of stable anchors: pane title, distinctive control, and frame/side. For example, record `SESSIONS`, `New session`, `Show projects`, and the project-tree root instead of relying on a generic `Hide sidebar` label.
- Save the baseline screenshot when the task may require a visual comparison. Avoid copying chat content into the report; inspect only geometry and controls.
- Define the target in plain language, such as “sessions left, files right, both visible, no overlay.”

### 2. Decide which source is authoritative for each claim

- **Physical geometry and visual visibility:** fresh screenshot.
- **Element identity, action target, and semantic open/closed state:** fresh AX snapshot.
- **Intended default/reset arrangement:** the application’s source or documented reset path, when available.
- **Completion:** the intersection of all three, not one signal.

Never infer a panel’s side from a button label. A button called `Hide right sidebar` can be present while the visible content is a swapped navigation pane. Compare the frame of real content anchors and inspect the screenshot.

### 3. Use the action ladder without blind retries

For CuaDriver-style automation:

1. Take a fresh `get_window_state` snapshot.
2. Prefer the exact `element_token` from that snapshot for an AX action.
3. Request a new snapshot after every mutation.
4. If the AX action is `unverifiable` or has no visual mutation, do not repeat the same call blindly.
5. Escalate in order: background AX → fresh snapshot → background pixel → fresh snapshot → foreground action.
6. Use pixel coordinates only from the current screenshot. CuaDriver’s `x,y` window-local coordinates are read directly from the PNG returned by `get_window_state`; do not invent Retina/downscale math. If the target is small or the result is uncertain, request a debug crosshair image and inspect where the click landed.
7. After pixel or foreground fallback, take another screenshot before deciding whether the action worked.

A foreground action that returns `unverifiable` is not failure and is not success. It is a request to inspect the new state.

### 4. Prefer the application’s official reset path

If the app exposes a `Default`, `Reset`, layout editor, or restore-layout command, use that instead of repeatedly toggling individual panes. A reset is safer than trying to infer how many swaps and hides are needed to undo a history of actions.

For Hermes Desktop specifically, the source establishes a default layout tree with sessions on the left and the workspace/file rail on the right. The `Swap sidebar sides` control toggles the mirror flag; it is not the same operation as resetting the full layout tree. Trace the layout store and tree controller before choosing between a flip and a reset.

Modifier caveat: a computer-use driver may hold a native modifier while the renderer’s DOM event does not expose `metaKey`/`ctrlKey` as expected. If a modifier-click on the layout control reports `unverifiable` or opens the layout editor instead of performing a transparent reset, do not claim the reset fired. Use the visible `Reset`/`Default` control explicitly, close the editor with `Done`, and then verify the underlying layout with a fresh screenshot and AX snapshot.

### 5. Verify the actual target state

For a two-pane layout, verify all of the following independently:

- The content anchor for the primary/navigation pane is on the intended side.
- The content anchor for the project/file/inspector pane is on the intended opposite side.
- Both panes are visibly present, not merely represented by `Hide` labels.
- The main content is between them as expected.
- No layout editor, modal, tooltip, or debug overlay remains.
- AX frames agree with the screenshot’s geometry. If they disagree, trust neither silently: capture again and investigate.

A good final record is concise: “fresh screenshot matches baseline; `SESSIONS` is left; project root is right; both visible; overlay absent.” Do not report “restored” from a stale snapshot.

### 6. Clean up only after verification

- End the CuaDriver session after the final screenshot, not before.
- Verify that post-session calls are rejected or that the session is reported inactive.
- Do not close or kill the user’s application unless explicitly requested; ending the automation session must leave the app open and in the verified state.
- Do not leave debug screenshots, cursor overlays, recording sessions, or temporary modal UI active in the user-facing app.

## Common failure patterns

- **Semantic-label fallacy:** `Hide sidebar`/`Hide right sidebar` look correct, but the content is mirrored. Fix: inspect real content anchors and a screenshot.
- **Stale-token fallacy:** reusing an element token after another snapshot. Fix: re-snapshot every turn and use the newest token.
- **Unverifiable-success fallacy:** treating the driver’s delivery result as a postcondition. Fix: read back with fresh AX plus screenshot.
- **Coordinate-scaling fallacy:** converting logical AX frames to screenshot coordinates manually. Fix: read pixel coordinates directly from the current PNG and use a debug crosshair. Also know the tool contract: the capture response's width/height are PNG (physical) pixels while AX `bounds` are logical points, and `coordinate=` is passed to the driver without a local bounds check — never send pixel coordinates from a stale or differently sized capture; prefer element indices.
- **Toggle-history fallacy:** trying to undo an unknown sequence by clicking visible toggles repeatedly. Fix: use the app’s official default/reset layout path.
- **Overlay fallacy:** the underlying layout is correct but the layout editor or a popover remains open. Fix: close the transient UI and take one last normal-screen screenshot.

## User-specific quality bar

Monsieur expects exact, evidence-backed conclusions. When he reports that a restoration did not happen, treat that as a live-state correction, not as a request for reassurance: re-read the actual source, compare the current screenshot with the baseline, explain the mechanism that caused the false positive, and add a systemic guardrail before concluding.

### Annotated screenshots and “ça” references

When Monsieur attaches a screenshot with arrows, circles, or other annotations and says “ça”, inspect the marked pixels first and name the exact UI elements they identify. Do not collapse several marked elements into a vague description such as “the layout” or “the full screen”: distinguish each target (for example, the submitted user-message container versus the composer field), describe the concrete visual change, and only then infer the likely CSS/layout mechanism. If the screenshot is available, use it as the primary evidence; do not answer from an assumed generic interface.

## Reference

For the Hermes Desktop sidebar case, including the baseline anchors, source symbols, and the verified CuaDriver readback pattern, see `references/hermes-sidebar-restoration.md`.