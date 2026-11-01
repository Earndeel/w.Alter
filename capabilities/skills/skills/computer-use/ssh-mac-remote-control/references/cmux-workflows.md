# ssh-mac-remote-control — cmux: multi-session reconnection, SSH config for tunnel-based cmux, configuration, the Hermes shortcut (fresh TUI in the same workspace).

Moved verbatim from SKILL.md on 2026-11-01.

## cmux Multi-Session Reconnection

### The problem
cmux (macOS terminal multiplexer) runs multiple SSH sessions to the VPS. When the network drops, ALL sessions get broken pipes. The autossh tunnel reconnects, but cmux's individual sessions stay dead.

### The solution: cmux-reconnect.sh

Script that scans ALL cmux workspaces/panes/surfaces, detects broken sessions, and reconnects each one.

Create `~/bin/cmux-reconnect.sh`:
```bash
#!/bin/bash
LOG="/tmp/cmux-reconnect.log"
CMUX="/Applications/cmux.app/Contents/Resources/bin/cmux"
CTRL_C=$(printf "\x03")
LOCAL_USER=$(whoami)

echo "$(date): Network change detected, scanning sessions..." >> "$LOG"

# Wait for tunnel (max 60s)
for i in $(seq 1 60); do
    if nc -z localhost 2222 2>/dev/null; then
        echo "$(date): Tunnel up after ${i}s" >> "$LOG"
        sleep 2
        break
    fi
    sleep 1
done

if ! nc -z localhost 2222 2>/dev/null; then
    echo "$(date): Tunnel never came back, aborting" >> "$LOG"
    exit 1
fi

pkill -f "ssh.*walter-ts" 2>/dev/null
sleep 1

RECONNECTED=0

is_broken() {
    local screen="$1"
    echo "$screen" | grep -qi "broken pipe\|Connection.*closed\|connection reset" && return 0
    echo "$screen" | grep -q "^${LOCAL_USER}@.*~ %" && return 0
    echo "$screen" | grep -qi "No such file\|command not found" && return 0
    return 1
}

for ws in $($CMUX list-workspaces 2>/dev/null | grep -o "workspace:[0-9]*"); do
    for pane in $($CMUX list-panes --workspace "$ws" 2>/dev/null | grep -o "pane:[0-9]*"); do
        for surface in $($CMUX list-pane-surfaces --workspace "$ws" --pane "$pane" 2>/dev/null | grep -o "surface:[0-9]*"); do
            SCREEN=$($CMUX read-screen --workspace "$ws" --surface "$surface" --lines 5 2>/dev/null)
            if is_broken "$SCREEN"; then
                $CMUX send --workspace "$ws" --surface "$surface" "$CTRL_C" 2>/dev/null
                sleep 0.3
                $CMUX send --workspace "$ws" --surface "$surface" "clear" 2>/dev/null
                $CMUX send-key --workspace "$ws" --surface "$surface" "enter" 2>/dev/null
                sleep 0.3
                $CMUX send --workspace "$ws" --surface "$surface" "$CMD" 2>/dev/null
                $CMUX send-key --workspace "$ws" --surface "$surface" "enter" 2>/dev/null
                RECONNECTED=$((RECONNECTED + 1))
                echo "$(date): Reconnected $ws/$pane/$surface" >> "$LOG"
                sleep 1
            fi
        done
    done
done

echo "$(date): Done. Reconnected $RECONNECTED sessions." >> "$LOG"
```

### launchd agent for network changes
Create `~/Library/LaunchAgents/com.walter.cmux-reconnect.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.walter.cmux-reconnect</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/<user>/bin/cmux-reconnect.sh</string>
    </array>
    <key>RunAtLoad</key><false/>
    <key>KeepAlive</key><dict><key>NetworkState</key><true/></dict>
    <key>ThrottleInterval</key><integer>30</integer>
    <key>StandardOutPath</key><string>/tmp/cmux-reconnect-stdout.log</string>
    <key>StandardErrorPath</key><string>/tmp/cmux-reconnect-stderr.log</string>
</dict>
</plist>
```

## SSH Config for Tunnel-Based cmux

Route `walter-ts` through the autossh tunnel instead of direct Tailscale:
```
Host walter-ts
    HostName localhost
    Port 2222
    User <vps-user>
    IdentityFile ~/Desktop/Keys/ssh-key.pem
    LocalForward 18789 127.0.0.1:18789
    LocalForward 18792 127.0.0.1:18792
    ServerAliveInterval 10
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

**Pitfall:** When the reconnect script sends `ssh -tt walter-ts "bash ~/bin/start-hermes-root-new"`, the `~` gets expanded locally on the Mac, not on the VPS. Use quotes: `ssh -tt walter-ts "\"bash ~/bin/start-hermes-root-new\""` or use full paths.

## cmux Hermes Shortcut — Fresh TUI in Same Workspace

The `Hermes cmux.app` applet on Desktop runs `~/bin/start-hermes-cmux`.

### Requirements

- Plain `ssh walter-ts` must give a normal root shell — no auto-attach.
- Only the Desktop shortcut should launch `hermes --tui`.
- The shortcut must open a **new panel in the same cmux workspace**.
- The new panel must run a **fresh tmux UUID session**, not mirror the existing TUI.

### Root Cause of the Mirror Bug

cmux `new-split` can mirror/clone the active terminal surface. Sending text to the returned surface can therefore type into the existing TUI input box. The reliable pattern is:

1. `cmux new-pane --type terminal` — create a panel in the same workspace.
2. Immediately `cmux respawn-pane --surface <new-surface> --command <cmd>` — replace any mirrored surface process with a fresh SSH command.

Do **not** use `new-split` for this workflow.

### Mac script: `~/bin/start-hermes-cmux`

```bash
#!/usr/bin/env bash
CMUX=/Applications/cmux.app/Contents/Resources/bin/cmux
LOG=/tmp/hermes-cmux.log
exec >> "$LOG" 2>&1
echo "---- $(date) ----"

