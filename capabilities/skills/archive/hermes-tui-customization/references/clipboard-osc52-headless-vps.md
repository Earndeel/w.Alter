# Clipboard / OSC 52 on Headless VPS (SSH + tmux + cmux)

## Problem
Copy-paste in the TUI fails silently when running on a headless Linux VPS (no X11/Wayland). Ctrl+C does nothing or interrupts instead of copying.

## Root Cause Chain (3 layers)

### Layer 1: tmux loses SSH environment
`SSH_CONNECTION` is empty inside tmux because `update-environment` is not configured.
Without `SSH_CONNECTION`, the TUI's `shouldEmitClipboardSequence()` (in `packages/hermes-ink/src/ink/termio/osc.ts`) returns false when `TMUX` is set → no OSC 52 emitted.

### Layer 2: tmux doesn't forward OSC 52
`set-clipboard` defaults to off in tmux. Even if the TUI emits OSC 52, tmux intercepts it and doesn't forward to the outer terminal.

### Layer 3: TUI can't detect SSH
Without `SSH_CONNECTION`, `getClipboardPath()` returns `'tmux-buffer'` (not `'osc52'`), and `shouldEmitClipboardSequence()` returns false. The TUI tries native tools (xclip/xsel) which fail without `$DISPLAY`.

## Clipboard Flow (ink internals)
```
getClipboardPath() in packages/hermes-ink/src/ink/termio/osc.ts:
  - macOS local → 'native' (pbcopy)
  - TMUX set    → 'tmux-buffer'
  - else        → 'osc52'

shouldEmitClipboardSequence():
  - HERMES_TUI_FORCE_OSC52=1 → true (override)
  - SSH_CONNECTION set        → true
  - no TMUX, no STY           → true
  - else                      → false

setClipboard():
  1. shouldUseNativeClipboard() → tries xclip/xsel (skipped over SSH)
  2. tmuxLoadBuffer()           → tmux load-buffer
  3. emits OSC 52 sequence     → wrapped in tmux passthrough if in tmux
```

## Fix (3 changes)

### 1. ~/.tmux.conf
```
set -g set-clipboard on
set -g allow-passthrough on
set -g update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"
```

### 2. ~/.bashrc
```bash
export HERMES_TUI_FORCE_OSC52=1
```

### 3. Restart tmux
```bash
tmux kill-server  # kills all sessions
```

## Mac Terminal Requirements
OSC 52 must be supported AND enabled on the Mac terminal:
- **iTerm2**: Preferences → Profiles → Terminal → "Applications in terminal may access clipboard" → ON
- **Kitty / WezTerm / Ghostty**: works by default
- **Terminal.app**: does NOT support OSC 52 — must switch to iTerm2/Kitty

## Verification
After restart, in a new tmux+TUI session:
1. Select text with mouse in TUI
2. Ctrl+C (or Cmd+C on Mac)
3. Cmd+V on Mac → text should paste

## Key Source Files
- `packages/hermes-ink/src/ink/termio/osc.ts` — setClipboard(), getClipboardPath(), shouldEmitClipboardSequence()
- `packages/hermes-ink/src/utils/env.ts` — OSC52_CAPABLE_TERMINALS, isOsc52CapableTerminal()
- `ui-tui/src/lib/clipboard.ts` — writeClipboardText(), readClipboardText()
- `ui-tui/src/lib/osc52.ts` — writeOsc52Clipboard(), readOsc52Clipboard()
- `ui-tui/src/app/useInputHandlers.ts` — Ctrl+C handler (isCopyShortcut + interrupt fallthrough)
- `ui-tui/src/app/useMainApp.ts` — copy-on-select (macOS only, line ~164)

## cmux-Specific Gotchas

cmux is a terminal multiplexer (runs on VPS as non-root user, e.g. `ubuntu`). Key findings from debugging session (2026-05-17):

### tmux user mismatch
cmux launches tmux as the `ubuntu` user, not root. The tmux server process is owned by `ubuntu`. Therefore `/root/.tmux.conf` is IGNORED — the config that matters is `/home/ubuntu/.tmux.conf`. Always verify with `ps aux | grep tmux`.

### cmux does NOT sync SSH_CONNECTION
cmux has `_CMUX_TMUX_SYNC_KEYS` in its bootstrap script that syncs cmux-internal variables into tmux's global environment. `SSH_CONNECTION` is NOT in this list. The tmux `update-environment` setting is the correct path.

### sudo -i strips SSH_CONNECTION
The hermes launcher scripts (`~/bin/start-hermes-root-new`, `~/bin/hermes-root-tmux`) use `sudo -i bash -lc 'hermes --tui'`. `sudo -i` strips SSH env vars by default. Requires `/etc/sudoers.d/keep-ssh-env` fix.

### Launcher scripts
- `~/bin/hermes-root-tmux` — persistent session named `hermes-root`
- `~/bin/start-hermes-root-new` — timestamped sessions like `hermes-20260517-133433-3977`

### Diagnosis for cmux setups
```bash
# 1. Which user runs tmux?
ps aux | grep tmux | grep -v grep

# 2. Does the tmux-user's tmux.conf have set-clipboard?
cat /home/<user>/.tmux.conf

# 3. Is SSH_CONNECTION in tmux's global environment?
sudo -u <user> tmux show-environment -g | grep SSH_CONNECTION

# 4. Does the hermes process have SSH_CONNECTION?
cat /proc/<hermes-pid>/environ | tr '\0' '\n' | grep SSH_CONNECTION

# 5. Does sudo -i preserve SSH_CONNECTION?
SSH_CONNECTION="test" sudo -i bash -c 'echo $SSH_CONNECTION'

# 6. cmux bootstrap location
ls /home/<user>/.cmux/relay/*.bootstrap.sh
```
