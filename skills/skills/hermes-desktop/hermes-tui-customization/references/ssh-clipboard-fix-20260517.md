# SSH Clipboard Fix — Session 2026-05-17

## Problem

User runs hermes TUI on Oracle VPS (Linux ARM64, headless, no X11/Wayland). Connects from Mac via cmux → SSH → tmux. Could not copy-paste in TUI — Ctrl+C was interrupt, not copy. Cmd+C didn't work at all. Links were not clickable.

## Root Causes (chain)

```
cmux (Mac) → SSH → tmux (ubuntu user) → sudo -i → bash -lc → hermes --tui
```

1. **tmux runs as ubuntu, not root** — tmux.conf was edited at `/root/.tmux.conf` (wrong) instead of `/home/ubuntu/.tmux.conf`
2. **`sudo -i` strips SSH_CONNECTION** — hermes had no SSH env vars, so `shouldEmitClipboardSequence()` returned false inside tmux
3. **tmux.conf missing `set-clipboard on`** — even if OSC 52 was emitted, tmux wouldn't forward it to the outer terminal
4. **`isActionMod()` only accepts meta/super on macOS** — Cmd+C arriving over SSH with `key.meta=true` was ignored on Linux
5. **`openExternalUrl()` calls xdg-open** — not installed on headless VPS, link clicks did nothing

## Fixes Applied

### Infrastructure (not in TUI source — survives updates)

| File | Change |
|------|--------|
| `/home/ubuntu/.tmux.conf` | Added `set-clipboard on`, `update-environment "SSH_CONNECTION ..."` |
| `/etc/sudoers.d/keep-ssh-env` | `Defaults env_keep += "SSH_CONNECTION SSH_CLIENT SSH_TTY"` |
| `/root/.bashrc` | Added `export HERMES_TUI_FORCE_OSC52=1` |

### TUI source (in overrides — survives updates via restore script)

| File | Change |
|------|--------|
| `lib/platform.ts` | `isActionMod()` accepts `key.meta`/`key.super` on Linux when `isRemoteShell()` |
| `lib/openExternalUrl.ts` | Fallback: copy URL to clipboard via OSC 52 when no browser opener available |

## Verification

After `tmux kill-server` + reconnect + relaunch:
1. Select text → Cmd+C → clipboard on Mac ✓
2. Ctrl+C → interrupt (no selection) ✓
3. Click link → URL copied to Mac clipboard via OSC 52 ✓

## Key Insight

The clipboard chain has 4 independent failure points. ALL must be correct:
1. `HERMES_TUI_FORCE_OSC52=1` → forces OSC 52 emission
2. `set-clipboard on` in tmux.conf → tmux forwards OSC 52
3. `allow-passthrough on` in tmux.conf → tmux passes escape sequences
4. `SSH_CONNECTION` set in hermes env → detection + sudoers preservation
