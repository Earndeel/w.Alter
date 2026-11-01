# cmux-Notify Event Filtering

## Problem

The default cmux-notify patch fires `_emit_cmux_notify()` on **every tool completion**. With a typical agent run doing 5-15 tool calls (terminal, read_file, search_files, etc.), the user gets a notification between every single message — pure spam.

## Solution: Filter by event type

Only fire notifications for high-signal events:

| Event | When | Notification |
|-------|------|-------------|
| `message.complete` (status=complete) | Agent run finished | "Hermes ✅ · Run terminée" |
| `message.complete` (status=error/failed) | Agent run failed | "Hermes ❌ · Run échouée" |
| `error` | Gateway error | "Hermes ❌ · Run échouée" |
| `background.complete` | Background task done | Same as message.complete |
| `clarify.request` | Agent needs user input | "Hermes ⏳ · Attend votre réponse" |

**Intentionally excluded:** tool.start, tool.complete, tool.progress, reasoning.delta — too noisy.

## Implementation

### Backend (`tui_gateway/server.py`)

1. **Remove tool-level notification** — delete `_emit_cmux_notify(sid, success=not bool(tool_error))` from `_on_tool_complete()`

2. **Add `reason` parameter** to `_emit_cmux_notify`:
```python
def _emit_cmux_notify(sid: str, success: bool, reason: str = "complete") -> None:
    # ... existing code ...
    # payload: {"success": bool(success), "reason": reason}
```

3. **Add `clarify.request` handler** in `_cmux_notify_for_event`:
```python
elif event == "clarify.request":
    _emit_cmux_notify(sid, success=True, reason="input")
    return
```

### Frontend (`createGatewayEventHandler.ts`)

Update `notifyCmux` to use the `reason` field:
```typescript
const notifyCmux = (success: boolean, reason?: string) => {
  let title: string
  let body: string

  if (reason === 'input') {
    title = 'Hermes ⏳'
    body = 'Attend votre réponse'
  } else if (success) {
    title = 'Hermes ✅'
    body = 'Run terminée'
  } else {
    title = 'Hermes ❌'
    body = 'Run échouée'
  }
  // ... spawn cmux-notify ...
}
```

### Type definition (`gatewayTypes.ts`)

Update the `cmux.notify` payload type:
```typescript
| { payload: { reason?: string; success?: boolean }; session_id?: string; type: 'cmux.notify' }
```

### Apply script (`apply-cmux-notify-patch.py`)

The restore script must match — remove `_emit_cmux_notify` from tool completion, add `reason` param, add `clarify.request` handler. The `apply-cmux-notify-patch.py` at `~/.hermes/scripts/` handles this.

## Files modified

- `tui_gateway/server.py` — backend event filtering
- `ui-tui/src/app/createGatewayEventHandler.ts` — frontend notification dispatch
- `ui-tui/src/gatewayTypes.ts` — type definition
- `~/.hermes/scripts/apply-cmux-notify-patch.py` — restore script (re-applied after hermes update)

## Pitfalls

1. **`clarify.request` goes through `_block()` which calls `_emit()`** — so it passes through `_cmux_notify_for_event()` automatically. No special wiring needed.

2. **Subagent completions** still fire notifications (via the separate subagent hook at line ~1681 in server.py). This is intentional — subagent runs can be long and the user wants to know when they finish.

3. **The `reason` field is optional** — old payloads without it still work (frontend defaults to the success/error path).

4. **tmux DCS passthrough required** — The `cmux-notify` binary must wrap OSC sequences in DCS passthrough format (`ESC P tmux ; <OSC> ESC \`) for tmux to forward them to the SSH client. Direct writes to `/dev/pts/N` don't reach the outer terminal. See the SKILL.md "cmux-notify: DCS Passthrough for tmux" section for the correct implementation.
