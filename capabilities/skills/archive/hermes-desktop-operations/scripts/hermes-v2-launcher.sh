#!/bin/bash
# Reversible Hermes V2 remote launcher: SSH loopback forward, live token, saved connection.
set -euo pipefail

readonly APP="/Applications/Hermes V2.app/Contents/MacOS/Hermes"
readonly SSH_HOST="${HERMES_SSH_HOST:-walter-ts}"
readonly LOCAL_PORT="${HERMES_LOCAL_PORT:-9119}"
readonly REMOTE_PORT="${HERMES_REMOTE_PORT:-8787}"
readonly CONTROL_SOCKET="${HERMES_SSH_CONTROL_SOCKET:-$HOME/.hermes/hermes-v2-ssh-ctrl}"
readonly CONFIG_DIR="$HOME/Library/Application Support/Hermes"
readonly CONFIG_FILE="$CONFIG_DIR/connection.json"

# Prefer graceful app shutdown. Do not blanket-kill similarly named processes.
osascript -e 'tell application id "com.nousresearch.hermes" to quit' >/dev/null 2>&1 || true
sleep 2

# Close only the control socket owned by this launcher, if present.
if [[ -S "$CONTROL_SOCKET" ]]; then
  ssh -S "$CONTROL_SOCKET" -O exit "$SSH_HOST" >/dev/null 2>&1 || true
  rm -f "$CONTROL_SOCKET"
fi
mkdir -p "$(dirname "$CONTROL_SOCKET")"

ssh -f -N -M -S "$CONTROL_SOCKET" \
  -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" "$SSH_HOST"

ready=0
for _ in $(seq 1 20); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${LOCAL_PORT}/api/status" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
(( ready == 1 )) || { echo 'Dashboard did not become ready' >&2; exit 1; }

session_token=$(curl -fsS --max-time 5 "http://127.0.0.1:${LOCAL_PORT}/" | \
  sed -n 's/.*__HERMES_SESSION_TOKEN__="\([^"]*\)".*/\1/p' | head -n 1)
[[ -n "$session_token" ]] || { echo 'Could not obtain a live dashboard session token' >&2; exit 1; }

mkdir -p "$CONFIG_DIR"
python3 - "$CONFIG_FILE" "$LOCAL_PORT" "$session_token" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
port, token = sys.argv[2], sys.argv[3]
try:
    data = json.loads(path.read_text()) if path.exists() else {}
except (OSError, json.JSONDecodeError):
    data = {}
data['mode'] = 'remote'
remote = dict(data.get('remote') or {})
remote['url'] = f'http://127.0.0.1:{port}'
remote['authMode'] = 'token'
remote['token'] = {**dict(remote.get('token') or {}), 'value': token}
data['remote'] = remote
path.write_text(json.dumps(data, indent=2) + '\n')
PY

exec "$APP"