[ -x "$CMUX" ] || { echo "ERREUR: cmux CLI introuvable: $CMUX"; exit 1; }

open -a cmux

for i in $(seq 1 60); do
  "$CMUX" list-workspaces >/dev/null 2>&1 && break
  sleep 0.25
done

WS=$("$CMUX" current-workspace 2>/dev/null | grep -o "workspace:[0-9]*" | head -1)
[ -n "$WS" ] || WS="workspace:1"

OUT=$("$CMUX" new-pane --type terminal --direction right --workspace "$WS" --focus true 2>&1)
SURFACE=$(echo "$OUT" | grep -o "surface:[0-9]*" | head -1)
[ -n "$SURFACE" ] || { echo "ERROR: no surface returned: $OUT"; exit 1; }

CMD="ssh -tt -o ClearAllForwardings=yes -o ConnectTimeout=10 walter-ts bash /root/bin/start-hermes-root-new"
"$CMUX" respawn-pane --workspace "$WS" --surface "$SURFACE" --command "$CMD"
```

### VPS script: `/root/bin/start-hermes-root-new`

Creates a UUID-named tmux session to avoid conflicts with any existing `hermes` session. Critical details:
- log to `/root/.hermes/logs/hermes-cmux.log`, **not** `/tmp/hermes-cmux.log` (can be owned by the Mac user and block redirection)
- `unset TMUX TMUX_PANE` before `tmux new-session`
- run `bash --norc` to avoid shell startup auto-attach
- blank resume env vars so the TUI starts fresh

```bash
#!/usr/bin/env bash
set -u
LOG_DIR="/root/.hermes/logs"
LOG="$LOG_DIR/hermes-cmux.log"
mkdir -p "$LOG_DIR"

# Guard: if `hermes update` reset TUI source files without running the shell hook,
# restore custom design before launching the TUI.
if [[ -x /root/.hermes/scripts/ensure-tui-design.sh ]]; then
  /root/.hermes/scripts/ensure-tui-design.sh >> "$LOG" 2>&1 || {
    echo "TUI design restore guard failed; refusing to launch broken TUI."
    exit 1
  }
fi

SESSION="hermes-$(cat /proc/sys/kernel/random/uuid | cut -d- -f1)"
echo "---- $(date) ---- session=$SESSION" >> "$LOG"

unset TMUX TMUX_PANE HERMES_TUI_RESUME HERMES_RESUME_SESSION

env -u TMUX -u TMUX_PANE tmux new-session -d -s "$SESSION" \
  "cd /root && HERMES_TUI_RESUME= HERMES_RESUME_SESSION= HERMES_TUI_FORCE_OSC52=1 bash --norc -c 'hermes --tui; exec bash'" >> "$LOG" 2>&1
```
tmux has-session -t "$SESSION" 2>/dev/null || { echo "Failed to create $SESSION"; exit 1; }
tmux set-option -t "$SESSION" allow-passthrough on
tmux set-option -t "$SESSION" set-clipboard on
tmux set-option -t "$SESSION" status off
tmux set-option -t "$SESSION" mouse on
tmux set-option -t "$SESSION" update-environment "SSH_CONNECTION SSH_CLIENT SSH_TTY DISPLAY WAYLAND_DISPLAY"

echo "OK: attaching to $SESSION"
tmux attach-session -t "$SESSION"
```

### Auto-Attach Anti-Pattern

**NEVER put unconditional tmux auto-attach in Mac `.zshrc` or VPS `/root/.bashrc`.** It makes plain `ssh walter-ts` attach to the existing TUI and breaks the cmux shortcut.

If kept for legacy reasons, gate it:
```bash
if [ "${HERMES_AUTO_ATTACH:-0}" = "1" ] && [ -z "$TMUX" ] && [ -n "$SSH_TTY" ]; then
    tmux attach -t hermes || tmux new -s hermes
fi
```

Plain SSH must remain plain shell. The shortcut owns TUI startup.

### cmux CLI Reference

| Command | Usage |
|---|---|
| `cmux list-workspaces` | List all workspaces |
| `cmux list-panes --workspace workspace:N` | List panes in workspace |
| `cmux list-pane-surfaces --workspace W --pane P` | List surfaces (terminal instances) |
| `cmux read-screen --workspace W --surface S --lines N` | Read terminal content |
| `cmux send --workspace W --surface S "text"` | Send text to surface |
| `cmux send-key --workspace W --surface S "enter"` | Send key press |
| `cmux new-split right --focus true` | Create new split pane |

## cmux Configuration

cmux config lives at `~/.config/cmux/` on the Mac. Key files: `cmux.json` and `settings.json` (update both).

**Notification blue border fix:** Set `paneFlash: false` and `unreadPaneRing: false` in both files. Keeps dock badge + menu bar notifications. The blue border is cmux's own `paneFlash`, NOT tmux — OSC 777 passthrough is independent of tmux bells.

See `references/cmux-configuration.md` for full config reference.

