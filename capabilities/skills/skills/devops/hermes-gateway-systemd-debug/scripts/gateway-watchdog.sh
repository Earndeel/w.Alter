#!/bin/bash
# Gateway Watchdog — checks if hermes-gateway is alive, restarts if dead
# Designed for systemd user-level timer (every 5 min) or cron
#
# Setup (systemd user timer):
#   cp scripts/gateway-watchdog.sh ~/.hermes/scripts/
#   chmod +x ~/.hermes/scripts/gateway-watchdog.sh
#   # Create timer + service units in ~/.config/systemd/user/
#   systemctl --user daemon-reload
#   systemctl --user enable --now gateway-watchdog.timer
#
# Requires: XDG_RUNTIME_DIR=/run/user/0 in timer environment

set -euo pipefail

LOG="${HOME}/.hermes/logs/watchdog.log"
PID_FILE="${HOME}/.hermes/gateway.pid"
SERVICE="hermes-gateway.service"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# Check if the user-level service is active
if systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
    # Service says active — verify the process actually exists
    if [ -f "$PID_FILE" ]; then
        PID=$(python3 -c "import json; print(json.load(open('$PID_FILE'))['pid'])" 2>/dev/null || echo "0")
        if [ "$PID" -gt 0 ] && kill -0 "$PID" 2>/dev/null; then
            exit 0  # All good
        fi
    fi
fi

# Gateway is down — restart it
log "Gateway DOWN. Restarting $SERVICE..."
systemctl --user restart "$SERVICE" 2>&1 | while read line; do log "  $line"; done

sleep 5
if systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
    log "Gateway restarted successfully."
else
    log "ERROR: Gateway failed to restart!"
fi
