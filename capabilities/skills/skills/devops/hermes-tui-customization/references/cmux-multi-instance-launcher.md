# cmux Multi-Instance TUI Launcher (macOS → VPS)

## Architecture

```
macOS shortcut (.app) → AppleScript → shell script → cmux CLI → new split pane → SSH → VPS → tmux session → hermes --tui
```

Each shortcut click creates an **independent split pane** in cmux with its own SSH connection, tmux session, and hermes TUI instance. Existing sessions stay alive. User can place panes side by side in the same workspace.

## macOS Side

### Shortcut: AppleScript App

`~/Desktop/Hermes cmux.app` — an AppleScript app (created via Script Editor → File → Export as Application). Script:

```applescript
do shell script "zsh $HOME/bin/start-hermes-cmux >/tmp/hermes-cmux-app.log 2>&1 &"
```

### Launcher Script: `~/bin/start-hermes-cmux`

```bash
#!/usr/bin/env bash

CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"
LOG="/tmp/hermes-cmux.log"

exec >> "$LOG" 2>&1
echo "---- $(date) ----"

[ -x "$CMUX" ] || {
  echo "ERREUR: cmux CLI introuvable: $CMUX"
  exit 1
}

open -a cmux

i=0
while [ "$i" -lt 60 ]; do
  "$CMUX" list-workspaces >/dev/null 2>&1 && break
  sleep 0.25
  i=$((i+1))
done

CMD="ssh -tt -o ClearAllForwardings=yes walter-ts 'bash ~/bin/start-hermes-root-new'"

# Create split and get its surface ID from the output
OUT=$("$CMUX" new-split right --focus true 2>&1)
echo "new-split output: $OUT"

SURFACE=$(echo "$OUT" | grep -o "surface:[0-9]\\+" | head -1)
echo "target surface: $SURFACE"
echo "command: $CMD"

# Wait for the new pane shell to be ready
sleep 0.5

if [ -n "$SURFACE" ]; then
  "$CMUX" send --surface "$SURFACE" "$CMD
"
else
  echo "WARN: no surface detected, sending to focused pane"
  "$CMUX" send "$CMD
"
fi
```

### SSH Config: `~/.ssh/config`

```
Host walter-ts
    HostName localhost
    Port 2222
    User ubuntu
    IdentityFile ~/Desktop/Keys/ssh-key-2025-12-10.key
    LocalForward 18789 127.0.0.1:18789
```

Port 2222 = autossh reverse tunnel from VPS to Mac.

## VPS Side

### Launcher Script: `/home/ubuntu/bin/start-hermes-root-new`

**Critical:** The SSH user is `ubuntu`, so `~/bin/` resolves to `/home/ubuntu/bin/`, NOT `/root/bin/`. Always write to the SSH user's home.

```bash
#!/usr/bin/env bash

SESSION="hermes-$(cat /proc/sys/kernel/random/uuid | cut -d- -f1)"
LOG="/tmp/hermes-cmux.log"

exec >> "$LOG" 2>&1
echo "---- $(date) ---- session=$SESSION"

# Create fresh tmux session
# --preserve-env: pass required env vars (bypasses .bashrc auto-attach)
# --norc: skip .bashrc so it doesn't exec tmux attach to existing session
tmux new-session -d -s "$SESSION" \
  "sudo --preserve-env=HERMES_HOME,HERMES_TUI_FORCE_OSC52,PATH,SSH_CONNECTION,DISPLAY,WAYLAND_DISPLAY \
  -u root bash --norc -c 'cd /root && hermes --tui; exec bash'" 2>>"$LOG"

# Set per-session options
tmux set-option -t "$SESSION" allow-passthrough on
tmux set-option -t "$SESSION" set-clipboard on
tmux set-option -t "$SESSION" status off
tmux set-option -t "$SESSION" mouse on
tmux set-option -t "$SESSION" update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"

echo "OK: attaching to $SESSION"
tmux attach-session -t "$SESSION"
echo "Session $SESSION ended"
```

## Pitfalls

1. **`cmux new-workspace --command` creates a SEPARATE workspace** — the user wants panes side by side in the same workspace. Use `new-split right --focus true` + `cmux send --surface` instead.

2. **`.bashrc` auto-attach hijacks sessions** — Root's `~/.bashrc` has `exec tmux attach -t hermes` which reattaches to the existing session. Every new pane becomes a mirror. Fix: `bash --norc` bypasses `.bashrc` entirely.

3. **`sudo -i bash -lc` triggers .bashrc auto-attach** — Use `sudo --preserve-env=... -u root bash --norc -c` instead. `--preserve-env` passes HERMES_HOME, PATH, etc. without sourcing `.bashrc`.

4. **Script path: `/home/ubuntu/bin/` not `/root/bin/`** — The SSH user is `ubuntu`. Writing to `/root/bin/` has no effect because the SSH command runs `bash ~/bin/start-hermes-root-new` which resolves to ubuntu's home.

5. **Session name uniqueness** — `hermes-$(date +%s)-$$` can collide if two clicks happen in the same second. Use UUID: `hermes-$(cat /proc/sys/kernel/random/uuid | cut -d- -f1)`.

6. **`sleep 0.5` after new-split** — The new pane's shell needs time to initialize before `cmux send` delivers the command. Without the delay, keystrokes may be lost or land in the wrong context.

7. **`cmux send` needs a newline** — The command string must end with `\n` to execute. Use `"$CMD\n"` not `"$CMD"`.

8. **`exec bash` keeps session alive** — After hermes exits, `exec bash` replaces the process with a shell so the tmux session (and cmux pane) stays open.

9. **Orphan sessions accumulate** — Each click creates a new tmux session. Old sessions stay alive until manually killed. Periodically clean with `sudo -u ubuntu tmux kill-session -t <name>`.

10. **`open -a cmux` is idempotent** — If cmux is already running, `open -a cmux` just activates it (doesn't open a new instance). Safe to call every time.

11. **cmux `--focus true` on new-split** — Ensures the new pane is focused so `cmux send` targets it correctly. Without it, `send` may go to the previously focused pane.
