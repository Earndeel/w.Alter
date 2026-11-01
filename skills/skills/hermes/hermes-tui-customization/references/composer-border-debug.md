# Composer Border / Frame Debug Reference

Session: 2026-05-06  
Symptom: User reports "la zone de saisie n'est plus encadrée comme avant" (input area no longer framed).

## Investigation Path

1. **Check current layout** — `appLayout.tsx` `ComposerPane` has NO `borderStyle` on the input block. The only borders near the input are:
   - `StatusRule` separator line (`─` in `t.color.border`) directly above the input.
   - `FloatBox` borders on overlays (model picker, session picker, etc.).

2. **Check git history** — Recent commits that touched composer layout:
   - `98f5be13f` "fix(tui): word-wrap composer input" — added `width={Math.max(1, composer.cols - 2)}` to the input row `Box`, moved `position="absolute"` GoodVibesHeart outside the TextInput wrapper.
   - `e7091bb32` "fix(tui): mouse + keyboard text selection in the composer" — added mouse drag handlers, changed prompt width from 3 to 2.
   - `4cc6da84a` "fix(tui): normalize legacy Terminal.app colors" — added ANSI256 color normalization that can remap `border` color on light terminals, potentially making separator lines invisible.

3. **Search for borderStyle removals** — No commit removed a border from the composer itself. The "missing frame" is either:
   - A lost local patch (check `git stash list`).
   - The `StatusRule` separator becoming invisible due to color normalization.
   - A previous overlay or prompt box that gave the impression of a frame.

## Key Code Locations

| File | Line | Purpose |
|------|------|---------|
| `ui-tui/src/components/appLayout.tsx` | ~246 | `ComposerPane` — input block lives here |
| `ui-tui/src/components/appChrome.tsx` | ~335 | `StatusRule` — `─` separator above input |
| `ui-tui/src/theme.ts` | ~259 | `DARK_THEME.border = '#CD7F32'` |
| `ui-tui/src/theme.ts` | ~310 | `LIGHT_THEME.border = '#7A4F1F'` |
| `ui-tui/src/components/textInput.tsx` | ~234 | `TextInput` component — no border prop |

## Proposed Patch

Wrap the `{!isBlocked && (...)}` block in `ComposerPane` with:

```tsx
<Box
  borderColor={ui.theme.color.border}
  borderStyle="single"
  flexDirection="column"
  paddingX={1}
  width={Math.max(1, composer.cols - 2)}
>
  {/* existing input block */}
</Box>
```

Account for 4 extra columns consumed by border + padding when sizing `TextInput.columns`.

## Related Commands

```bash
# Check for lost local patches after update
cd ~/.hermes/hermes-agent && git stash list

# Diff a stashed file against current
git diff HEAD stash@{0} -- ui-tui/src/components/appLayout.tsx

# Check theme detection env vars
echo $HERMES_TUI_THEME $HERMES_TUI_LIGHT $COLORFGBG

# Force dark theme to test visibility
HERMES_TUI_THEME=dark hermes --tui
```
