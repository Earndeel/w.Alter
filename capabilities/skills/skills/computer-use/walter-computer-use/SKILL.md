---
name: walter-computer-use
description: Use when Hermes needs GUI/device manipulation via Walter Operator.
---

# Walter Operator

## When
Use `computer_use` for local or remote GUI/device manipulation: apps, windows, dialogs, keyboard, pointer, files, Finder, and System Settings.

External information, documentation, and public-web research belong to Walter Browse. Device/session interaction belongs here.

## Boundary
Hermes is the only planner and reasoner. Operator only observes, performs atomic actions, verifies local effects, and returns facts. It never interprets the overall user goal or decides completion.

## Loop
`observe → Hermes reasons → act → compact post-action facts`

If a popup, missing window, changed UI, permission screen, or error appears, observe it and let Hermes choose the next action. Small bounded mechanical waits and targeted verification inside one atomic action are allowed.

## Progressive knowledge
Load only the smallest relevant reference with `skill_view`:
- launch/open/focus: `references/actions/launch-focus.md`
- dialogs/permissions: `references/actions/dialogs-permissions.md`
- keyboard/pointer/verification: `references/actions/input-verification.md`
- device facts: `references/device-context.md`
- Safari: `references/apps/safari.md`
- Notes: `references/apps/notes.md`
- Blender: `references/apps/blender.md`
- Finder/file pickers: `references/apps/finder.md`
- System Settings: `references/apps/system-settings.md`

Do not load app references speculatively. Reusable lessons from instructive failures patch the smallest relevant reference; normal successes and transient errors are not stored.
