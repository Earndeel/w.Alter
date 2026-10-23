#!/bin/bash
# cmux-reconnect.sh — reconnect ALL broken cmux sessions transparently
# Tested on macOS with cmux.app, autossh tunnel (localhost:2222), and multiple workspaces
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

# Kill dead SSH processes
pkill -f "ssh.*walter-ts" 2>/dev/null
sleep 1

RECONNECTED=0

is_broken() {
    local screen="$1"
    # Explicit broken pipe / connection closed
    echo "$screen" | grep -qi "broken pipe\|Connection.*closed\|connection reset" && return 0
    # Dead local prompt (no active SSH)
    echo "$screen" | grep -q "^${LOCAL_USER}@.*~ %" && return 0
    echo "$screen" | grep -q "^${LOCAL_USER}@.*\$ $" && return 0
    # Script not found (tunnel worked but command failed)
    echo "$screen" | grep -qi "No such file\|command not found" && return 0
    return 1
}

for ws in $($CMUX list-workspaces 2>/dev/null | grep -o "workspace:[0-9]*"); do
    for pane in $($CMUX list-panes --workspace "$ws" 2>/dev/null | grep -o "pane:[0-9]*"); do
        for surface in $($CMUX list-pane-surfaces --workspace "$ws" --pane "$pane" 2>/dev/null | grep -o "surface:[0-9]*"); do
            SCREEN=$($CMUX read-screen --workspace "$ws" --surface "$surface" --lines 5 2>/dev/null)

            if is_broken "$SCREEN"; then
                echo "$(date): $ws/$pane/$surface is broken, reconnecting..." >> "$LOG"

                # Workspace 1 = hermes, others = plain shell
                if [ "$ws" = "workspace:1" ]; then
                    CMD="ssh -tt -o ClearAllForwardings=yes walter-ts \"bash ~/bin/start-hermes-root-new\""
                else
                    CMD="ssh -tt -o ClearAllForwardings=yes walter-ts"
                fi

                # Ctrl+C, clear, then command
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
