# hermes-tui-customization — Bordered input area and composer frame, scroll and resize tuning, live todo panel updates, the session orchestrator (Ctrl+X).

Moved verbatim from SKILL.md on 2026-11-01.

## Bordered Input Area (components/appLayout.tsx)

The TextInput (line ~224) sits inside a bare `<Box position="relative">`. Wrap it with a border:

```tsx
<Box borderStyle="round" borderColor={ui.theme.color.bronze} flexDirection="column" paddingX={1} marginTop={1}>
  {/* existing prompt + TextInput here */}
</Box>
```

Subtract 2 extra columns from TextInput `columns` prop (was `cols - pw - 2`, becomes `cols - pw - 4`) to account for the border + paddingX.

## Scroll & Resize Tuning

### Wheel scroll step (`config/limits.ts`)

`WHEEL_SCROLL_STEP` controls how many lines each wheel tick scrolls. Default is 3.
For smoother scrolling, reduce to 1:

```typescript
export const WHEEL_SCROLL_STEP = 1  // was 3 — smoother trackpad/wheel feel
```

### Resize stability (`hooks/useVirtualHistory.ts`)

`FREEZE_RENDERS` controls how many render cycles the virtual scroller freezes the mount
range after a column resize (to let Yoga reflow stabilize). Default is 2. If text disappears
or jumps after resize, increase to 4:

```typescript
const FREEZE_RENDERS = 4  // was 2 — better resize stability
```

The resize handler (useMainApp.ts) debounces `terminal.resize` RPC to gateway at 100ms.
The virtual history scales cached heights by `prevColumns / columns` ratio and skips one
measurement cycle to avoid poisoning the cache with pre-reflow Yoga heights.

## Backend: Live Todo Panel Updates

The TUI shows a live todo panel (`LiveTodoPanel` in `streamingAssistant.tsx`) that displays the agent's current task list. By default, it only updates when the agent explicitly calls the `todo` tool. After the initial plan is created, the agent executes steps (read_file, write_file, etc.) without calling `todo` again — the panel stays frozen.

**Fix:** Inject the current agent todo store into **every** `tool.complete` event, not just `todo` tool completions. In `tui_gateway/server.py`, `_on_tool_complete()`:

```python
if name == "todo":
    try:
        data = json.loads(result)
        if isinstance(data, dict) and isinstance(data.get("todos"), list):
            payload["todos"] = data.get("todos")
    except Exception:
        pass
else:
    # Always include current agent todos so the TUI live todo panel
    # stays fresh even when the agent does not explicitly call todo.
    agent = session.get("agent") if session else None
    if agent is not None:
        try:
            todo_store = getattr(agent, "_todo_store", None)
            if todo_store is not None:
                current_todos = todo_store.read()
                if current_todos:
                    payload["todos"] = current_todos
        except Exception:
            pass
```

**Why this works:** The frontend's `turnController.recordTodos()` is called on every `tool.complete` event (see `createGatewayEventHandler.ts`). By attaching the current todo list to every tool completion, the live panel refreshes after each step automatically — no frontend changes needed.

**Pitfall:** Do not emit empty `todos: []` — only include the field if `current_todos` is non-empty. This avoids clearing the panel when the agent has no active todos.

## Composer Input Border / Frame

The user-input area (`TextInput` inside `ComposerPane`) has **no explicit border by default**. It sits as a flat row of text prefixed by the prompt glyph (`❯` or `$`). If the user says "the input area is no longer framed," check two things:

1. **Was there ever a border?** Search git history for `borderStyle` in `appLayout.tsx`. Upstream Hermes has never shipped a border around the composer — the "frame" the user remembers may have been:
   - The `StatusRule` separator line (`─`) directly above the input, which can *look* like a top border when the terminal is wide.
   - A transient overlay (approval prompt, etc.) that had a border and gave the impression the input itself was framed.
   - A previous local patch that was lost during `hermes update` (the update stashes local changes).

2. **Is the separator line invisible?** The `StatusRule` (appChrome.tsx) draws `─` characters in `t.color.border`. On light-terminal profiles, or after commit `4cc6da84a` (ANSI256 normalization), the border color may be remapped to a tone very close to the background, making the separator disappear. This creates the *illusion* that a frame was removed.

