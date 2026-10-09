# cmux Launcher + bashrc Auto-Attach Conflict

## Problem

Clicking the Mac shortcut ("Hermes cmux.app") opens a new cmux split but shows a **mirror** of the existing TUI session instead of a fresh one. Disconnecting one kills both.

## Root Cause

`~/.bashrc` lines 25-30 auto-attach to the `hermes` tmux session on any login shell:

```bash
if [ -z "$TMUX" ] && [ -n "$SSH_TTY" ] && [ "$TERM" != "dumb" ]; then
    exec tmux attach -t hermes   # ← hijacks every new session
fi
```

The launcher script (`~/bin/start-hermes-root-new`) runs `sudo -i bash -lc 'hermes --tui'`. The `-i` flag sources `.bashrc` → `exec tmux attach -t hermes` replaces the shell → `hermes --tui` never executes.

## Fix

### VPS script (`~/bin/start-hermes-root-new`)

```bash
#!/usr/bin/env bash
SESSION="hermes-$(cat /proc/sys/kernel/random/uuid | cut -d- -f1)"
LOG="/tmp/hermes-cmux.log"

exec >> "$LOG" 2>&1
echo "---- $(date) ---- session=$SESSION"

# --norc: skip .bashrc (avoids auto-attach)
# --preserve-env: pass required env vars that .bashrc normally sets
tmux new-session -d -s "$SESSION" \
  "sudo --preserve-env=HERMES_HOME,HERMES_TUI_FORCE_OSC52,PATH,SSH_CONNECTION,DISPLAY,WAYLAND_DISPLAY \
  -u root bash --norc -c 'cd /root && hermes --tui; exec bash'" 2>>"$LOG"

tmux set-option -t "$SESSION" allow-passthrough on
tmux set-option -t "$SESSION" set-clipboard on
tmux set-option -t "$SESSION" status off
tmux set-option -t "$SESSION" mouse on
tmux set-option -t "$SESSION" update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"

echo "OK: attaching to $SESSION"
tmux attach-session -t "$SESSION"
echo "Session $SESSION ended"
```

Key: `bash --norc` skips `.bashrc` entirely. `--preserve-env` passes the env vars that hermes needs (HERMES_HOME, PATH, HERMES_TUI_FORCE_OSC52, SSH_CONNECTION).

### Mac script (`~/bin/start-hermes-cmux`)

```bash
#!/usr/bin/env bash
CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"
LOG="/tmp/hermes-cmux.log"

exec >> "$LOG" 2>&1
echo "---- $(date) ----"

[ -x "$CMUX" ] || { echo "ERREUR: cmux CLI introuvable: $CMUX"; exit 1; }
open -a cmux

i=0
while [ "$i" -lt 60 ]; do
  "$CMUX" list-workspaces >/dev/null 2>&1 && break
  sleep 0.25
  i=$((i+1))
done

CMD="ssh -tt -o ClearAllForwardings=yes walter-ts 'bash ~/bin/start-hermes-root-new'"
OUT=$("$CMUX" new-split right --focus true 2>&1)
echo "new-split output: $OUT"

SURFACE=$(echo "$OUT" | grep -o "surface:[0-9]\\+" | head -1)
echo "target surface: $SURFACE"
echo "command: $CMD"

sleep 0.5  # wait for new pane shell to initialize

if [ -n "$SURFACE" ]; then
  "$CMUX" send --surface "$SURFACE" "$CMD
"
else
  echo "WARN: no surface detected, sending to focused pane"
  "$CMUX" send "$CMD
"
fi
```

## Pitfalls

1. **`sudo -i` sources `.bashrc`** — any `exec` in `.bashrc` replaces the intended command. Always use `bash --norc` when the command must run reliably.
2. **`--preserve-env` vs env_keep** — `env_keep` in sudoers only applies to `sudo -i`. For `sudo -u root bash --norc -c`, use `--preserve-env=VAR1,VAR2` explicitly.
3. **UUID session names** — use `cat /proc/sys/kernel/random/uuid | cut -d- -f1` for 8-char unique names. `date +%s` + PID can collide if two clicks happen in the same second.
4. **`cmux new-pane` has no `--command` flag** — must use `new-split right --focus true` + `cmux send --surface`. The `sleep 0.5` after `new-split` is critical for the shell to be ready.
5. **`new-workspace --command`** works but creates separate workspaces, not side-by-side splits in the same workspace. User explicitly rejected this — wants splits in the same workspace.
