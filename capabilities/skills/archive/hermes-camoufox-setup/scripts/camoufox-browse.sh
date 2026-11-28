#!/usr/bin/env bash
# Start Camoufox with cookie injection support (NODE_ENV=development)
# Usage: bash camoufox-browse.sh [port]
set -e

PORT="${1:-9377}"
CAMOFOX_DIR="/root/.hermes/hermes-agent/node_modules/@askjo/camofox-browser"

if [ ! -f "$CAMOFOX_DIR/server.js" ]; then
    echo "ERROR: Camoufox server not found at $CAMOFOX_DIR/server.js"
    echo "Install: cd /root/.hermes/hermes-agent && npm install @askjo/camofox-browser"
    exit 1
fi

if curl -s --max-time 2 "http://localhost:$PORT/health" >/dev/null 2>&1; then
    echo "Camoufox already running on port $PORT"
    curl -s "http://localhost:$PORT/health" | python3 -m json.tool
    exit 0
fi

echo "Starting Camoufox on port $PORT (NODE_ENV=development for cookie injection)..."
cd "$CAMOFOX_DIR"
NODE_ENV=development PORT=$PORT node server.js