### Adding a Border Around the Composer

To add an actual border, wrap the input block in `appLayout.tsx` (~line 246, inside `ComposerPane`):

```tsx
{!isBlocked && (
  <Box
    borderColor={ui.theme.color.border}
    borderStyle="single"
    flexDirection="column"
    paddingX={1}
    width={Math.max(1, composer.cols - 2)}
  >
    {composer.inputBuf.map((line, i) => (
      <Box key={i}>
        <Box width={promptWidth}>
          {/* prompt prefix logic */}
        </Box>
        <Text color={ui.theme.color.text}>{line || ' '}</Text>
      </Box>
    ))}

    <Box
      onMouseDown={captureInputDrag}
      onMouseDrag={dragFromPromptRow}
      onMouseUp={endInputDrag}
      position="relative"
      width={Math.max(1, composer.cols - 2)}
    >
      <Box width={promptWidth}>{/* prompt prefix */}</Box>
      <Box flexGrow={0} flexShrink={0} height={inputHeight} width={inputColumns}>
        <TextInput
          columns={inputColumns}
          mouseApiRef={inputMouseRef}
          onChange={composer.updateInput}
          onPaste={composer.handleTextPaste}
          onSubmit={composer.submit}
          placeholder={composer.empty ? PLACEHOLDER : ui.busy ? 'Ctrl+C to interrupt…' : ''}
          value={composer.input}
        />
      </Box>
      <Box position="absolute" right={0}>
        <GoodVibesHeart t={ui.theme} tick={status.goodVibesTick} />
      </Box>
    </Box>
  </Box>
)}
```

**Column math:** The outer `Box` with `paddingX={1}` + `borderStyle="single"` consumes 4 columns (left border + left pad + right pad + right border). If you previously sized `TextInput` at `cols - promptWidth - 2`, you may need to reduce it by another 2 so the text doesn't wrap prematurely inside the narrower inner width.

### Theme `border` Color Visibility on Light Terminals

Commit `4cc6da84a` ("normalize legacy Terminal.app colors") added ANSI256-safe color remapping. On terminals detected as light, the `border` token (`#7A4F1F` in `LIGHT_THEME`) is normalized through `normalizeAnsiForeground()` into an `ansi256()` value. If that mapped color is too close to the background, separator lines disappear.

**Quick diagnosis:**
- Run `echo $HERMES_TUI_THEME $HERMES_TUI_LIGHT $COLORFGBG` to check detection.
- Temporarily force dark theme: `HERMES_TUI_THEME=dark hermes --tui`. If the frame reappears, the issue is color normalization.
- Override the border color in your skin YAML to something darker/higher contrast on light backgrounds:
  ```yaml
  colors:
    banner_border: "#5A3A10"   # darker bronze for light terminals
  ```

## Session Orchestrator (Ctrl+X)

The TUI has a **Session Orchestrator** overlay (`activeSessionSwitcher.tsx`) for managing multiple live sessions. It is NOT visible by default — users frequently can't find it.

**Open:** `Ctrl+X` or `/sessions` slash command.

**Capabilities:**
- Lists all active sessions with status glyphs: `✓` idle, `…` starting, `?` waiting, `▶` working
- Shows model name per session (short form: strips provider prefix)
- Create new session inline with prompt input
- Model picker (Tab) before launching a new session

**Keybindings:**
| Key | Action |
|-----|--------|
| ↑↓ | Navigate sessions |
| Enter | Switch to selected / start new |
| Ctrl+N | New session row |
| Ctrl+D | Close selected session |
| Ctrl+R | Refresh session list |
| Tab | Model picker (on new session row) |
| Esc | Close overlay |

**Source:** `ui-tui/src/components/activeSessionSwitcher.tsx` + mounted in `appOverlays.tsx` when `overlay.sessions` is true.

**Pitfall:** There is no visual indicator that Ctrl+X exists. Users must know the shortcut or use `/sessions`. The Kanban board has NO TUI component — it is CLI-only (`hermes kanban`) + gateway (`/kanban`) + dashboard plugin API.

