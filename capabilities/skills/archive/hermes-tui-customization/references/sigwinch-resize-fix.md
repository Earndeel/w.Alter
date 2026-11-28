---
name: tui-resize-propagation
description: Fix TUI resize detection in nested terminal multiplexer environments (cmux + tmux + SSH) where SIGWINCH is not reliably propagated.
version: 1.0.0
author: W.Alther
tags: [tui, cmux, tmux, resize, sigwinch, terminal]
---

# TUI Resize Propagation Fix

## When to use

The Hermes TUI (`hermes --tui`) doesn't respond to terminal resize when running inside a nested multiplexer chain (e.g., cmux pane → SSH → tmux → hermes). The TUI stays frozen at old dimensions, then snaps back with visual glitches.

## Root cause

SIGWINCH doesn't reliably propagate through the `cmux → SSH → tmux → hermes` chain. cmux may not send SIGWINCH to the SSH process, or tmux may not forward it to the hermes child. Ink (the React terminal framework) only detects resize via `stdout.on('resize')`, which depends on SIGWINCH.

## Fix: polling fallback in terminalDimensions.ts

**File:** `ui-tui/src/lib/terminalDimensions.ts` → `clampStdoutDimensions()`

After installing clamping getters on `process.stdout`, add a `setInterval` that polls raw dimensions every 250ms. When they differ from the previous poll, emit a synthetic `resize` event.

```typescript
// Inside clampStdoutDimensions(), after the clamping getters and target[PATCHED] = true:

// SIGWINCH polling fallback for nested multiplexers
if (typeof readCols() === 'number') {
  let prevPollCols = readCols() as number
  let prevPollRows = readRows() as number

  const pollInterval = setInterval(() => {
    const curCols = readCols() as number
    const curRows = readRows() as number
    if (curCols !== prevPollCols || curRows !== prevPollRows) {
      prevPollCols = curCols
      prevPollRows = curRows
      ;(target as unknown as EmittableStream).emit('resize')
    }
  }, 250)

  if (pollInterval.unref) pollInterval.unref()
}
```

Requires adding `EmittableStream` interface:
```typescript
interface EmittableStream extends ClampableStream {
  emit(event: string): boolean
}
```

## Key details

- Polls **raw** (unclamped) values via original property descriptors — not the sanitized getters
- 250ms interval: responsive enough for UX, low overhead
- `unref()`: poller doesn't keep the process alive on exit
- Emits the same `'resize'` event Node.js emits on real SIGWINCH — Ink and all `stdout.on('resize', …)` handlers fire normally

## Persistence across Hermes updates

The file is tracked by the TUI override system:
1. **Override:** `/root/.hermes/tui-overrides/terminalDimensions.ts`
2. **Guard:** `ensure-tui-design.sh` checks drift (pairs array includes `terminalDimensions.ts:ui-tui/src/lib/terminalDimensions.ts`)
3. **Restore:** `restore-tui-design.sh` copies override back + rebuilds TUI

When adding new overrides, update both `ensure-tui-design.sh` (pairs array) and `restore-tui-design.sh` (cp lines).

## Why not fix tmux/cmux

- cmux is proprietary — no source access
- tmux `allow-passthrough` controls escape sequences, NOT SIGWINCH propagation
- The polling approach is the only reliable fix from the TUI side
