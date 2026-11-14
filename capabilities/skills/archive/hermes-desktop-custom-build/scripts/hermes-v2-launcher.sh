#!/bin/bash
# Hermes V2 Launcher — Intel Mac Edition
# Tunnel SSH vers VPS → fetch le vrai token session → lance l'app Electron en mode remote
#
# Approche hybride : connection.json (pas env vars) car `open` ne passe pas les env vars.
# Le token est extrait dynamiquement du dashboard HTML à chaque lancement
# car il change au redémarrage du gateway.
#
# Usage : /tmp/hermes-v2-launcher.sh

set -euo pipefail

readonly APP="/Applications/Hermes V2.app"
readonly SSH_HOST="walter-ts"
readonly LOCAL_PORT=9119
readonly REMOTE_PORT=8787
readonly CTRL="/tmp/hermes-v2-ssh-ctrl"
readonly CONFIG_DIR="$HOME/Library/Application Support/Hermes"
readonly CONFIG_FILE="$CONFIG_DIR/connection.json"

# ── Cron healthcheck mode ───────────────────────────
if [[ "${1:-}" == "--ping" ]]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) SSH tunnel ready"
    exit 0
fi

echo "[hermes-v2] $(date) Starting..."

# ── 1. Kill existing V2 processes (avoid SingletonLock) ─
echo "[hermes-v2] Killing existing Hermes V2 instances..."
pkill -f 'Hermes V2.app' 2>/dev/null || true
sleep 2

# ── 2. Kill existing SSH tunnel ─────────────────────
echo "[hermes-v2] Killing existing SSH tunnel..."
pkill -f "ssh.*-L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" 2>/dev/null || true
rm -f "$CTRL"
sleep 1

# ── 3. Start SSH tunnel ─────────────────────────────
echo "[hermes-v2] Starting SSH tunnel..."
ssh -f -N -M -S "$CTRL" \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
    "$SSH_HOST"

# ── 4. Wait for dashboard ───────────────────────────
echo "[hermes-v2] Waiting for dashboard..."
for i in $(seq 1 15); do
    if curl -s --max-time 2 "http://127.0.0.1:${LOCAL_PORT}/api/status" > /dev/null 2>&1; then
        echo "[hermes-v2] Dashboard ready (attempt $i)"
        break
    fi
    sleep 1
done

# ── 5. Fetch REAL session token from dashboard HTML ──
# Le gateway injecte window.__HERMES_SESSION_TOKEN__ dans le HTML.
# Ce token change à chaque redémarrage du gateway — on le récupère dynamiquement.
echo "[hermes-v2] Fetching session token..."
SESSION_TOKEN=$(curl -s --max-time 5 "http://127.0.0.1:${LOCAL_PORT}/" | \
    grep -o '__HERMES_SESSION_TOKEN__="[^"]*"' | head -1 | \
    sed 's/__HERMES_SESSION_TOKEN__="//;s/"$//')

if [[ -z "$SESSION_TOKEN" ]]; then
    echo "[hermes-v2] ERROR: Could not fetch session token from dashboard"
    exit 1
fi
echo "[hermes-v2] Got token: ${SESSION_TOKEN:0:10}..."

# ── 6. Write connection.json with real token ────────
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_FILE" << TOKENEOF
{
  "mode": "remote",
  "remote": {
    "url": "http://127.0.0.1:${LOCAL_PORT}",
    "token": { "value": "${SESSION_TOKEN}" },
    "authMode": "token"
  }
}
TOKENEOF
echo "[hermes-v2] connection.json written with live token"

# ── 7. Launch Electron app ──────────────────────────
# On utilise `open` car connection.json est déjà écrit.
# `open` ne passe pas d'env vars → c'est pour ça qu'on écrit connection.json.
echo "[hermes-v2] Launching Hermes V2..."
open "$APP"

echo "[hermes-v2] $(date) Done."
